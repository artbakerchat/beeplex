"""Validation helpers for the spontaneous-speech annotation standard.

The Bee API supplies text, but it does not guarantee that the text follows the
annotation convention used by the voice editor.  This module deliberately
validates rather than silently rewrites transcripts: audio annotation is a
human judgment and an automatic rewrite could remove a real speech event.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


FILLER_WORDS = (
    "uh",
    "uhm",
    "ugh",
    "hmm",
    "mm-hmm",
    "yeah",
    "yep",
    "yup",
    "oh",
    "aw",
    "eh",
    "ah",
    "pfft",
    "shh",
    "ooh",
    "huh",
    "uh-huh",
    "psst",
)
FILLER_SET = frozenset(FILLER_WORDS)
NONVERBAL_TAGS = frozenset(
    {
        "laugh",
        "cry",
        "gag",
        "throatclear",
        "gasp",
        "cough",
        "swallow",
        "noise",
        "inaudible",
        "pause",
    }
)
SUPPORTED_PUNCTUATION = frozenset('.?!,\"\'-')
COMMON_SPELLINGS = {
    "okay": "OK",
    "o.k.": "OK",
    "ok": "OK",
    "alright": "All right",
    "woah": "Whoa",
}


@dataclass(frozen=True)
class GuidelineIssue:
    code: str
    message: str
    severity: str = "warning"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


_ANGLE_RE = re.compile(r"<([^<>]*)>")
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")
_UNCLEAR_RE = re.compile(r"\(\(([^()]*)\)\)")
_FOREIGN_RE = re.compile(r"\{([^{}]*)\}")
_SPEAKER_LABEL_RE = re.compile(r"\(Speaker\s+\w+\)\s*", re.IGNORECASE)
_UNBRACKETED_FILLER_RE = re.compile(
    r"(?<![\w\[])\b(" + "|".join(re.escape(x) for x in sorted(FILLER_WORDS, key=len, reverse=True)) + r")\b(?!\])",
    re.IGNORECASE,
)


def validate_transcript(text: str, *, speaker: str | None = None) -> list[GuidelineIssue]:
    """Return actionable issues without changing *text*.

    The validator permits the guideline's annotation wrappers (``[]``, ``<>``,
    ``(())`` and ``{}``) while rejecting unknown tags and unsupported prose
    punctuation.  It intentionally reports possible issues instead of claiming
    that an audio event is present or absent; that requires listening.
    """

    issues: list[GuidelineIssue] = []
    if not isinstance(text, str) or not text.strip():
        return [GuidelineIssue("empty", "Add the words or non-verbal events heard in the audio.", "error")]

    for match in _ANGLE_RE.finditer(text):
        tag = match.group(1).strip().lower()
        if tag not in NONVERBAL_TAGS:
            issues.append(GuidelineIssue("unknown-tag", f"Unknown angle-bracket tag <{match.group(1)}>."))
    for match in _BRACKET_RE.finditer(text):
        value = match.group(1).strip().lower()
        if value not in FILLER_SET:
            issues.append(GuidelineIssue("unknown-filler", f"[{match.group(1)}] is not a supported filler word."))

    if _UNBRACKETED_FILLER_RE.search(text):
        issues.append(GuidelineIssue("unbracketed-filler", "Filler words must be enclosed in square brackets, for example [uh]."))

    masked = _ANGLE_RE.sub(" ", text)
    masked = _BRACKET_RE.sub(" ", masked)
    masked = _UNCLEAR_RE.sub(" ", masked)
    masked = _FOREIGN_RE.sub(" ", masked)
    masked = _SPEAKER_LABEL_RE.sub(" ", masked)
    masked = masked.replace("!?", "")
    unsupported = sorted({char for char in masked if not (char.isalnum() or char.isspace() or char in SUPPORTED_PUNCTUATION)})
    if unsupported:
        issues.append(GuidelineIssue("unsupported-punctuation", "Use only . ? ! , quotes, apostrophes, and hyphens in prose: " + " ".join(unsupported) + ".", "error"))

    for found, preferred in COMMON_SPELLINGS.items():
        if re.search(r"(?<![\w'])" + re.escape(found) + r"(?![\w'])", text, re.IGNORECASE):
            issues.append(GuidelineIssue("standard-spelling", f"Use {preferred} instead of {found}."))

    if text.rstrip().endswith("-"):
        # This is valid for a false start, but deserves a reminder because a
        # trailing dash can also mean the recording ended mid-word.
        issues.append(GuidelineIssue("review-trailing-dash", "Confirm the trailing hyphen is a spoken fragment or an abrupt cut-off."))
    if speaker and not re.match(r"^Speaker\s+\w+$", speaker.strip(), re.IGNORECASE):
        issues.append(GuidelineIssue("speaker-label", "Use a consistent label such as Speaker 1 or Speaker 2."))
    return issues


def validate_segments(segments: list[dict]) -> dict[str, object]:
    """Validate editor segments and return a compact page-safe summary."""

    by_segment = []
    speakers: list[str] = []
    for segment in segments:
        speaker = str(segment.get("speaker") or "Speaker 1")
        if speaker not in speakers:
            speakers.append(speaker)
        issues = validate_transcript(str(segment.get("text") or ""), speaker=speaker)
        by_segment.append({"id": segment.get("id"), "issues": [issue.as_dict() for issue in issues]})
    return {
        "segmentIssues": by_segment,
        "speakerCount": len(speakers),
        "hasErrors": any(item["issues"] for item in by_segment),
        "standard": "Spontaneous Speech Data Annotations",
    }
