"""Optional LLM enrichment for beeplex engagement scoring.

Sends conversation transcripts to an LLM for a second-opinion engagement
score plus a one-line rationale, a tone/positivity rating, and a progress
rating (is the conversation advancing or going in circles -
paraphrase-level restating can't be caught deterministically, so this is
the LLM's job).

Two providers, one shared prompt. Gemini is tried first when
``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``) is set; if it is missing or the
call fails, AWS Bedrock (Nova) is tried via boto3 using your local AWS
credentials. If both are unavailable the deterministic heuristic in
``bee_fetcher.py`` stands alone - the report pipeline never depends on
the LLM.

All of a run's transcripts are scored in a SINGLE API call
(llm_engagement_batch); llm_engagement() is the one-conversation wrapper
used by simulator/record.py. Purely optional: without any configured
provider this module does nothing. Any API failure also degrades silently
to the deterministic score.

Privacy: enabling this sends your transcript text to Google's and/or
Amazon's API. Keys live only in your environment or a gitignored .env
file - never in the repo, never in the reports.

boto3 is a hard dependency for the Bedrock path; without it (or without
AWS credentials) that path is skipped silently. python-dotenv is optional
- if installed, a .env file in the working directory is loaded
automatically.
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
# Bedrock fallback: Nova is not served in-region in ca-central-1, so the
# default uses the US cross-region inference profile (documented AWS path
# for Canada). Override with BEDROCK_REGION / BEDROCK_MODEL as needed;
# AWS_REGION is also honored for the region.
BEDROCK_REGION = (
    os.environ.get("BEDROCK_REGION")
    or os.environ.get("AWS_REGION")
    or "ca-central-1"
)
BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "us.amazon.nova-lite-v1:0")
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
    """True when an LLM provider looks configured (does not verify it)."""
    if API_KEY:
        return True
    try:
        import boto3  # noqa: F401
    except ImportError:
        return False
    return True


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


def _gemini_post(prompt_text, max_output_tokens, temperature=0.2):
    """POST prompt_text to Gemini, return the raw reply text or None."""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": temperature,
                             "maxOutputTokens": max_output_tokens},
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


def _bedrock_post(prompt_text, max_output_tokens, temperature=0.2):
    """Send prompt_text to Bedrock Nova via the Converse API.

    Returns the raw reply text or None. Uses boto3's default credential
    chain (env vars, ~/.aws/credentials, IAM role) - no key handling here.
    """
    try:
        import boto3
    except ImportError:
        return None
    try:
        client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        resp = client.converse(
            modelId=BEDROCK_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt_text}]}],
            inferenceConfig={
                "maxTokens": max_output_tokens,
                "temperature": temperature,
            },
        )
    except Exception:
        return None
    try:
        blocks = resp["output"]["message"]["content"]
        text = "".join(b.get("text", "") for b in blocks).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return text or None
    except (KeyError, TypeError):
        return None


def _parse_batch(text, items):
    """Parse one provider's raw reply into {key: scores}. {} on any failure."""
    if not text:
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


def llm_engagement_batch(items):
    """Score many conversations with a SINGLE LLM API call.

    ``items`` is [(key, parts)] with ``parts`` as [(speaker, text)].
    Returns {key: {"engagement": float, "rationale": str,
                   "tone": float|None, "tone_label": str,
                   "progress": float|None, "progress_label": str}}.
    Keys with no valid engagement score are omitted, so callers fall back
    to the deterministic score for those conversations.

    Provider chain: Gemini first when an API key is set, then Bedrock Nova
    via boto3 (local AWS credentials). The first provider that returns
    usable scores wins; if neither does, returns {} and the deterministic
    score stands alone for the run.
    """
    items = [(key, parts) for key, parts in items if parts]
    if not items:
        return {}
    blocks = "\n\n".join(
        f"### Conversation {key}\n{_transcript_text(parts)}" for key, parts in items
    )
    prompt = BATCH_PROMPT.replace("{blocks}", blocks)
    results = {}
    if API_KEY:
        results = _parse_batch(_gemini_post(prompt, 2048), items)
    if not results:
        results = _parse_batch(_bedrock_post(prompt, 2048), items)
    return results


def llm_text(prompt, max_output_tokens=1024, temperature=0.7):
    """Send an arbitrary prompt through the provider chain.

    Returns the raw reply text, or None when no provider is configured
    or the call fails. Gemini first (when a key is set), then Bedrock
    Nova. Higher temperature default than scoring - this is for voice,
    not numbers.
    """
    if API_KEY:
        text = _gemini_post(prompt, max_output_tokens, temperature)
        if text:
            return text
    return _bedrock_post(prompt, max_output_tokens, temperature)


def llm_engagement(parts):
    """Score engagement and tone via the LLM provider chain.

    Returns {"engagement": float|None, "rationale": str,
             "tone": float|None, "tone_label": str,
             "progress": float|None, "progress_label": str} -
    or None when no provider is configured, the transcript is empty, or
    the requests fail. Partial results are kept: a valid engagement score
    is returned even if the tone fields are missing/invalid.

    ``parts`` is [(speaker, text)] as built by bee_fetcher._utterance_parts.
    Implemented as a one-item batch so there is a single code path.
    """
    if not parts or not available():
        return None
    return llm_engagement_batch([("0", parts)]).get("0")
