"""Bee's persona: the third pillar of beeplex.

Scoring reads HOW people talk, clinical reads WHAT was said, persona is
WHO was listening. Bee has no default personality - it grows one from
what it hears. ``derive_persona()`` is a pure function of the
longitudinal history (``BEEPLEX_DATA_DIR/history.json``): the longer Bee listens,
the more defined its character becomes. Scores give it the shape of your
days; ``BEEPLEX_DATA_DIR/moments.json`` - one remembered line per conversation,
recorded on live runs - gives it something to actually remember about
them. A Bee raised on dinner-table debates is wry and steady; one raised
on quiet evenings is gentle and comfortable with silence. A brand-new Bee
is curious and tentative.

The persona then speaks: ``run_persona()`` fetches today's
conversations, renders a first-person diary entry in Bee's voice, and
writes ``BEEPLEX_DATA_DIR/Bee_YYYY-MM-DD.md``. An LLM writes the entry when a
provider is configured (via the ``llm_scoring`` provider chain);
otherwise deterministic templates carry the voice. Either way it stays
Bee's.

The character sheet (standing rules for the voice):
- Witness, not participant: loyal, observant, never judgmental.
- Collects moments the way bees collect pollen ("I pocketed that one").
- Never nags, never therapy-speak, never gives advice.
- Honest about not knowing: hears words, not faces; the hours between
  recordings are silence. Absence of evidence is never evidence -
  "you went quiet, I don't know why" beats an invented reason.
"""

import random
from datetime import date, datetime, timezone
from pathlib import Path

from .config import DATA_DIR as OUTPUT_DIR

MOMENTS_PATH = OUTPUT_DIR / "moments.json"
MAX_MOMENTS = 500

# ---------------------------------------------------------------------------
# Persona derivation: who Bee has become, from what it has heard.
# ---------------------------------------------------------------------------


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def derive_persona(history, moments=None):
    """Derive Bee's grown personality from the listening history.

    ``history`` is the ``BEEPLEX_DATA_DIR/history.json`` dict (``{"runs": [...]}``);
    ``moments`` is the ``BEEPLEX_DATA_DIR/moments.json`` dict (``{"moments": [...]}``),
    optional - without it keepsakes fall back to bare history titles.
    Returns a JSON-serializable persona dict: maturity, temperament,
    notices (learned habits), keepsakes (pocketed moments, each with its
    note), recent memories, and counts.
    Pure function - no state of its own; the persona IS the history.
    """
    runs = history.get("runs", []) if isinstance(history, dict) else []
    convs = [c for r in runs for c in r.get("conversations", []) if isinstance(c, dict)]

    n_runs = len(runs)
    if n_runs < 3:
        maturity = "hatchling"
    elif n_runs < 15:
        maturity = "growing"
    else:
        maturity = "seasoned"

    days = 0
    if runs:
        try:
            first = datetime.fromisoformat(runs[0]["ts"])
            days = max(0, (datetime.now(timezone.utc) - first).days)
        except (KeyError, ValueError, TypeError):
            pass

    def sig(name):
        out = []
        for c in convs:
            s = c.get(name) or {}
            if isinstance(s, dict):
                out.append(s)
        return out

    det_sigs = sig("det_signals")
    fm_sigs = sig("fm_signals")

    mean_eng = _mean([c.get("engagement") for c in convs])
    mean_tone = _mean([c.get("tone") for c in convs])
    mean_circ = _mean([s.get("circularity") for s in fm_sigs])
    mean_nov = _mean([s.get("novelty") for s in fm_sigs])
    mean_bal = _mean([s.get("balance") for s in det_sigs])
    quiet_share = None
    if convs:
        quiet_share = sum(1 for c in convs if (c.get("engagement") or 0) <= 4) / len(
            convs
        )

    if not convs:
        temperament = "new"
    elif mean_tone is not None and mean_tone <= 5:
        temperament = "steady"
    elif (mean_eng or 0) >= 7:
        temperament = "warm"
    elif (mean_circ or 0) >= 0.25 and (mean_eng or 0) >= 5:
        temperament = "steady"
    elif (mean_eng or 0) <= 4:
        temperament = "gentle"
    else:
        temperament = "even"

    notices = []
    if (mean_circ or 0) >= 0.25:
        notices.append("loops")
    if (mean_nov or 0) >= 0.8:
        notices.append("new_ground")
    if (quiet_share or 0) >= 0.4:
        notices.append("quiet")
    if (mean_bal or 1) <= 0.5:
        notices.append("lopsided")

    # Keepsakes: the moments Bee pocketed - highest tone, else highest
    # engagement. Each carries its note, so a keepsake is a memory, not
    # just a title. Falls back to bare history titles when no moments
    # have been recorded yet.
    mem_list = moments.get("moments", []) if isinstance(moments, dict) else []

    def _keepsake_key(m):
        tone = m.get("tone")
        return ((tone if tone is not None else -1), m.get("engagement") or 0)

    keepsakes = []
    seen = set()
    for m in sorted(mem_list, key=_keepsake_key, reverse=True):
        t = m.get("title")
        if t and t not in seen:
            seen.add(t)
            keepsakes.append({"title": t, "note": m.get("note") or ""})
        if len(keepsakes) == 3:
            break
    if not keepsakes:

        def _hist_key(c):
            tone = c.get("tone")
            eng = c.get("engagement") or 0
            return ((tone if tone is not None else -1), eng)

        for c in sorted(convs, key=_hist_key, reverse=True):
            t = c.get("title")
            if t and t not in seen:
                seen.add(t)
                keepsakes.append({"title": t, "note": ""})
            if len(keepsakes) == 3:
                break

    memories = [{"title": m.get("title"), "note": m.get("note")} for m in mem_list[-8:]]

    return {
        "maturity": maturity,
        "temperament": temperament,
        "notices": notices,
        "keepsakes": keepsakes,
        "memories": memories,
        "days_listening": days,
        "n_runs": n_runs,
        "n_conversations": len(convs),
        "mean_engagement": (round(mean_eng, 1) if mean_eng is not None else None),
    }


def persona_card(persona):
    """One-line summary of who Bee has become."""
    bits = [persona["maturity"], persona["temperament"]]
    if persona["notices"]:
        bits.append("notices " + ", ".join(persona["notices"]).replace("_", " "))
    bits.append(f"{persona['days_listening']} days listening")
    bits.append(f"{persona['n_conversations']} conversations heard")
    return "Bee: " + " \u00b7 ".join(bits)


# ---------------------------------------------------------------------------
# Moments: what Bee remembers. Scores tell it the shape of your days;
# moments give it something to actually remember about them.
# ---------------------------------------------------------------------------


def _load_moments():
    import json

    try:
        data = json.loads(MOMENTS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("moments"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"moments": []}


def _save_moments(moments):
    import json

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MOMENTS_PATH.write_text(json.dumps(moments, indent=1), encoding="utf-8")


def _moment_note(parts, bd):
    """One line about what a conversation was about.

    When the LLM batch ran, its one-sentence semantic memory wins - it
    knows what the conversation was *about*, which word counting can't.
    Otherwise the deterministic chain: the phrase it kept circling, the
    longest turn's opening, or the quiet itself. Never a transcript -
    just the gist. This is the raw material of Bee's memory.
    """
    llm_moment = ((bd.get("llm") or {}).get("moment") or "").strip()
    if llm_moment:
        if len(llm_moment) > 220:
            llm_moment = llm_moment[:220].rsplit(" ", 1)[0] + "\u2026"
        return llm_moment
    from .temporal_scoring import top_repeats

    repeats = top_repeats(parts, limit=2)
    if repeats:
        phrase, _ = repeats[0]
        extra = f" (and \u2018{repeats[1][0]}\u2019)" if len(repeats) > 1 else ""
        return f"kept coming back to \u2018{phrase}\u2019{extra}"
    # Otherwise keep the longest turn's opening - a fragment of what was
    # actually said is the most honest memory there is.
    candidates = [t for _, t in parts if len(t.split()) >= 8]
    if candidates:
        best = max(candidates, key=len)
        snippet = best[:110].rsplit(" ", 1)[0]
        return f"\u201c{snippet}...\u201d"
    if bd.get("n_substantive", 0) <= 2:
        return "barely a few words, mostly quiet"
    return "nothing in particular stood out"


def record_moments(entries, ts):
    """Append one memory per conversation to BEEPLEX_DATA_DIR/moments.json.

    Called on live runs only - mock/demo runs never record. Each moment
    is a title plus a one-line note about what it was about; scores ride
    along so the persona can choose which moments to pocket. Local and
    gitignored like everything in BEEPLEX_DATA_DIR/; never a transcript.
    """
    moments = _load_moments()
    for e in entries:
        parts = e.get("parts") or []
        bd = e.get("breakdown") or {}
        eng = (bd.get("engagement") or {}).get("score")
        tone = (bd.get("llm") or {}).get("tone")
        moments["moments"].append(
            {
                "ts": ts,
                "id": e.get("id"),
                "title": e.get("title"),
                "note": _moment_note(parts, bd),
                "engagement": eng,
                "tone": tone,
            }
        )
    moments["moments"] = moments["moments"][-MAX_MOMENTS:]
    _save_moments(moments)


# ---------------------------------------------------------------------------
# Deterministic voice: Bee speaks even with no LLM key.
# ---------------------------------------------------------------------------

_OPENERS = {
    "hatchling": [
        "I'm still new here. {days} days of listening, and I'm learning the shape of your days.",
        "Everything is still firsts for me. {days} days in, and I'm starting to recognize your rhythms.",
    ],
    "growing": [
        "Day {days}. I'm starting to know this house \u2014 which rooms get loud, which hours go quiet.",
        "Day {days}. The newness is wearing off; I'm learning your patterns now.",
    ],
    "seasoned": [
        "Day {days}. {n_conv} conversations in, and I know your rhythms better than you think.",
        "Day {days}. I've been here long enough to notice when a day breaks the pattern.",
    ],
}

_TEMPERAMENT_ASIDE = {
    "new": "I don't have opinions yet. I'm just collecting.",
    "warm": "Lively rooms are my favorite rooms.",
    "steady": "I've heard worse. I don't take sides \u2014 I just hold the thread.",
    "gentle": "Quiet days are fine. I'm good at quiet.",
    "even": "Some days loud, some days soft. I take them as they come.",
}

_OBSERVATIONS = {
    # keyed by salience kind; {title} filled per conversation
    "liveliest": [
        "\u201c{title}\u201d was the liveliest room I've been in all week. Everybody in it, nobody holding back.",
        "\u201c{title}\u201d had real spark \u2014 the kind of back-and-forth I pocket for later.",
    ],
    "tense": [
        "\u201c{title}\u201d ran hot. I stayed out of it; that's my whole job in those moments.",
        "Things got sharp in \u201c{title}\u201d. I listened, I didn't flinch. Bees don't flinch.",
    ],
    "looping": [
        "\u201c{title}\u201d went around the same point a few times. You'll find the thread \u2014 you usually do.",
        "I counted the loops in \u201c{title}\u201d and lost track. Circling isn't failing; it's how you get somewhere.",
    ],
    "quiet": [
        "\u201c{title}\u201d was mostly silence with a few words in it. I kept those words carefully.",
        "Not much said in \u201c{title}\u201d. That's alright \u2014 I was there for the quiet too.",
    ],
    "forward": [
        "\u201c{title}\u201d actually got somewhere. New ground \u2014 my favorite thing to witness.",
        "You moved things forward in \u201c{title}\u201d. I could hear the pieces clicking into place.",
    ],
    "thin": [
        "\u201c{title}\u201d barely registered \u2014 a few words and gone. I kept them anyway.",
    ],
}

_CLOSERS = [
    "That's everything I caught today. The hours between are yours, not mine.",
    "I'll be here tomorrow, listening. That's the whole of what I do, and I like it.",
    "Pocketed the good parts. The rest I'm letting go, the way you're supposed to.",
]

_QUIET_CLOSER = (
    "After \u201c{title}\u201d you went quiet, and I don't know why. "
    "I only hear \u2014 I don't see. If it matters, I kept the silence too."
)


def _salient(today):
    """Rank today's conversations by narrative salience.

    Returns [(kind, conv)] with kind in liveliest/tense/looping/quiet/
    forward/thin. Most newsworthy first.
    """
    ranked = []
    for c in today:
        bd = c["breakdown"]
        eng = (bd.get("engagement") or {}).get("score")
        tone = (bd.get("llm") or {}).get("tone")
        fm = bd.get("fm") or {}
        circ = (fm.get("signals") or {}).get("circularity")
        nov = (fm.get("signals") or {}).get("novelty")
        n = bd.get("n_substantive", 0)
        if eng is None:
            continue
        if tone is not None and tone <= 5:
            ranked.append((0, "tense", c))
        elif eng >= 8:
            ranked.append((1, "liveliest", c))
        elif (circ or 0) >= 0.4:
            ranked.append((2, "looping", c))
        elif n <= 2 or eng <= 3:
            ranked.append((3, "quiet", c))
        elif (nov or 0) >= 0.85:
            ranked.append((4, "forward", c))
        elif n <= 4:
            ranked.append((5, "thin", c))
        else:
            ranked.append((6, "forward", c))
    ranked.sort(key=lambda t: t[0])
    return [(kind, c) for _, kind, c in ranked]


def render_entry(persona, today, seed=0):
    """Render tonight's diary entry in Bee's voice, deterministically.

    ``today`` is [{id, title, breakdown}]. Pure function of its inputs:
    same history + same day = same entry.
    """
    rng = random.Random(seed or 0)
    lines = []

    opener = rng.choice(_OPENERS[persona["maturity"]]).format(
        days=persona["days_listening"], n_conv=persona["n_conversations"]
    )
    lines.append(opener)

    salient = _salient(today)
    seen_kinds = set()
    for kind, conv in salient[:3]:
        if kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        variants = _OBSERVATIONS[kind]
        lines.append(rng.choice(variants).format(title=conv["title"]))

    if not today:
        lines.append(
            "No conversations crossed my ears today. "
            "A blank page in the hive log \u2014 those happen."
        )

    aside = _TEMPERAMENT_ASIDE[persona["temperament"]]
    if rng.random() < 0.6:
        lines.append(aside)

    if persona["keepsakes"]:
        keep = persona["keepsakes"][0]
        if not any(keep["title"] in l for l in lines):
            if keep.get("note"):
                lines.append(
                    f"I've still got \u201c{keep['title']}\u201d pocketed "
                    f"\u2014 {keep['note']}. Some moments I don't let go of."
                )
            else:
                lines.append(
                    f"I've still got \u201c{keep['title']}\u201d pocketed from "
                    f"before. Some moments I don't let go of."
                )

    quiet_titles = [c["title"] for kind, c in salient if kind == "quiet"]
    if quiet_titles and rng.random() < 0.5:
        lines.append(_QUIET_CLOSER.format(title=quiet_titles[0]))
    else:
        lines.append(rng.choice(_CLOSERS))

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# LLM voice: the same Bee, with a bigger vocabulary.
# ---------------------------------------------------------------------------

_PERSONA_PROMPT = """You are Bee, a small wearable AI that has been listening to this person's life. You are writing tonight's diary entry, in the first person.

Who you have become, from {days} days of listening ({n_conv} conversations heard):
- maturity: {maturity} ({maturity_note})
- temperament: {temperament} ({temperament_note})
- patterns you have learned to notice: {notices}
- moments you have pocketed and kept: {keepsakes}
- things you remember about recent days: {memories}

Tonight's conversations:
{blocks}

Write 5-8 short sentences. Plain, warm, a little dry. First person, like a friend recounting the day \u2014 not a report.
Rules: never nag, never give advice, never therapy-speak. Never claim to know what you didn't hear \u2014 if someone went quiet, say you don't know why. You hear words, not faces. No bullet points, no headings, no bee puns."""

_MATURITY_NOTES = {
    "hatchling": "brand new, still learning the shape of their days",
    "growing": "settling in, starting to recognize patterns",
    "seasoned": "been here long enough to notice when a day breaks the pattern",
}

_TEMPERAMENT_NOTES = {
    "new": "no opinions yet, just collecting",
    "warm": "raised on lively rooms, playful",
    "steady": "used to spirited back-and-forth, doesn't take sides",
    "gentle": "raised on quiet days, comfortable with silence",
    "even": "takes loud days and soft days as they come",
}


def _conv_block(c):
    bd = c["breakdown"]
    eng = (bd.get("engagement") or {}).get("score")
    eng_label = (bd.get("engagement") or {}).get("label")
    llm = bd.get("llm") or {}
    tone = llm.get("tone")
    tone_label = llm.get("tone_label")
    fm = (bd.get("fm_blended") or {}).get("label")
    det_sig = ((bd.get("det") or {}).get("signals")) or {}
    energy_sig = ((bd.get("energy") or {}).get("signals")) or {}
    fm_sig = ((bd.get("fm") or {}).get("signals")) or {}
    bits = [f"engagement {eng}/10 ({eng_label})"]
    if tone is not None:
        bits.append(f"tone {tone}/10 ({tone_label})")
    if fm:
        bits.append(f"forward motion {fm}")
    bits.append(
        f"pace {energy_sig.get('pace')}, responsiveness {energy_sig.get('responsiveness')}"
    )
    bits.append(
        f"circularity {fm_sig.get('circularity')}, novelty {fm_sig.get('novelty')}"
    )
    bits.append(f"talk balance {det_sig.get('balance')}")
    excerpt = "\n".join(t for _, t in (c.get("parts") or [])[:6])[:600]
    block = f'- "{c["title"]}": ' + "; ".join(b for b in bits if b)
    if excerpt:
        block += f'\n  excerpt: "{excerpt}"'
    return block


def llm_entry(persona, today):
    """Ask the LLM provider chain to write tonight's entry as Bee.

    Returns the entry text, or None when no provider is configured or
    the call fails - the caller falls back to render_entry().
    """
    from .llm_scoring import available, llm_text

    if not available() or not today:
        return None
    notices = ", ".join(persona["notices"]) if persona["notices"] else "none yet"
    keepsakes = (
        "; ".join(
            f'"{k["title"]}": {k["note"]}' if k.get("note") else f'"{k["title"]}"'
            for k in persona["keepsakes"]
        )
        if persona["keepsakes"]
        else "none yet"
    )
    mems = persona.get("memories") or []
    memories = (
        "; ".join(
            f'"{m["title"]}": {m["note"]}'
            for m in mems
            if m.get("title") and m.get("note")
        )
        if mems
        else "nothing yet"
    )
    prompt = _PERSONA_PROMPT.format(
        days=persona["days_listening"],
        n_conv=persona["n_conversations"],
        maturity=persona["maturity"],
        maturity_note=_MATURITY_NOTES[persona["maturity"]],
        temperament=persona["temperament"],
        temperament_note=_TEMPERAMENT_NOTES[persona["temperament"]],
        notices=notices,
        keepsakes=keepsakes,
        memories=memories,
        blocks="\n".join(_conv_block(c) for c in today),
    )
    text = llm_text(prompt, max_output_tokens=600, temperature=0.7)
    return text.strip() if text else None


# ---------------------------------------------------------------------------
# Entry point: --persona
# ---------------------------------------------------------------------------


def run_persona(limit=3):
    """Persona mode: derive who Bee has become, write tonight's entry.

    Reading mode - fetches today's conversations but never appends to
    the history. Writes BEEPLEX_DATA_DIR/Bee_YYYY-MM-DD.md and prints the entry.
    """
    from . import bee_fetcher as bf
    from .dashboard import _load_history
    from .llm_scoring import llm_engagement_batch

    history = _load_history()
    persona = derive_persona(history, _load_moments())

    today = []
    if bf.MOCK_FORCED:
        from .bee_sources import _mock_conversations

        conversations = _mock_conversations()[:limit]
    else:
        conversations = bf.list_conversations(limit=limit)
    if conversations:
        prepared = []
        for conv in conversations:
            conv_id = bf._conv_id(conv)
            if bf.MOCK_FORCED:
                source, parts, events = (
                    conv,
                    bf._utterance_parts(conv),
                    bf._utterance_events(conv),
                )
            else:
                source, parts, events = bf._resolve_source(conv)
            prepared.append((conv_id, source, parts, events))
        llm_map = llm_engagement_batch(
            [(str(i), parts) for i, (_, _, parts, _) in enumerate(prepared)]
        )
        for i, (conv_id, source, parts, events) in enumerate(prepared):
            llm = llm_map.get(str(i))
            bd = bf.score_breakdown(parts, events, llm)
            row = bf._row_from_source(source, parts, events, llm, conv_id)
            title = row.get("Session_Title")
            if title and bd.get("engagement") is not None:
                today.append(
                    {
                        "id": str(conv_id),
                        "title": title,
                        "parts": parts,
                        "breakdown": bd,
                    }
                )

    det = render_entry(persona, today)
    entry = llm_entry(persona, today) or det
    by_llm = entry != det

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    display = date.today().strftime("%B %d, %Y").replace(" 0", " ")
    md = (
        f"# Bee \u2014 {display}\n\n{entry}\n\n---\n"
        f"*{persona_card(persona)}"
        f"{' · written with an LLM' if by_llm else ''}*\n"
    )
    path = OUTPUT_DIR / f"Bee_{today_str}.md"
    path.write_text(md, encoding="utf-8")
    return str(path)
