"""Temporal dynamics: the third scoring domain for beeplex.

Deterministic scoring reads a conversation's STRUCTURE (who talks, how
much, questions, length). The LLM reads its MEANING (energy, tone,
substance). This module reads its MOTION - how the conversation moves
through time:

  pace            words per minute per turn, vs a conversational norm
                  (~150 wpm: much faster reads agitated, much slower drags)
  responsiveness  reply latency *relative to the turn being answered* - a
                  3-second gap after a 25-word turn is an instant reply;
                  after "yeah" it is just a pause. Expected processing time
                  scales with the preceding turn's word count, so the 20+
                  word "substantial turn" bar doubles as the timing hint.
  circularity     3-4 word phrases repeated 2x+ inside 20+ word turns -
                  the "saying one thing on loop" detector
  spinning        structural signs of going in circles: questions answered
                  with questions, absolutist language ("you always/never"),
                  circling rhetoric ("as I said", "don't even start") -
                  catches the argument that restates one fight in fresh
                  words (novelty ~1.0) while going nowhere
  novelty         share of each turn's phrases never seen before in the
                  conversation (restating vs advancing)

pace + responsiveness -> temporal ENERGY (0-10), blended into Engagement.
circularity + novelty -> lexical motion, discounted by spinning ->
FORWARD MOTION (0-10), reported as its own axis:
engagement measures the heat, forward motion measures whether the heat
is cooking anything. A heated argument and a sharp debate can share an
engagement score while splitting on forward motion.

Needs per-utterance timestamps (Bee provides them); everything else is
plain arithmetic on the transcript text. No API calls, no key, no model.
Like the deterministic scorer, these signals are ambiguous on their own
(fast replies = excitement or interruption; repetition = rhetoric or
harping) - the semantic layer is what disambiguates them.
"""

import re

# Conversational speech norm; also the rate used to estimate how long a
# turn takes to say (and therefore how long a "fair" pause after it is).
SPEAKING_WPM = 150.0
# A turn this long counts as substantial: the same 20-word bar the
# deterministic depth signal uses for full marks. Only substantial turns
# get the repetition check (short turns are too small for phrase repeats
# to mean anything) and only they can anchor a speaking-rate estimate.
SUBSTANTIAL_WORDS = 20
# A natural beat between turns before the reply itself starts.
NATURAL_PAUSE_S = 1.0

_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text):
    return _WORD_RE.findall(text.lower())


def _ngram_counts(words, n):
    counts = {}
    for i in range(len(words) - n + 1):
        phrase = " ".join(words[i:i + n])
        counts[phrase] = counts.get(phrase, 0) + 1
    return counts


def phrase_repeats(text):
    """Map each 3-4 word phrase repeated 2x+ to its count.

    Only substantial (20+ word) turns are checked. Returns {} for short
    turns - phrase repetition inside a 6-word turn is noise, not signal.
    """
    words = _words(text)
    if len(words) < SUBSTANTIAL_WORDS:
        return {}
    repeats = {}
    for n in (4, 3):
        for phrase, count in _ngram_counts(words, n).items():
            if count >= 2:
                repeats[phrase] = max(repeats.get(phrase, 0), count)
    return repeats


def effective_words(text):
    """Word count with looped phrases discounted to their first occurrence.

    "we need to leave now" said three times is 15 raw words but one
    5-word thought - it contributes ~5 effective words. Greedy longest
    phrases first so a repeated 4-gram's inner 3-grams don't double-count.
    Short turns (<20 words) are returned as-is.
    """
    words = _words(text)
    n = len(words)
    if n < SUBSTANTIAL_WORDS:
        return n
    discounted = [False] * n
    for size in (4, 3):
        positions = {}
        for i in range(n - size + 1):
            positions.setdefault(" ".join(words[i:i + size]), []).append(i)
        for phrase_positions in positions.values():
            if len(phrase_positions) >= 2:
                # First occurrence kept; later ones are looped filler.
                for pos in phrase_positions[1:]:
                    for j in range(pos, pos + size):
                        discounted[j] = True
    return sum(1 for d in discounted if not d)


def top_repeats(parts, limit=3):
    """Most-looped phrases across a conversation: [(phrase, count)].

    Aggregates phrase_repeats() over the substantive turns, keeping each
    phrase's highest single-turn count. Used by the coaching dashboard to
    show the user exactly what they kept saying on loop.
    """
    from bee_fetcher import _is_substantive

    agg = {}
    for _, text in parts:
        if not _is_substantive(text):
            continue
        for phrase, count in phrase_repeats(text).items():
            agg[phrase] = max(agg.get(phrase, 0), count)
    return sorted(agg.items(), key=lambda kv: -kv[1])[:limit]


def circularity(text):
    """0..1: share of a turn's words lost to repeated phrases.

    0 = every word is new; approaching 1 = the turn is one thought on
    loop. Only meaningful for 20+ word turns (0.0 otherwise).
    """
    words = _words(text)
    if len(words) < SUBSTANTIAL_WORDS:
        return 0.0
    eff = effective_words(text)
    return round(1.0 - eff / len(words), 3)


# Absolutist language: "you always/never", bare always/never, "exact same".
# Well-established markers of heated, stuck exchanges - and purely lexical.
_ABSOLUTIST_RES = [
    re.compile(p) for p in (
        r"\byou always\b", r"\byou never\b",
        r"\balways\b", r"\bnever\b",
        r"\bexact same\b", r"\bevery single time\b",
    )
]
# Circling rhetoric: the stock phrases people reach for when an exchange
# is looping instead of advancing. Small, transparent, documented - not a
# sentiment model.
_CIRCLING_PHRASES = (
    "as i said", "like i said", "like i told you", "i already told you",
    "i've told you", "i have told you",
    "we've been over this", "we have been over this", "been through this",
    "don't even start", "dont even start", "do not even start",
    "stop twisting", "twisting my words", "twisting things",
    "for a change", "for once",
    "here we go again", "not this again", "again with this",
    "just admit",
)


def _has_absolutist(text):
    low = text.lower()
    return any(p.search(low) for p in _ABSOLUTIST_RES)


def _has_circling_marker(text):
    low = text.lower()
    return any(phrase in low for phrase in _CIRCLING_PHRASES)


def spinning(parts):
    """0..1: structural signs a conversation is going in circles.

    Higher = more spinning. Three sub-signals, averaged:
      question_chains   share of question-turns answered with another
                        question instead of an answer
      absolutist        share of substantive turns using absolutist
                        language ("you always/never", "exact same", ...)
      circling_markers  share of substantive turns containing circling
                        rhetoric ("as I said", "don't even start", ...)

    Reads the *shape* of the exchange, not its meaning: an argument that
    restates one fight in fresh words scores novelty ~1.0 while going
    nowhere, and this is the signal that catches it. Returns 0.0 when
    there is nothing to measure.
    """
    from bee_fetcher import _is_substantive

    turns = [t for _, t in parts if _is_substantive(t)]
    n = len(turns)
    if n < 2:
        return {"score": 0.0, "signals": {}}
    signals = {}
    q_idx = [i for i, t in enumerate(turns) if t.rstrip().endswith("?")]
    if q_idx:
        chained = sum(1 for i in q_idx
                      if i + 1 < n and turns[i + 1].rstrip().endswith("?"))
        signals["question_chains"] = round(chained / len(q_idx), 3)
    signals["absolutist"] = round(
        sum(1 for t in turns if _has_absolutist(t)) / n, 3)
    signals["circling_markers"] = round(
        sum(1 for t in turns if _has_circling_marker(t)) / n, 3)
    score = round(sum(signals.values()) / len(signals), 3)
    return {"score": score, "signals": signals}


def novelty(parts):
    """0..1: mean share of each turn's 3-word phrases never seen before.

    High = each turn advances the conversation; low = restating the same
    ground. The opening turn is excluded (everything is new at the start).
    ``parts`` is [(speaker, text)]; non-substantive turns are skipped via
    the shared substantive filter in bee_fetcher.
    """
    from bee_fetcher import _is_substantive

    turns = [t for _, t in parts if _is_substantive(t)]
    if len(turns) < 2:
        return None
    seen = set()
    scores = []
    for idx, text in enumerate(turns):
        words = _words(text)
        grams = {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
        if not grams:
            continue
        if idx > 0:
            scores.append(sum(1 for g in grams if g not in seen) / len(grams))
        seen.update(grams)
    return round(sum(scores) / len(scores), 3) if scores else None


def forward_motion(parts):
    """Forward-motion score 0..10 from circularity + novelty, discounted
    by spinning.

    The "is this going somewhere" axis, separate from engagement's
    "how heated is this" axis. Lexical motion (fresh phrases, no verbatim
    loops) is multiplied by (1 - spinning penalty): a conversation
    restating one fight in fresh words can score novelty ~1.0 while going
    nowhere, and the discount is what pulls it back down. Returns None
    when there is nothing substantive to measure.
    """
    from bee_fetcher import _is_substantive

    substantive = [t for _, t in parts if _is_substantive(t)]
    if not substantive:
        return None
    nov = novelty(parts)
    circs = [circularity(t) for t in substantive if len(_words(t)) >= SUBSTANTIAL_WORDS]
    if circs:
        circ = sum(circs) / len(circs)
        base = 0.5 * (1.0 - circ) + 0.5 * (nov if nov is not None else 0.5)
    elif nov is not None:
        circ = 0.0
        base = nov
    else:
        return None
    spin = spinning(parts)
    score = round(10.0 * base * (1.0 - 0.6 * spin["score"]), 1)
    label = "High" if score >= 7 else ("Moderate" if score >= 4 else "Low")
    signals = {
        "circularity": round(circ, 3),
        "novelty": nov,
        "spinning": spin["score"],
    }
    signals.update(spin["signals"])
    return {"score": score, "label": label, "signals": signals}


def _norm_ts(value):
    """Normalize a timestamp to epoch milliseconds, or None."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1e13:      # microseconds
        v /= 1000.0
    elif v > 1e11:    # already milliseconds
        pass
    elif v > 1e8:     # seconds
        v *= 1000.0
    else:
        return None
    return v


def temporal_energy(events):
    """Temporal energy 0..10 from pace + responsiveness.

    ``events`` is [(speaker, text, ts_ms|None)]. Turn duration comes from
    consecutive timestamps (turn start to next turn start); the last turn
    has no end and is skipped. Returns None when fewer than two
    timestamped utterances exist - then the temporal domain simply
    doesn't participate in the blend.
    """
    from bee_fetcher import _is_substantive

    seq = [(s, t, _norm_ts(ts)) for s, t, ts in events
           if t and _is_substantive(t) and _norm_ts(ts) is not None]
    if len(seq) < 2:
        return None

    pace_scores, resp_scores = [], []
    for (s1, t1, ts1), (s2, t2, ts2) in zip(seq, seq[1:]):
        gap_s = (ts2 - ts1) / 1000.0
        if gap_s <= 0:
            continue
        words = len(_words(t1))
        if words == 0:
            continue
        # Pace: this turn's speaking rate vs the conversational norm.
        wpm = words / gap_s * 60.0
        pace_scores.append(max(0.0, 1.0 - abs(wpm - SPEAKING_WPM) / SPEAKING_WPM))
        # Responsiveness: the gap relative to the turn being answered.
        # gap ~= turn duration + silence; expected duration comes from the
        # word count, so a quick reply to a long turn scores like the
        # instant reply it is.
        expected_s = words / SPEAKING_WPM * 60.0 + NATURAL_PAUSE_S
        ratio = gap_s / expected_s
        if ratio <= 1.0:
            # At or faster than expected: eager (slight dock at the
            # extreme - that starts to look like talking over each other).
            resp_scores.append(1.0 - 0.3 * (1.0 - ratio))
        else:
            resp_scores.append(1.0 / ratio)

    signals = {}
    if pace_scores:
        signals["pace"] = round(sum(pace_scores) / len(pace_scores), 3)
    if resp_scores:
        signals["responsiveness"] = round(sum(resp_scores) / len(resp_scores), 3)
    if not signals:
        return None
    score = round(sum(signals.values()) / len(signals) * 10, 1)
    label = "High" if score >= 7 else ("Moderate" if score >= 4 else "Low")
    return {"score": score, "label": label, "signals": signals}


def temporal_scores(events):
    """Both temporal outputs for a conversation.

    Returns {"energy": {...}|None, "forward_motion": {...}|None}.
    ``events`` is [(speaker, text, ts_ms|None)]; parts are derived
    internally for the text-only signals.
    """
    parts = [(s, t) for s, t, _ in events]
    return {
        "energy": temporal_energy(events),
        "forward_motion": forward_motion(parts),
    }
