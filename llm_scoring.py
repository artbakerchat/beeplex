"""Optional LLM enrichment for beeplex engagement scoring.

Sends conversation transcripts to Google's Gemini API for a second-opinion
engagement score plus a one-line rationale, a tone/positivity rating,
and a progress rating (is the conversation advancing or going in circles -
paraphrase-level restating can't be caught deterministically, so this is
the LLM's job).

All of a run's transcripts are scored in a SINGLE API call
(llm_engagement_batch); llm_engagement() is the one-conversation wrapper
used by simulator/record.py. Purely optional: without a ``GEMINI_API_KEY``
(or ``GOOGLE_API_KEY``) env var this module does nothing and the
deterministic heuristic in ``bee_fetcher.py`` stands alone. Any API failure
also degrades silently to the deterministic score - the report pipeline
never depends on the LLM.

Privacy: enabling this sends your transcript text to Google's API. The key
lives only in your environment or a gitignored .env file - never in the
repo, never in the reports.

No hard third-party dependencies: plain urllib against the Gemini REST API.
python-dotenv is optional - if installed, a .env file in the working
directory is loaded automatically.
"""

import json
import os
import urllib.request

try:
    from dotenv import load_dotenv
except ImportError:  # optional dependency; plain env vars still work
    pass
else:
    load_dotenv()  # GEMINI_API_KEY from a .env file if present

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)
TIMEOUT = 30
MAX_CHARS = 12_000

BATCH_PROMPT = """You are analyzing transcribed conversations.
For EACH conversation below:
1. Rate ENGAGEMENT 1-10 (1 = one person talking to silence, 10 = lively back-and-forth with everyone invested). Consider: balanced participation, follow-up questions, energy, topic depth.
2. Rate TONE 1-10 (1 = hostile, 10 = warm) and give it a one-word label (e.g. Warm, Friendly, Neutral, Tense, Hostile, Playful).
3. Give a one-sentence rationale for the engagement score.
4. Rate PROGRESS 1-10 (1 = going in circles, restating the same points; 10 = every turn advances: new points, decisions, building on what was said) and give it a one-word label (e.g. Advancing, Building, Circling, Spinning, Stalled).
Reply with ONLY a JSON object mapping each conversation number to its scores, no other text, e.g.:
{"0": {"engagement": 8, "rationale": "...", "tone": 6, "tone_label": "Neutral", "progress": 7, "progress_label": "Advancing"}, "1": {"engagement": 3, "rationale": "...", "tone": 8, "tone_label": "Warm", "progress": 4, "progress_label": "Circling"}}

Conversations:
{blocks}"""


def available():
    """True when an API key is configured (does not verify it)."""
    return bool(API_KEY)


def _valid_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return round(score, 1) if 1 <= score <= 10 else None


def _transcript_text(parts, max_chars=MAX_CHARS):
    transcript = "\n".join(f"{s}: {t}" if s else t for s, t in parts)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n[...truncated]"
    return transcript


def _post(prompt_text, max_output_tokens):
    """POST prompt_text to Gemini, return the raw reply text or None."""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_output_tokens},
    }).encode()
    req = urllib.request.Request(
        ENDPOINT + f"?key={API_KEY}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.load(resp)
    except Exception:
        return None
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return text
    except (KeyError, IndexError, TypeError):
        return None


def llm_engagement_batch(items):
    """Score many conversations with a SINGLE Gemini API call.

    ``items`` is [(key, parts)] with ``parts`` as [(speaker, text)].
    Returns {key: {"engagement": float, "rationale": str,
                   "tone": float|None, "tone_label": str,
                   "progress": float|None, "progress_label": str}}.
    Keys with no valid engagement score are omitted, so callers fall back
    to the deterministic score for those conversations.

    All-or-nothing by design: one failed call loses every LLM score for
    the run (the deterministic score always stands alone). Returns {}
    when no API key is configured.
    """
    items = [(key, parts) for key, parts in items if parts]
    if not API_KEY or not items:
        return {}
    blocks = "\n\n".join(
        f"### Conversation {key}\n{_transcript_text(parts)}" for key, parts in items
    )
    text = _post(BATCH_PROMPT.replace("{blocks}", blocks), max_output_tokens=2048)
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    results = {}
    for key, _ in items:
        entry = data.get(key)
        if not isinstance(entry, dict):
            continue
        engagement = _valid_score(entry.get("engagement"))
        if engagement is None:
            continue
        results[key] = {
            "engagement": engagement,
            "rationale": str(entry.get("rationale", "")).strip(),
            "tone": _valid_score(entry.get("tone")),
            "tone_label": str(entry.get("tone_label", "")).strip(),
            "progress": _valid_score(entry.get("progress")),
            "progress_label": str(entry.get("progress_label", "")).strip(),
        }
    return results


def llm_engagement(parts):
    """Score engagement and tone via Gemini (single conversation).

    Returns {"engagement": float|None, "rationale": str,
             "tone": float|None, "tone_label": str,
             "progress": float|None, "progress_label": str} -
    or None when no key is configured, the transcript is empty, or the
    request fails. Partial results are kept: a valid engagement score is
    returned even if the tone fields are missing/invalid.

    ``parts`` is [(speaker, text)] as built by bee_fetcher._utterance_parts.
    Implemented as a one-item batch so there is a single code path.
    """
    if not API_KEY or not parts:
        return None
    return llm_engagement_batch([("0", parts)]).get("0")
