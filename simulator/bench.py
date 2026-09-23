#!/usr/bin/env python3
"""bench.py - one-command engagement-scoring test harness.

Runs every registered scoring formula over every conversation in
simulator/conversations.json and prints a side-by-side comparison, so new
formulas can be judged against the same fixed fixtures instead of gut feel.

Usage:
    python3 bench.py

The fixture file is opened read-only; the harness never writes to it.
Recorded audio and transcripts under simulator/recordings/ are never touched.

Formulas
--------
Each formula is a function taking a list of utterance dicts
({speaker, text, pause_s, ...}) and returning a score from 0 to 10
(or None when the formula cannot score the conversation, e.g. no speaker
labels for a balance-based formula).

Ships with:
  utterance_count  baseline - the naive heuristic: raw utterance count,
                   20+ utterances = 10. Every comparison keeps this anchor.
  talk_balance     seed alternate - how evenly word share splits across
                   speakers (50/50 = 10, one-sided = 0).
  question_rate    seed alternate - share of substantive turns that ask a
                   question (30% = 10).
  turn_length      seed alternate - mean words per substantive turn
                   (20+ words = 10).

Register your own with a few lines at the bottom of this file:

    def my_formula(utterances):
        ...
        return score  # 0..10

    register("my_formula", my_formula)

For example, to benchmark the repo's current deterministic scorer:

    from bee_fetcher import engagement_signals

    def current_deterministic(utterances):
        parts = [(u.get("speaker") or "", u["text"]) for u in utterances]
        return engagement_signals(parts)["score"]

    register("current_deterministic", current_deterministic)
"""

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(HERE, "simulator", "conversations.json")

BACKCHANNELS = {
    "yeah", "yep", "yes", "no", "nope", "ok", "okay", "uh-huh", "mm-hmm",
    "hmm", "right", "sure", "thanks", "thank you", "bye", "hello", "hi",
}


# ---------------------------------------------------------------------------
# Shared helpers (local copies so the harness has zero repo-module imports)
# ---------------------------------------------------------------------------

def _words(text):
    return text.split()


def _is_substantive(text):
    if len(_words(text)) <= 3:
        return False
    cleaned = text.strip().strip(".,!?;:\"'").lower()
    return cleaned not in BACKCHANNELS


def _substantive(utterances):
    return [u for u in utterances if _is_substantive(u.get("text", ""))]


# ---------------------------------------------------------------------------
# Formula registry
# ---------------------------------------------------------------------------

FORMULAS = {}
FORMULA_ORDER = []


def register(name, fn):
    """Register a scoring formula. fn(utterances) -> 0..10 (or None)."""
    if name in FORMULAS:
        raise ValueError("formula %r already registered" % name)
    FORMULAS[name] = fn
    FORMULA_ORDER.append(name)


# ---------------------------------------------------------------------------
# Shipped formulas
# ---------------------------------------------------------------------------

def utterance_count(utterances):
    """Baseline: the naive utterance-count heuristic. 20+ utterances = 10."""
    return round(min(10.0, len(utterances) / 20.0 * 10.0), 1)


def talk_balance(utterances):
    """Seed alternate: word-share balance across speakers. 50/50 = 10.

    Returns None when fewer than two speakers are labeled.
    """
    counts = {}
    for u in _substantive(utterances):
        speaker = u.get("speaker")
        if speaker:
            counts[speaker] = counts.get(speaker, 0) + len(_words(u["text"]))
    if len(counts) < 2:
        return None
    total = sum(counts.values()) or 1
    shares = sorted(w / total for w in counts.values())
    if len(shares) == 2:
        balance = 1.0 - (shares[-1] - shares[0])
    else:
        balance = min(1.0, shares[0] * len(shares))
    return round(max(0.0, balance) * 10.0, 1)


def question_rate(utterances):
    """Seed alternate: share of substantive turns asking a question. 30% = 10."""
    subs = _substantive(utterances)
    if not subs:
        return 0.0
    questions = sum(1 for u in subs if u["text"].rstrip().endswith("?"))
    return round(min(1.0, questions / (len(subs) * 0.3)) * 10.0, 1)


def turn_length(utterances):
    """Seed alternate: mean words per substantive turn. 20+ words = 10."""
    subs = _substantive(utterances)
    if not subs:
        return 0.0
    avg = sum(len(_words(u["text"])) for u in subs) / len(subs)
    return round(min(1.0, avg / 20.0) * 10.0, 1)


register("utterance_count", utterance_count)
register("talk_balance", talk_balance)
register("question_rate", question_rate)
register("turn_length", turn_length)

# Add your own formulas here with register("name", fn).


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _short_name(conv):
    cid = conv.get("id", "?")
    return cid[4:] if cid.startswith("sim_") else cid


def _load_fixtures():
    with open(FIXTURES, "r", encoding="utf-8") as f:  # read-only
        convs = json.load(f)
    return convs


def run():
    convs = _load_fixtures()
    rows = []
    for conv in convs:
        utterances = conv.get("utterances", [])
        scores = {}
        for name in FORMULA_ORDER:
            try:
                scores[name] = FORMULAS[name](utterances)
            except Exception as e:  # a broken formula must not kill the run
                scores[name] = "ERR:%s" % e
        rows.append((_short_name(conv), len(utterances), scores))
    return rows


def _fmt(score):
    if score is None:
        return "n/a"
    if isinstance(score, str):
        return score
    return "%.1f" % score


def report(rows):
    names = FORMULA_ORDER
    label_w = max(len(r[0]) for r in rows + [("scenario", 0, {})]) + 2
    col_w = max(max(len(n) for n in names), 5) + 2

    lines = []
    header = "scenario".ljust(label_w) + "".join(n.ljust(col_w) for n in names)
    lines.append(header)
    lines.append("-" * len(header))
    for label, n_utt, scores in rows:
        line = label.ljust(label_w)
        line += "".join(_fmt(scores[n]).ljust(col_w) for n in names)
        lines.append(line)

    # Where the baseline anchor disagrees with the alternates.
    lines.append("")
    lines.append("Where the utterance-count baseline misses:")
    base = names[0]
    for label, n_utt, scores in rows:
        numeric = {n: s for n, s in scores.items()
                   if isinstance(s, (int, float))}
        if base not in numeric or len(numeric) < 2:
            continue
        others = {n: s for n, s in numeric.items() if n != base}
        hi = max(others, key=others.get)
        lo = min(others, key=others.get)
        b = numeric[base]
        if b >= max(others.values()):
            verdict = "baseline scores it HIGHEST"
        elif b <= min(others.values()):
            verdict = "baseline scores it LOWEST"
        else:
            verdict = "baseline in the middle"
        lines.append("  %-16s baseline %s - %s (%s: %s, %s: %s)"
                     % (label, _fmt(b), verdict, hi, _fmt(others[hi]),
                        lo, _fmt(others[lo])))
    return "\n".join(lines)


def main():
    rows = run()
    print(report(rows))
    print("")
    print("%d scenarios x %d formulas (fixtures read-only: %s)"
          % (len(rows), len(FORMULA_ORDER), FIXTURES))


if __name__ == "__main__":
    main()
