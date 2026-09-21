"""Bee CLI integration for beeplex.

Fetches real conversation data from the Bee wearable via the official Bee CLI
(``npm install -g @beeai/cli``) and maps it onto the report schema consumed by
``family.py``.

Two modes:

* ``live`` - the ``bee`` binary is on PATH and authenticated
  (``bee me --json`` succeeds). Real transcripts are fetched.
* ``mock`` - forced with ``BEEX_MOCK=1``, or used automatically when the CLI
  is missing or not logged in. Returns clearly-labelled sample data so the
  reports (and the hackathon demo) still run offline.

Hackathon note: the repo "actually calls Bee's technology in code" right here -
``subprocess`` calls to the official Bee CLI (an import of nothing and a
README mention would not count).

Privacy: Bee data is end-to-end encrypted and belongs to the owner. This
module only ever reads it through the owner's own authenticated CLI and never
writes transcripts to the repo - fetched data goes straight into the generated
reports in memory.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from llm_scoring import llm_engagement, llm_engagement_batch
from temporal_scoring import effective_words, temporal_scores

BEE_CMD = os.environ.get("BEE_CLI", "bee")
MOCK_FORCED = os.environ.get("BEEX_MOCK") == "1"
DEFAULT_TIMEOUT = 60

# Sentinel for "LLM result not pre-fetched": _engagement_cells falls back to a
# single-shot llm_engagement() call (used by simulator/record.py, which scores
# one recording). The batch path in fetch_report_data passes an explicit
# result (or None), never this sentinel, so a failed batch never triggers
# one-call-per-row retries.
_LLM_NOT_FETCHED = object()

# Schema keys consumed by family.py (docx / xlsx / pptx builders).
SCHEMA = [
    "Recording_Date",
    "Session_Title",
    "Source_Transcript_Snippet",
    "Key_Topic",
    "Tone_Rating",
    "Engagement_Level",
    "Forward_Motion",
    "Action_Items",
    "Summary_Notes",
]


def cli_available():
    """True when the `bee` binary is on PATH."""
    return shutil.which(BEE_CMD) is not None


def _run_bee(*args, timeout=DEFAULT_TIMEOUT):
    """Run `bee <args> --json` and return parsed JSON, or None on any failure."""
    if not cli_available():
        return None
    cmd = [BEE_CMD, *args]
    if "--json" not in cmd:
        cmd.append("--json")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None


def is_authenticated():
    """True when the CLI has a working Bee login."""
    return _run_bee("me") is not None


def list_conversations(limit=10):
    """Return normalized conversation dicts (summaries only), newest first."""
    payload = _run_bee("conversations", "list", "--limit", str(limit))
    if isinstance(payload, dict):
        items = payload.get("conversations") or payload.get("items") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    return [c for c in items if isinstance(c, dict)][:limit]


def get_conversation(conv_id):
    """Return one full conversation (verbatim utterances) or None."""
    payload = _run_bee("conversations", "get", str(conv_id))
    if isinstance(payload, dict):
        conv = payload.get("conversation", payload)
        return conv if isinstance(conv, dict) else None
    return None


def _conv_id(conv):
    return conv.get("id") or conv.get("conversation_id")


def _recording_date(conv):
    """Parse the conversation's start time into a date (the actual Bee
    recording date), or None when unavailable."""
    raw = (
        conv.get("start_time")
        or conv.get("started_at")
        or conv.get("created_at")
    )
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # epoch - millis if implausibly large
        epoch = raw / 1000.0 if raw > 10_000_000_000 else float(raw)
        return datetime.fromtimestamp(epoch, tz=timezone.utc).date()
    if isinstance(raw, str):
        text = raw.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d"):
            try:
                return datetime.strptime(text[: len(fmt)] if len(text) > len(fmt) else text, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None
    return None


def _utterance_parts(conv):
    """Return [(speaker, text)] for a conversation payload, order preserved."""
    utterances = conv.get("utterances") or conv.get("transcript") or []
    if isinstance(utterances, str):
        text = utterances.strip()
        return [(None, text)] if text else []
    parts = []
    for u in utterances:
        if isinstance(u, str):
            text = u.strip()
            if text:
                parts.append((None, text))
        elif isinstance(u, dict):
            for key in ("text", "content", "utterance"):
                if u.get(key):
                    text = str(u[key]).strip()
                    if text:
                        parts.append((u.get("speaker") or u.get("role"), text))
                    break
    return parts


def _utterance_texts(conv):
    """Extract verbatim utterance texts (display form) from a payload."""
    return [f"{s}: {t}" if s else t for s, t in _utterance_parts(conv)]


def _utterance_events(conv):
    """Return [(speaker, text, ts_ms|None)] for a conversation payload.

    Timestamps come from the utterance's own fields ("timestamp",
    "start_time", ...); Bee emits epoch milliseconds. Missing or
    unparseable timestamps become None - the temporal domain then skips
    what it can't measure instead of guessing.
    """
    utterances = conv.get("utterances") or conv.get("transcript") or []
    if isinstance(utterances, str):
        text = utterances.strip()
        return [(None, text, None)] if text else []
    events = []
    for u in utterances:
        if isinstance(u, str):
            text = u.strip()
            if text:
                events.append((None, text, None))
        elif isinstance(u, dict):
            for key in ("text", "content", "utterance"):
                if u.get(key):
                    text = str(u[key]).strip()
                    if text:
                        ts = None
                        for tkey in ("timestamp", "start_time", "startTime",
                                     "ts", "time", "t"):
                            if u.get(tkey) is not None:
                                ts = u.get(tkey)
                                break
                        events.append(
                            (u.get("speaker") or u.get("role"), text, ts))
                    break
    return events


# Words that carry no substance on their own - filtered out of the engagement
# signals so "yeah / uh-huh / ok" ping-pong can't fake a lively conversation.
BACKCHANNELS = frozenset({
    "yeah", "yep", "yes", "no", "nope", "ok", "okay", "mm", "mhm", "mm-hm",
    "uh-huh", "uh", "um", "hmm", "right", "sure", "thanks", "thank you",
    "bye", "hi", "hello", "hey",
})


def _is_substantive(text):
    words = text.split()
    if len(words) <= 3:
        return False
    cleaned = text.strip().strip(".,!?;:\"'").lower()
    return cleaned not in BACKCHANNELS


def engagement_signals(parts):
    """Deterministic engagement signals from [(speaker, text)] utterance parts.

    Returns {"score": 0..10, "label": "High"|"Moderate"|"Low",
             "signals": {...}}. Each sub-signal is 0..1; when speaker labels
    are missing, balance/interactivity drop out and the remaining weights
    are renormalized so the score stays comparable:

      balance        0.30  how evenly talk time splits across speakers
                               (50/50 = 1.0, monologue -> 0.0)
      interactivity  0.25  rate of speaker switches between turns
      curiosity      0.20  share of utterances that ask questions
                               (30% question rate = full marks)
      depth          0.25  average substantive utterance length
                               (20+ words = full marks)

    Backchannel-only turns ("yeah", "ok", ...) are excluded before scoring.
    """
    substantive = [(s, t) for s, t in parts if _is_substantive(t)]
    n = len(substantive)

    signals = {}
    weights = {}

    speakers = [s for s, _ in substantive if s]
    if len(set(speakers)) >= 2:
        word_counts = {}
        for s, t in substantive:
            if s:
                word_counts[s] = word_counts.get(s, 0) + len(t.split())
        total = sum(word_counts.values()) or 1
        shares = sorted(w / total for w in word_counts.values())
        if len(shares) == 2:
            balance = 1.0 - (shares[-1] - shares[0])
        else:
            # multi-speaker: how close the quietest speaker is to equal share
            balance = min(1.0, shares[0] * len(shares))
        signals["balance"] = round(balance, 3)
        weights["balance"] = 0.30

        switches = sum(1 for a, b in zip(speakers, speakers[1:]) if a != b)
        signals["interactivity"] = round(switches / max(1, len(speakers) - 1), 3)
        weights["interactivity"] = 0.25
    elif speakers:
        # One person doing all the substantive talking: a monologue, not a
        # conversation. Score the missing participation as zero, keeping the
        # weights so depth alone can't rescue it.
        signals["balance"] = 0.0
        weights["balance"] = 0.30
        signals["interactivity"] = 0.0
        weights["interactivity"] = 0.25
    # (no speaker labels at all: balance/interactivity drop out and the
    # remaining weights renormalize, so unlabeled transcripts still score)

    questions = sum(1 for _, t in substantive if t.rstrip().endswith("?"))
    signals["curiosity"] = round(min(1.0, questions / max(1, n * 0.3)), 3)
    weights["curiosity"] = 0.20

    # Depth counts *effective* words: a 30-word turn that loops one 8-word
    # thought on repeat contributes ~8 words, not 30. Short turns are
    # unaffected (the repetition check only runs on 20+ word turns).
    avg_words = sum(effective_words(t) for _, t in substantive) / max(1, n)
    signals["depth"] = round(min(1.0, avg_words / 20.0), 3)
    weights["depth"] = 0.25

    wsum = sum(weights.values()) or 1
    score = round(sum(signals[k] * weights[k] for k in signals) / wsum * 10, 1)
    if n < 5:
        # Few substantive turns: the intensity may be real but the evidence
        # is thin, so cap at Moderate no matter what the signals say.
        score = min(score, 6.9)
    label = "High" if score >= 7 else ("Moderate" if score >= 4 else "Low")
    return {"score": score, "label": label, "signals": signals}


def score_breakdown(parts, events, llm=_LLM_NOT_FETCHED):
    """Full numeric scoring breakdown for one conversation.

    Returns a JSON-serializable dict with every domain's score, label and
    sub-signals plus the blended Engagement and Forward Motion, the
    substantive-turn count, and per-speaker talk shares. ``_engagement_cells``
    renders the report cells from this; ``dashboard.py`` renders the
    coaching dashboard from it. Empty transcript -> everything None.
    """
    if not parts:
        return {"det": None, "energy": None, "fm": None, "llm": None,
                "engagement": None, "fm_blended": None,
                "n_substantive": 0, "speaker_shares": None}
    if llm is _LLM_NOT_FETCHED:
        llm = llm_engagement(parts)
    det = engagement_signals(parts)
    temporal = temporal_scores(events)
    energy = temporal["energy"]
    fm = temporal["forward_motion"]

    domains = [det["score"]]
    if energy is not None:
        domains.append(energy["score"])
    llm_eng = llm.get("engagement") if llm else None
    if llm_eng is not None:
        domains.append(llm_eng)
    eng_score = round(sum(domains) / len(domains), 1)
    engagement = {"score": eng_score,
                  "label": "High" if eng_score >= 7
                  else ("Moderate" if eng_score >= 4 else "Low")}

    fm_domains = []
    if fm is not None:
        fm_domains.append(fm["score"])
    llm_prog = llm.get("progress") if llm else None
    if llm_prog is not None:
        fm_domains.append(llm_prog)
    fm_blended = None
    if fm_domains:
        s = round(sum(fm_domains) / len(fm_domains), 1)
        fm_blended = {"score": s,
                      "label": "High" if s >= 7
                      else ("Moderate" if s >= 4 else "Low")}

    llm_out = None
    if llm:
        llm_out = {k: llm.get(k) for k in ("engagement", "rationale", "tone",
                                           "tone_label", "progress",
                                           "progress_label")}

    substantive = [(s, t) for s, t in parts if _is_substantive(t)]
    shares = None
    speakers = [s for s, _ in substantive if s]
    if len(set(speakers)) >= 2:
        counts = {}
        for s, t in substantive:
            if s:
                counts[s] = counts.get(s, 0) + len(t.split())
        total = sum(counts.values()) or 1
        shares = {s: round(c / total, 3)
                  for s, c in sorted(counts.items(), key=lambda kv: -kv[1])}

    return {
        "det": {"score": det["score"], "label": det["label"],
                "signals": det["signals"]},
        "energy": ({"score": energy["score"], "label": energy["label"],
                    "signals": energy["signals"]} if energy is not None
                   else None),
        "fm": ({"score": fm["score"], "label": fm["label"],
                "signals": fm["signals"]} if fm is not None else None),
        "llm": llm_out,
        "engagement": engagement,
        "fm_blended": fm_blended,
        "n_substantive": len(substantive),
        "speaker_shares": shares,
    }


def _engagement_cells(parts, events, llm=_LLM_NOT_FETCHED):
    """Return (engagement_cell, tone_cell, forward_motion_cell) for a row.

    Renders the display cells from score_breakdown() - the numeric source
    of truth both the reports and the coaching dashboard share.

    Engagement is the mean of the available scoring domains - deterministic
    (structure), temporal energy (motion), and Gemini (meaning) when
    llm_scoring has a key and succeeds. The LLM's one-line rationale is
    appended so the report shows the *why*. Tone: Gemini's 1-10 positivity
    rating + one-word label ("Warm (8/10)"); "—" when the LLM is
    unavailable - tone can't be done deterministically. Forward motion is
    the temporal domain's second output and stays its own axis: engagement
    measures the heat, forward motion whether the heat cooks anything.
    Empty transcript -> ("—", "—", "—").

    ``llm`` is a pre-fetched llm_engagement() result (or None). When omitted,
    a single-shot llm_engagement() call is made - the one-recording path.
    """
    bd = score_breakdown(parts, events, llm)
    if bd["engagement"] is None:
        return "—", "—", "—"
    e = bd["engagement"]
    engagement_cell = f"{e['label']} ({e['score']})"
    rationale = (bd["llm"] or {}).get("rationale")
    if rationale:
        engagement_cell += f" — {rationale}"
    l = bd["llm"] or {}
    tone = l.get("tone")
    tone_label = (l.get("tone_label") or "").strip()
    if tone is None:
        tone_cell = "—"
    elif tone_label:
        tone_cell = f"{tone_label} ({tone}/10)"
    else:
        tone_cell = f"{tone}/10"
    fmb = bd["fm_blended"]
    if fmb is None:
        forward_motion_cell = "—"
    else:
        forward_motion_cell = f"{fmb['label']} ({fmb['score']})"
        plabel = (l.get("progress_label") or "").strip()
        if plabel:
            forward_motion_cell += f" [{plabel}]"
    return engagement_cell, tone_cell, forward_motion_cell


def _resolve_source(conv):
    """Fetch the full conversation and return (source_payload, parts, events)."""
    conv_id = _conv_id(conv)
    full = get_conversation(conv_id) if conv_id is not None else None
    source = full if full else conv
    return source, _utterance_parts(source), _utterance_events(source)


def _row_from_source(source, parts, events, llm=_LLM_NOT_FETCHED, conv_id=None):
    """Map a resolved conversation payload onto the family.py report schema."""
    title = (
        source.get("title")
        or source.get("name")
        or source.get("summary")
        or (f"Conversation {conv_id}" if conv_id is not None else "Conversation")
    )
    summary = source.get("summary") or source.get("description") or ""

    utterances = _utterance_texts(source)
    snippet = " ".join(utterances[:3])
    if len(snippet) > 220:
        snippet = snippet[:217] + "..."
    if not snippet and summary:
        snippet = summary[:220]

    key_topic = (summary[:60] + "...") if len(summary) > 60 else (summary or "—")

    engagement_cell, tone_cell, forward_motion_cell = _engagement_cells(
        parts, events, llm)

    return {
        # The actual Bee recording date - wired into report titles by family.py.
        "Recording_Date": _recording_date(source),
        "Session_Title": str(title)[:80],
        "Source_Transcript_Snippet": snippet,
        "Key_Topic": key_topic,
        "Tone_Rating": tone_cell,
        "Engagement_Level": engagement_cell,
        "Forward_Motion": forward_motion_cell,
        # Per-conversation action items are not exposed by the CLI; the global
        # `bee todos suggestions` feed can be mined separately.
        "Action_Items": "",
        "Summary_Notes": summary,
    }


def conversation_to_row(conv, llm=_LLM_NOT_FETCHED):
    """Map one conversation payload onto the family.py report schema.

    Convenience wrapper: resolves the full conversation, then builds the
    row. ``llm`` is a pre-fetched llm_engagement() result (or None); when
    omitted a single-shot LLM call is made for this conversation.
    """
    conv_id = _conv_id(conv)
    source, parts, events = _resolve_source(conv)
    return _row_from_source(source, parts, events, llm, conv_id)


def mock_rows():
    """Sample data used when the Bee CLI is unavailable (demo / CI / offline)."""
    from datetime import date

    today = date.today()
    return [
        {
            "Recording_Date": today,
            "Session_Title": "Product Strategy Sync [MOCK]",
            "Source_Transcript_Snippet": "...we need to finalize the Q3 roadmap by Friday and assign module owners...",
            "Key_Topic": "Roadmap Deadlines",
            "Tone_Rating": "7/10 (Moderate Positive)",
            "Engagement_Level": "High",
            "Forward_Motion": "—",
            "Action_Items": "Finalize Q3 roadmap by Friday; assign module owners.",
            "Summary_Notes": "Team aligned on core priorities and established strict delivery milestones.",
        },
        {
            "Recording_Date": today,
            "Session_Title": "Client Feedback Review [MOCK]",
            "Source_Transcript_Snippet": "...the client mentioned latency issues during peak hours, need an urgent patch...",
            "Key_Topic": "Performance Bug",
            "Tone_Rating": "4/10 (Low / Tense)",
            "Engagement_Level": "High",
            "Forward_Motion": "—",
            "Action_Items": "Deploy latency patch before Monday peak hours.",
            "Summary_Notes": "Addressed urgent customer friction point; engineering team to investigate.",
        },
        {
            "Recording_Date": today,
            "Session_Title": "Weekly Team Catch-up [MOCK]",
            "Source_Transcript_Snippet": "...everyone's workload looks balanced, let's keep the current sprint velocity...",
            "Key_Topic": "Workload & Velocity",
            "Tone_Rating": "9/10 (High Positive)",
            "Engagement_Level": "Moderate",
            "Forward_Motion": "—",
            "Action_Items": "Maintain current sprint tasks; schedule next retro.",
            "Summary_Notes": "Positive alignment; team morale is high and pacing is sustainable.",
        },
    ]


def fetch_report_data(limit=10):
    """Fetch conversation rows for the reports.

    Returns (rows, info) where info describes the source:
    {"mode": "live"|"mock", "detail": ...}.
    """
    if MOCK_FORCED:
        rows, info = mock_rows(), {
            "mode": "mock",
            "detail": "BEEX_MOCK=1 - forced mock data",
        }
    elif not cli_available():
        rows, info = mock_rows(), {
            "mode": "mock",
            "detail": f"'{BEE_CMD}' not found - install with: npm install -g @beeai/cli",
        }
    elif not is_authenticated():
        rows, info = mock_rows(), {
            "mode": "mock",
            "detail": "Bee CLI not authenticated - run `bee login` (or `bee login --no-wait`)",
        }
    else:
        rows, info = _fetch_live(limit)
    # Mock runs regenerate the dashboard from history (demo banner, no
    # new history entry); the live path records the run itself.
    if info["mode"] == "mock":
        from dashboard import record_run
        record_run([], info)
    return rows, info


def _fetch_live(limit):
    """Live path of fetch_report_data: CLI list/get, batch LLM, dashboard."""

    conversations = list_conversations(limit=limit)

    # Resolve all sources first, then score every transcript with ONE
    # Gemini call (llm_engagement_batch). A failed batch degrades to the
    # deterministic score for every row - never one call per row.
    prepared = []
    for conv in conversations:
        conv_id = _conv_id(conv)
        source, parts, events = _resolve_source(conv)
        prepared.append((conv_id, source, parts, events))
    llm_map = llm_engagement_batch(
        [(str(i), parts) for i, (_, _, parts, _) in enumerate(prepared)]
    )
    scored = [
        (conv_id, source, parts, events, llm_map.get(str(i)))
        for i, (conv_id, source, parts, events) in enumerate(prepared)
    ]
    pairs = [
        (_row_from_source(source, parts, events, llm, conv_id),
         (conv_id, source, parts, events, llm))
        for conv_id, source, parts, events, llm in scored
    ]
    pairs = [(row, meta) for row, meta in pairs if row["Session_Title"]]
    rows = [row for row, _ in pairs]

    # Coaching dashboard: append this run's scores to the local trend
    # history and regenerate family/dashboard.html. Automatic on every
    # run; mock mode regenerates the page from history without appending.
    from dashboard import record_run
    record_run(
        [
            {
                "id": str(conv_id),
                "title": row["Session_Title"],
                "date": (str(row["Recording_Date"])
                         if row.get("Recording_Date") else None),
                "parts": parts,
                "breakdown": score_breakdown(parts, events, llm),
            }
            for row, (conv_id, source, parts, events, llm) in pairs
        ],
        {"mode": "live"},
    )
    return rows, {
        "mode": "live",
        "detail": f"{len(rows)} conversations via Bee CLI",
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="beeplex - Bee conversation reports (default) or "
                    "clinical encounter extraction (--clinical).")
    ap.add_argument("--clinical", action="store_true",
                    help="Clinical mode: doctor-worn Bee encounter -> "
                         "one-page clinical summary per conversation "
                         "(extraction only, no engagement scoring).")
    ap.add_argument("--limit", type=int, default=3,
                    help="Max conversations to process (default: 3).")
    args = ap.parse_args()

    if args.clinical:
        from clinical_extraction import run_clinical
        run_clinical(limit=args.limit)
    else:
        rows, info = fetch_report_data(limit=args.limit)
        print(f"mode={info['mode']} ({info['detail']})")
        for row in rows:
            print(f"- {row['Recording_Date']} | {row['Session_Title']}")
