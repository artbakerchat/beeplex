#!/usr/bin/env python3
"""Beeplex user profile builder: maintain BEEPLEX_DATA_DIR/user.md.

Incrementally learns who the owner is from their Bee data and keeps a
living profile (the skill's user.md workflow, adapted to beeplex):

* new conversations since the last run -> speakers become Relationships,
  topics feed Work & Projects, explicit date mentions become Events
* Bee's confirmed/unconfirmed facts -> Basic info, Preferences, Notes
  (unconfirmed facts are always flagged as Bee's inference, not truth)
* Bee's insights -> Interests & Hobbies (attributed: "Bee noticed")
* frequent places -> Places

State lives in BEEPLEX_DATA_DIR/profile_state.json: per-conversation aggregates,
processed ids, and the `changed` cursor. Each run gathers only what's
new, then re-renders the whole user.md from state + fresh static data
(facts/insights/journals/places are small and idempotent, so they're
re-fetched every run). Both files stay local - BEEPLEX_DATA_DIR/ is gitignored -
because a user profile is personal data, never committed.

Extraction is deterministic and always runs. When an LLM provider is
configured (llm_scoring.available()), one extra call per run asks for
candidate profile updates as JSON, merged defensively; without a key
the profile is built from structure alone.

Usage:
    python -m python.profile            # incremental update
    python -m python.profile --full     # rebuild from scratch
    python -m python.profile --limit 50 # conversations considered on --full
"""

import json
import os
import re
import time
from datetime import datetime, timezone

from .config import DATA_DIR, DEMO

FAMILY = str(DATA_DIR)
PROFILE_MD = os.path.join(FAMILY, "user.md")
STATE_JSON = os.path.join(FAMILY, "profile_state.json")

# Speaker labels that mean the owner (case-insensitive).
OWNER_ALIASES = {"you", "me", "owner"}

# Explicit date mentions: "March 3rd", "Sep 12", weekdays.
_DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"\d{1,2}(?:st|nd|rd|th)?\b"
    r"|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
    re.IGNORECASE,
)

_PROFILE_PROMPT = """You are updating a personal profile from newly overheard conversations.
Reply with ONLY a JSON object. Include only keys you have real evidence for; omit the rest:
{"relationships": [{"name": "...", "note": "one concrete line about this person"}],
 "preferences": ["concrete likes/dislikes/preferences actually stated"],
 "events": [{"hint": "the date words used", "text": "what is happening"}],
 "notes": ["other concrete facts worth remembering"]}
Rules: concrete and specific, plain words, no therapy-speak. Only things actually said in the transcripts - never guess.

New conversations:
{blocks}"""


# --- state ---------------------------------------------------------------


def _load_state():
    try:
        with open(STATE_JSON, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    state.setdefault("processed_ids", [])
    state.setdefault("conversations", {})
    state.setdefault("changed_cursor", None)
    state.setdefault(
        "llm", {"relationships": {}, "preferences": [], "events": [], "notes": []}
    )
    state.setdefault("runs", 0)
    return state


def _save_state(state):
    os.makedirs(FAMILY, exist_ok=True)
    state["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = STATE_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_JSON)


# --- gathering -----------------------------------------------------------


def _is_live():
    from .bee_fetcher import cli_available, is_authenticated

    return cli_available() and is_authenticated()


def _summaries_to_targets(summaries, processed):
    """[(conv_id, summary)] for ids not yet processed."""
    targets = []
    for s in summaries or []:
        cid = s.get("id")
        if cid and str(cid) not in processed:
            targets.append((str(cid), s))
    return targets


def _gather_targets(limit, full, state, live):
    """Return (targets, new_cursor). targets is [(id, summary, utterances)].

    utterances is [(speaker, text)] or None when the transcript fetch
    failed (caller retries those on the next run). new_cursor is the
    `changed` cursor to persist after successful processing (None when
    the full path was used).
    """
    from .bee_fetcher import get_conversation, list_conversations, _utterance_parts
    from . import bee_sources

    processed = set(state["processed_ids"])
    new_cursor = None

    if live and not full and state["changed_cursor"]:
        batch = bee_sources.changed(cursor=state["changed_cursor"]) or {}
        targets = _summaries_to_targets(batch.get("conversations"), processed)
        new_cursor = batch.get("next_cursor")
    elif live:
        convs = list_conversations(limit=limit) or []
        targets = _summaries_to_targets(convs[:limit], processed)
        if not full and not state["changed_cursor"]:
            # Seed the changefeed cursor so the next run takes the
            # incremental `changed` path instead of re-listing.
            try:
                seed = bee_sources.changed() or {}
                new_cursor = seed.get("next_cursor")
            except Exception:
                new_cursor = None
    else:
        # No CLI configured: failures are explicit, never silent sample data.
        # Run with beeplex --demo (or BEE_CLI pointed at demo_cli.py) for the
        # sample-data path, which flows through this same live code.
        from .client import BeeError

        raise BeeError(
            "Bee CLI not found or not authenticated. Install with "
            "npm install -g @beeai/cli and run bee login, or use "
            "beeplex --demo for sample data."
        )

    resolved = []
    ok = True
    for cid, summary in targets:
        full_conv = get_conversation(cid)
        if full_conv is None:
            ok = False  # retry this conversation on the next run
            continue
        resolved.append((cid, summary, _utterance_parts(full_conv)))
    if not ok:
        new_cursor = None  # don't advance past a failed batch
    return resolved, new_cursor


def _gather_static():
    """Facts, insights, journals, places - re-fetched every run."""
    from . import bee_sources

    facts = (bee_sources.facts_list(limit=50, unconfirmed=True) or {}).get("facts", [])
    insights = (bee_sources.insights_list(limit=20) or {}).get("insights", [])
    journals = (bee_sources.journals_list(limit=20) or {}).get("journals", [])
    places = (bee_sources.locations_clusters(limit=20) or {}).get("clusters", [])
    return {
        "facts": facts,
        "insights": insights,
        "journals": journals,
        "places": places,
    }


# --- extraction ----------------------------------------------------------


def _is_owner(speaker):
    return (speaker or "").strip().lower() in OWNER_ALIASES


def _sentence_around(text, match):
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    end = len(text) if end == -1 else end + 1
    frag = text[start:end].strip().strip(".,!?;:\"'")
    return frag[:140]


def _extract(cid, summary, utterances):
    """Aggregate one conversation into state-sized signals."""
    speakers = {}
    for speaker, text in utterances or []:
        if _is_owner(speaker) or not (speaker or "").strip():
            continue
        name = speaker.strip()
        entry = speakers.setdefault(name, {"turns": 0, "words": 0})
        entry["turns"] += 1
        entry["words"] += len(text.split())

    mentions = []
    seen = set()
    for _speaker, text in utterances or []:
        for m in _DATE_RE.finditer(text):
            key = m.group(0).lower()
            if key in seen or len(mentions) >= 5:
                continue
            seen.add(key)
            mentions.append({"hint": m.group(0), "context": _sentence_around(text, m)})

    start = summary.get("start_time")
    date = None
    if isinstance(start, (int, float)):
        epoch = start / 1000.0 if start > 10_000_000_000 else float(start)
        date = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")

    return {
        "title": summary.get("title") or summary.get("summary") or cid,
        "summary": (summary.get("summary") or "")[:200],
        "date": date,
        "speakers": speakers,
        "date_mentions": mentions,
    }


def _bucket_fact(text):
    t = text.lower()
    if any(k in t for k in ("name is", "lives in", "born", "years old")):
        return "basic"
    if any(
        k in t
        for k in (
            "prefer",
            "like",
            "love",
            "hate",
            "dislike",
            "allergic",
            "favourite",
            "favorite",
            "can't stand",
            "cannot stand",
        )
    ):
        return "preferences"
    if any(
        k in t
        for k in (
            "work",
            "job",
            "project",
            "meeting",
            "client",
            "team",
            "company",
            "startup",
            "deadline",
            "launch",
        )
    ):
        return "work"
    return "notes"


def _llm_candidates(targets):
    """Best-effort LLM pass over the new transcripts. {} on any failure."""
    try:
        from .llm_scoring import llm_text, available
    except ImportError:
        return {}
    if not available() or not targets:
        return {}
    blocks = []
    total = 0
    for cid, summary, utterances in targets:
        if not utterances:
            continue
        title = summary.get("title") or cid
        text = "\n".join(f"{s or '?'}: {t}" for s, t in utterances[:40])
        block = f"### {title}\n{text[:1500]}"
        if total + len(block) > 6000:
            break
        blocks.append(block)
        total += len(block)
    if not blocks:
        return {}
    try:
        raw = llm_text(
            _PROFILE_PROMPT.replace("{blocks}", "\n\n".join(blocks)),
            max_output_tokens=1024,
            temperature=0.3,
        )
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_llm(state, candidates):
    llm = state["llm"]
    for rel in candidates.get("relationships") or []:
        if isinstance(rel, dict) and rel.get("name") and rel.get("note"):
            notes = llm["relationships"].setdefault(rel["name"].strip(), [])
            note = rel["note"].strip()[:200]
            if note and note not in notes:
                notes.append(note)
    for key in ("preferences", "events", "notes"):
        items = candidates.get(key) or []
        seen = {json.dumps(x, sort_keys=True) for x in llm[key]}
        for item in items:
            blob = json.dumps(item, sort_keys=True)
            if blob not in seen and len(llm[key]) < 50:
                seen.add(blob)
                llm[key].append(item)


# --- rendering -----------------------------------------------------------


def _render(state, static):
    convs = state["conversations"]
    n_conv = len(convs)

    # Relationships, merged across conversations.
    rels = {}
    for cid, c in convs.items():
        for name, s in c.get("speakers", {}).items():
            r = rels.setdefault(
                name, {"conversations": 0, "words": 0, "topics": [], "last": None}
            )
            r["conversations"] += 1
            r["words"] += s["words"]
            topic = (c.get("summary") or c.get("title") or "")[:70]
            if topic and topic not in r["topics"] and len(r["topics"]) < 3:
                r["topics"].append(topic)
            if c.get("date") and (not r["last"] or c["date"] > r["last"]):
                r["last"] = c["date"]
    llm_rels = state["llm"]["relationships"]

    # Facts, bucketed.
    buckets = {"basic": [], "preferences": [], "work": [], "notes": []}
    unconfirmed = []
    for f in static["facts"]:
        text = (f.get("text") or "").strip()
        if not text:
            continue
        if f.get("confirmed"):
            buckets[_bucket_fact(text)].append(text)
        else:
            unconfirmed.append(text)

    # Frequent topics across all conversations.
    topics = {}
    for c in convs.values():
        t = (c.get("summary") or c.get("title") or "").strip()
        if t:
            topics[t[:70]] = topics.get(t[:70], 0) + 1
    top_topics = sorted(topics.items(), key=lambda kv: -kv[1])[:8]

    # Date mentions, deduplicated.
    events = []
    seen_ev = set()
    for c in convs.values():
        for m in c.get("date_mentions", []):
            key = (m["hint"].lower(), m["context"].lower())
            if key in seen_ev:
                continue
            seen_ev.add(key)
            events.append({**m, "conversation": c.get("title"), "date": c.get("date")})

    L = []
    A = L.append
    A("# User Profile")
    A(
        f"_Last updated: {time.strftime('%Y-%m-%d')} "
        f"· {n_conv} conversation{'s' if n_conv != 1 else ''} processed_"
    )
    A("")
    A("> Built by beeplex from your Bee data. Bee's own claims are marked;")
    A("> unconfirmed facts are Bee's inferences and may be wrong.")
    A("")

    A("## Basic Information")
    if buckets["basic"]:
        for t in buckets["basic"]:
            A(f"- {t}")
    else:
        A("- —")
    A("")

    A("## Relationships")
    names = sorted(rels, key=lambda n: -rels[n]["conversations"])
    if not names:
        A("- —")
    for name in names:
        r = rels[name]
        A(f"### {name}")
        bits = [
            f"{r['conversations']} conversation{'s' if r['conversations'] != 1 else ''}",
            f"~{r['words']} words",
        ]
        if r["last"]:
            bits.append(f"last: {r['last']}")
        A(f"- {', '.join(bits)}")
        if r["topics"]:
            A(f"- Topics: {'; '.join(r['topics'])}")
        for note in llm_rels.get(name, [])[:2]:
            A(f"- Bee's read: {note}")
    A("")

    A("## Work & Projects")
    if buckets["work"]:
        for t in buckets["work"]:
            A(f"- {t} _(Bee fact)_")
    if top_topics:
        A("- Frequent topics: " + "; ".join(f"{t} ({n}×)" for t, n in top_topics))
    if not buckets["work"] and not top_topics:
        A("- —")
    A("")

    A("## Interests & Hobbies")
    if static["insights"]:
        for ins in static["insights"]:
            text = (ins.get("text") or ins.get("title") or "").strip()
            if text:
                A(f"- Bee noticed: {text}")
    else:
        A("- —")
    A("")

    A("## Preferences")
    prefs = buckets["preferences"] + [
        p for p in state["llm"]["preferences"] if isinstance(p, str)
    ]
    if prefs:
        for p in prefs:
            A(f"- {p}")
    else:
        A("- —")
    A("")

    A("## Places")
    if static["places"]:
        for p in static["places"]:
            name = p.get("name") or p.get("place") or "?"
            visits = p.get("visits")
            A(f"- {name}" + (f" ({visits} visits)" if visits else ""))
    else:
        A("- —")
    A("")

    A("## Important Dates & Events")
    ev_all = events + [e for e in state["llm"]["events"] if isinstance(e, dict)]
    if ev_all:
        for e in ev_all[:15]:
            hint = e.get("hint", "")
            text = e.get("text") or e.get("context", "")
            conv = e.get("conversation")
            line = f"- **{hint}**: {text}" if hint else f"- {text}"
            if conv:
                line += f" _(mentioned in: {conv[:50]})_"
            A(line)
    else:
        A("- —")
    A("")

    A("## Notes")
    notes = buckets["notes"] + [
        u + " _(unconfirmed — Bee inferred this, may be wrong)_" for u in unconfirmed
    ]
    for j in static["journals"][:5]:
        text = (j.get("text") or "").strip()
        if text:
            notes.append(f"Voice memo: {text[:140]}")
    notes += [n for n in state["llm"]["notes"] if isinstance(n, str)]
    if notes:
        for n in notes[:20]:
            A(f"- {n}")
    else:
        A("- —")
    A("")
    return "\n".join(L)


# --- entry point ---------------------------------------------------------


def run_profile(full=False, limit=50):
    """Build/update BEEPLEX_DATA_DIR/user.md. Returns (path, info)."""
    state = _load_state()
    if full:
        state = {
            "processed_ids": [],
            "conversations": {},
            "changed_cursor": None,
            "llm": {"relationships": {}, "preferences": [], "events": [], "notes": []},
            "runs": state.get("runs", 0),
        }
    live = _is_live()

    targets, new_cursor = _gather_targets(limit, full, state, live)
    for cid, summary, utterances in targets:
        state["conversations"][cid] = _extract(cid, summary, utterances)
        if cid not in state["processed_ids"]:
            state["processed_ids"].append(cid)

    if targets:
        _merge_llm(state, _llm_candidates(targets))
    if new_cursor:
        state["changed_cursor"] = new_cursor
    state["runs"] += 1

    static = _gather_static()
    os.makedirs(FAMILY, exist_ok=True)
    with open(PROFILE_MD, "w", encoding="utf-8") as fh:
        fh.write(_render(state, static))
    _save_state(state)

    return PROFILE_MD, {
        "mode": "demo" if DEMO else "live",
        "new_conversations": len(targets),
        "total_conversations": len(state["conversations"]),
        "facts": len(static["facts"]),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Build/update BEEPLEX_DATA_DIR/user.md from Bee data."
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="Rebuild from scratch instead of incrementally.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Conversations to consider on --full (default: 50).",
    )
    args = ap.parse_args()
    path, info = run_profile(full=args.full, limit=args.limit)
    print(
        f"mode={info['mode']} new={info['new_conversations']} "
        f"total={info['total_conversations']} facts={info['facts']}"
    )
    print(f"wrote {path}")
