"""Clinical extraction mode for beeplex.

Scenario: a doctor wears the Bee during patient encounters. The point is
not to score how the conversation *felt* (see bee_fetcher.engagement_signals)
but to pull out what the doctor actually needs: the reason for the visit,
what changed, what the patient is worried about, and what was ordered.
Two or three bullets that get fed forward - never a rubric, never a row in
a database nobody reads.

Two layers, same philosophy as the engagement pipeline:
  deterministic - always runs, nothing leaves the machine. Heuristic
      speaker-role detection (doctor vs patient), symptom spotting with
      onset / change / severity markers, patient questions, and plan items
      (prescriptions, referrals, tests, follow-ups).
  LLM (optional) - Gemini first, then Bedrock Nova, reusing the
      llm_scoring provider chain. Returns structured clinical JSON plus a
      two-to-three sentence handoff the doctor can read in ten seconds.

Privacy: deterministic mode sends nothing anywhere. The LLM pass sends
transcript text to the configured provider - the same tradeoff as
llm_scoring. Summaries land in family/, which is gitignored: never commit
real patient transcripts.

This is a hackathon demo aid, not a medical device. Deterministic output
is heuristic and the LLM can misread - review every summary before filing.
"""

import json
import re
from datetime import date
from pathlib import Path

from docx import Document

from bee_fetcher import _is_substantive
from llm_scoring import (
    API_KEY,
    _bedrock_post,
    _gemini_post,
    _transcript_text,
    available as llm_available,
)

# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------

# Visit-shaped language. The doctor asks the clinical questions and issues
# the orders; the patient describes what they feel and what worries them.
DOCTOR_CUES = [
    r"what brings you in",
    r"how can i help",
    r"how long has",
    r"how long have",
    r"when did (this|it|that) start",
    r"have you (had|been|noticed|tried)",
    r"are you taking",
    r"any (pain|swelling|fever|nausea|dizziness|bleeding|numbness)",
    r"does it hurt when",
    r"on a scale of",
    r"i('m| am) going to (prescribe|order|refer|send you)",
    r"i('d| will) like to (order|refer|prescribe)",
    r"let's (get|run|order|check|schedule|try)",
    r"we('ll| will) (run|order|schedule|get)",
    r"come back (in|if|when)",
    r"follow up",
    r"see you in",
]

PATIENT_CUES = [
    r"\bi (feel|felt|have|had|notice|noticed|get|got)\b",
    r"\bit hurts\b",
    r"\bmy \w+ (hurts?|aches?|is sore|is swollen)\b",
    r"\bi('m| am) worried\b",
    r"\bcould this be\b",
    r"\bdo i (need|have to)\b",
]

SYMPTOM_WORDS = [
    "pain", "ache", "aching", "sore", "hurt", "hurts", "tender",
    "nausea", "nauseous", "vomit", "vomiting",
    "dizzy", "dizziness", "lightheaded",
    "fever", "chills", "cough", "headache", "migraine",
    "fatigue", "tired", "exhausted", "weakness",
    "swelling", "swollen", "swell", "rash", "itch", "itchy",
    "numb", "numbness", "tingling", "cramp", "cramps",
    "shortness of breath", "wheezing", "chest", "palpitations",
    "bleeding", "bruise", "bruising", "stiff", "stiffness",
    # common inflections the \b...\b whole-word match would otherwise miss
    "swelled", "aches", "hurting",
]

_ONSET = re.compile(
    r"\bfor (?:about |around )?(\w+(?: \w+)?) "
    r"(days?|weeks?|months?|hours?|years?)\b"
    r"|\bsince (\w+)\b"
    r"|\bstarted\b",
    re.IGNORECASE,
)
_CHANGE = re.compile(
    r"\b(worse|worsening|better|improving|improved|spreading|spread|"
    r"new|gone away|resolved|came back|returned|flare[\s-]?ups?)\b",
    re.IGNORECASE,
)
_SEVERITY = re.compile(
    r"\b(\d{1,2})\s*(?:/|out of)\s*10\b"
    r"|\b(severe|mild|moderate|unbearable|excruciating)\b",
    re.IGNORECASE,
)
_PLAN = re.compile(
    r"\b(prescrib\w*|prescription|refer(?:ral)?|blood ?work|blood tests?|"
    r"labs?|metabolic panel|x-?ray|mri|ultrasound|scan|follow.?up|"
    r"come back|appointment|schedul\w+|physio(?:therapy)?|surgery|"
    r"\d+\s*mg\b|ibuprofen|antibiotics?)\b",
    re.IGNORECASE,
)

# Medication mentions: "lisinopril 20 mg", "amlodipine 5 mg". Doses may be
# written as words ("twenty milligrams") in transcripts, so normalize the
# common ones before matching.
_NUMWORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50",
}
_NUMWORDS_RE = re.compile(
    r"\b(" + "|".join(_NUMWORDS) + r")\s+(milligrams?|mg)\b", re.IGNORECASE)

_MED_DOSE = re.compile(
    r"\b([A-Za-z][A-Za-z\-]{2,})\s+(\d+(?:\.\d+)?)\s*mg\b", re.IGNORECASE)
_ORPHAN_DOSE = re.compile(r"\b(\d+(?:\.\d+)?)\s*mg\b", re.IGNORECASE)
# Words that are never a drug name when scanning backwards from a dose.
_MED_STOPWORDS = {
    "to", "the", "a", "an", "of", "back", "dose", "doses", "daily",
    "your", "you", "that", "this", "with", "for", "and", "then", "my",
}
_MED_KNOWN = re.compile(
    r"\b(ibuprofen|acetaminophen|tylenol|aspirin|antibiotics?)\b",
    re.IGNORECASE)
_MED_CHANGE = re.compile(
    r"\b(raise[sd]?|increase[sd]?|increasing|lower[sd]?|decrease[sd]?|"
    r"decreasing|drop(?:ped|ping)?|start(?:ed|ing)?|add(?:ed|ing)?|"
    r"stop(?:ped|ping)?|continue[sd]?|continuing|keep taking)\b",
    re.IGNORECASE,
)
_MED_CHANGE_MAP = {
    "raise": "increased", "raised": "increased", "increase": "increased",
    "increased": "increased", "increasing": "increased",
    "lower": "decreased", "lowered": "decreased", "decrease": "decreased",
    "decreased": "decreased", "decreasing": "decreased",
    "drop": "decreased", "dropped": "decreased", "dropping": "decreased",
    "start": "started", "started": "started", "starting": "started",
    "add": "started", "added": "started", "adding": "started",
    "stop": "stopped", "stopped": "stopped", "stopping": "stopped",
    "continue": "continued", "continues": "continued", "continued": "continued",
    "continuing": "continued", "keep taking": "continued",
}
_MED_FREQ = re.compile(
    r"\b(daily|every morning|every evening|twice a day|at bedtime|"
    r"as needed|now and then|with breakfast|with food)\b",
    re.IGNORECASE,
)

_FOLLOWUP = re.compile(
    r"\b(?:come back|have you back|see you|follow.?up|return)\s+"
    r"(?:back\s+)?in\s+"
    r"((?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:days?|weeks?|months?))\b",
    re.IGNORECASE,
)


def _normalize_dose_words(text):
    return _NUMWORDS_RE.sub(
        lambda m: f"{_NUMWORDS[m.group(1).lower()]} mg", text)


def detect_roles(parts):
    """Guess {speaker: 'doctor'|'patient'} from visit-shaped language.

    The speaker with the strongest doctor-cue signal wins; everyone else is
    the patient. Returns {} when there is no usable signal (fewer than two
    speakers, or nobody sounds like either role) - extraction still runs,
    just without role attribution.
    """
    speakers = [s for s, _ in parts if s]
    uniq = list(dict.fromkeys(speakers))
    if len(uniq) < 2:
        return {}
    score = {sp: 0.0 for sp in uniq}
    for sp in uniq:
        turns = [t for s, t in parts if s == sp]
        for t in turns:
            for pat in DOCTOR_CUES:
                if re.search(pat, t, re.IGNORECASE):
                    score[sp] += 2.0
            for pat in PATIENT_CUES:
                if re.search(pat, t, re.IGNORECASE):
                    score[sp] -= 2.0
            if t.rstrip().endswith("?"):
                score[sp] += 0.5  # in a visit, the questioner is usually the doctor
    best = max(uniq, key=lambda sp: score[sp])
    if score[best] <= 0:
        return {}
    return {sp: ("doctor" if sp == best else "patient") for sp in uniq}


def _symptom_hits(text):
    low = text.lower()
    return [
        w for w in SYMPTOM_WORDS
        if re.search(r"\b" + re.escape(w) + r"\b", low)
    ]


def _trim(text, n=140):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def extract_medications(substantive):
    """Heuristic medication mentions: [{name, dose, frequency, change}].

    One entry per drug (last mention wins for dose); ``change`` is one of
    increased/decreased/started/stopped/continued when a change verb is
    nearby, else None. Deterministic and conservative - brand/generic
    coverage is deliberately narrow; the LLM pass refines when enabled.
    """
    meds = {}

    def note(name, dose=None, freq=None, change=None):
        key = name.lower()
        entry = meds.setdefault(key, {"name": name.lower()})
        if dose:
            entry["dose"] = dose
        if freq and "frequency" not in entry:
            entry["frequency"] = freq
        if change:
            entry["change"] = change
        return entry

    def change_before(name_start):
        # Change verbs precede the drug ("raised the lisinopril", "add
        # amlodipine") - a verb after the mention belongs to another drug.
        cm = _MED_CHANGE.search(text[max(0, name_start - 40): name_start])
        return _MED_CHANGE_MAP.get(cm.group(1).lower()) if cm else None

    for _, t in substantive:
        text = _normalize_dose_words(t)
        direct_spans = []
        for m in _MED_DOSE.finditer(text):
            direct_spans.append(m.span())
            name, dose = m.group(1), f"{m.group(2)} mg"
            window = text[max(0, m.start() - 40): m.end() + 40]
            fm = _MED_FREQ.search(window)
            note(name, dose, fm.group(1).lower() if fm else None,
                 change_before(m.start(1)))
        for m in _ORPHAN_DOSE.finditer(text):
            # "raised the lisinopril to 20 mg" - the name rides ahead of the
            # dose with small words between. Scan backwards past stopwords.
            if any(s <= m.start() < e for s, e in direct_spans):
                continue
            base = max(0, m.start() - 50)
            before = text[base: m.start()]
            known = _MED_KNOWN.search(before)
            if known:
                name, name_start = known.group(1), base + known.start()
            else:
                words = [w for w in
                         re.findall(r"[A-Za-z\-]{4,}", before)
                         if w.lower() not in _MED_STOPWORDS]
                if not words:
                    continue
                name = words[-1]
                name_start = base + before.lower().rfind(name.lower())
            dose = f"{m.group(1)} mg"
            fm = _MED_FREQ.search(text[max(0, m.start() - 40): m.end() + 40])
            note(name, dose, fm.group(1).lower() if fm else None,
                 change_before(name_start))
        for m in _MED_KNOWN.finditer(text):
            name = m.group(1).lower()
            if any(k == name for k in meds):
                continue
            fm = _MED_FREQ.search(text)
            note(name, None, fm.group(1).lower() if fm else None, None)
    return list(meds.values())


def extract_followup(substantive, roles):
    """First 'see you back in N weeks'-style timeframe, normalized to digits."""
    for s, t in substantive:
        if roles and roles.get(s) != "doctor":
            continue
        m = _FOLLOWUP.search(_normalize_dose_words(t))
        if m:
            when = m.group(1).lower()
            when = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b",
                          lambda mm: _NUMWORDS[mm.group(1)], when)
            return when
    return None


def _dedupe_words(words):
    """Drop near-duplicate symptom words sharing a 4-letter stem."""
    kept = []
    for w in words:
        if not any(w[:4] == k[:4] for k in kept):
            kept.append(w)
    return kept


def _render_med(m):
    bits = " ".join(x for x in (m.get("name"), m.get("dose"),
                                m.get("frequency")) if x)
    if m.get("change"):
        bits += f" ({m['change']})"
    return bits


def extract_clinical(parts):
    """Deterministic clinical extraction from [(speaker, text)].

    Returns {"roles", "chief_complaint", "symptoms", "medications",
    "follow_up", "patient_concerns", "plan", "handoff"}. ``handoff`` is
    three short bullets - the whole point of this mode: the two or three
    things worth feeding forward.
    """
    substantive = [(s, t) for s, t in parts if _is_substantive(t)]
    roles = detect_roles(parts)

    def is_patient(s):
        return roles.get(s, "patient") == "patient"

    def is_doctor(s):
        return roles.get(s) == "doctor"

    symptoms = []
    for s, t in substantive:
        # When roles are known, symptoms come from the patient: the doctor's
        # screening questions ("any swelling?") are not reported symptoms.
        if roles and not is_patient(s):
            continue
        hits = _symptom_hits(t)
        change = _CHANGE.search(t)
        if not hits:
            # Change marker without a named symptom ("definitely worse after
            # my shifts") belongs to the most recent symptom entry.
            if change and symptoms and not symptoms[-1]["change"]:
                symptoms[-1]["change"] = change.group(1)
            continue
        onset = _ONSET.search(t)
        severity = _SEVERITY.search(t)
        symptoms.append({
            "text": _trim(t),
            "symptoms": hits,
            "onset": onset.group(0) if onset else None,
            "change": change.group(1) if change else None,
            "severity": severity.group(0) if severity else None,
        })
    symptoms = symptoms[:8]

    patient_turns = [t for s, t in substantive if is_patient(s)]
    complaint_src = (
        next((t for t in patient_turns if _symptom_hits(t)), None)
        or next(iter(patient_turns), "")
    )
    chief_complaint = _trim(complaint_src, 160)

    patient_concerns = [
        _trim(t) for s, t in substantive
        if is_patient(s) and t.rstrip().endswith("?")
    ][:5]

    plan = []
    for s, t in substantive:
        # Questions are not orders: "you're here for the follow-up?" would
        # otherwise land in the plan via the follow-up keyword.
        if t.rstrip().endswith("?"):
            continue
        if _PLAN.search(t) and (is_doctor(s) or not roles):
            plan.append(_trim(t))
    # de-dupe while keeping order
    plan = list(dict.fromkeys(plan))[:6]

    medications = extract_medications(substantive)
    follow_up = extract_followup(substantive, roles)

    # The handoff: three bullets, nothing more.
    handoff = [
        f"Reason for visit: {chief_complaint or 'not clearly stated'}",
    ]
    changed = [s for s in symptoms if s["change"]]
    if changed:
        words = _dedupe_words(
            w for s in changed[:3] for w in s["symptoms"])
        handoff.append("Changes: " + "; ".join(
            f"{', '.join(w for w in s['symptoms'] if w in words)}"
            f" ({s['change']})"
            for s in changed[:3]
            if any(w in words for w in s["symptoms"])))
    elif symptoms:
        words = _dedupe_words(
            w for s in symptoms[:3] for w in s["symptoms"])
        handoff.append("Reported: " + "; ".join(words))
    else:
        handoff.append("No symptoms detected in transcript")
    tail = []
    if patient_concerns:
        tail.append("Patient asked: " + " / ".join(patient_concerns[:2]))
    if plan:
        tail.append("Next steps: " + " / ".join(plan[:2]))
    if medications:
        tail.append("Meds: " + "; ".join(
            _render_med(m) for m in medications[:4]))
    if follow_up:
        tail.append(f"Follow-up: in {follow_up}")
    handoff.append(" | ".join(tail) if tail else "No open questions or orders detected")

    # Sparse transcript: the patient spoke, but only in a few words per turn,
    # and the extractor found nothing to report. Per the design note above,
    # this is not a clean bill of health - it usually means the verbal
    # channel failed and the real concern never made it into words.
    patient_turns = [t for s, t in parts if is_patient(s) and t.strip()]
    avg_words = (sum(len(t.split()) for t in patient_turns) / len(patient_turns)
                 if patient_turns else 0)
    sparse_transcript = bool(
        patient_turns
        and avg_words < 6
        and not symptoms
        and not medications
        and not patient_concerns
        and not plan
    )

    return {
        "roles": roles,
        "chief_complaint": chief_complaint,
        "symptoms": symptoms,
        "medications": medications,
        "follow_up": follow_up,
        "patient_concerns": patient_concerns,
        "plan": plan,
        "handoff": handoff,
        "sparse_transcript": sparse_transcript,
    }

# ---------------------------------------------------------------------------
# Optional LLM pass (Gemini -> Bedrock Nova, same chain as llm_scoring)
# ---------------------------------------------------------------------------

CLINICAL_PROMPT = """You are a clinical documentation assistant. Below is a transcript of a doctor-patient encounter recorded on a doctor-worn wearable with the patient's consent.

Extract ONLY what the doctor needs for the chart. Reply with ONLY a JSON object, no other text:
{"chief_complaint": "...", "symptoms": [{"description": "...", "onset": "...", "change": "..."}], "medications": [{"name": "...", "dose": "...", "change": "increased/decreased/started/stopped/continued or null"}], "follow_up": "e.g. 4 weeks or null", "patient_concerns": ["..."], "plan": ["..."], "handoff": "Two or three plain sentences the doctor can read in ten seconds before the next patient."}
Do not invent facts not present in the transcript; use null for anything unknown.

Transcript:
{transcript}"""


def _strip_fences(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip() or None


def _parse_clinical(text, items):
    """Parse one provider's raw reply into {key: clinical dict}. {} on failure."""
    text = _strip_fences(text)
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
        results[key] = {
            "chief_complaint": entry.get("chief_complaint"),
            "symptoms": entry.get("symptoms") or [],
            "medications": entry.get("medications") or [],
            "follow_up": entry.get("follow_up"),
            "patient_concerns": entry.get("patient_concerns") or [],
            "plan": entry.get("plan") or [],
            "handoff": entry.get("handoff"),
        }
    return results


def clinical_batch(items):
    """Extract clinical facts from many encounters with a SINGLE LLM call.

    ``items`` is [(key, parts)] with ``parts`` as [(speaker, text)].
    Returns {key: {"chief_complaint", "symptoms", "medications", "follow_up",
    "patient_concerns", "plan", "handoff"}}. Keys the provider fumbles are omitted, so callers
    fall back to the deterministic extraction for those encounters.

    Provider chain mirrors llm_scoring: Gemini first when a key is set,
    then Bedrock Nova via boto3. No provider -> {} and the deterministic
    layer stands alone. Enabling this sends transcript text to the
    configured provider.
    """
    items = [(key, parts) for key, parts in items if parts]
    if not items:
        return {}
    blocks = "\n\n".join(
        f"### Encounter {key}\n{_transcript_text(parts)}" for key, parts in items
    )
    prompt = CLINICAL_PROMPT.replace("{transcript}", blocks)
    results = {}
    if API_KEY:
        results = _parse_clinical(_gemini_post(prompt, 2048), items)
    if not results:
        results = _parse_clinical(_bedrock_post(prompt, 2048), items)
    return results


# ---------------------------------------------------------------------------
# One-page encounter summary (the deliverable)
# ---------------------------------------------------------------------------

# Design note (2026-09-21): "None detected" is not a clean bill of health.
# The extractor only reports what it can positively find, so an empty section
# means *absence of evidence*, never *evidence of absence*. A terse patient
# ("nothing", "same") often IS the signal - the worry the tool couldn't hear.
# Never let empty output read like an all-clear; prefer an explicit
# sparse-transcript flag over a quiet "None detected."
def write_clinical_docx(path, title, rec_date, det, llm):
    """Write the one-page clinical encounter summary.

    ``det`` is extract_clinical() output; ``llm`` is the clinical_batch()
    entry for this encounter (or None). The LLM handoff replaces the
    deterministic bullets when present; the structured sections stay
    deterministic so there is always a no-LLM paper trail.
    """
    doc = Document()
    doc.core_properties.title = f"Clinical Encounter Summary - {title}"
    doc.add_heading("Clinical Encounter Summary", 0)
    doc.add_paragraph(f"{title}  •  {rec_date}")
    doc.add_paragraph(
        "Recorded on a doctor-worn Bee (patient encounter). "
        "Heuristic extraction - review before filing."
    )

    doc.add_heading("Handoff - read first", 1)
    handoff = (llm or {}).get("handoff") or det["handoff"]
    if isinstance(handoff, str):
        doc.add_paragraph(handoff)
    else:
        for bullet in handoff:
            doc.add_paragraph(bullet, style="List Bullet")

    doc.add_heading("Reason for visit", 1)
    doc.add_paragraph(det["chief_complaint"] or "Not clearly stated.")

    doc.add_heading("Symptoms", 1)
    if det["symptoms"]:
        for s in det["symptoms"]:
            bits = ", ".join(s["symptoms"])
            extras = " / ".join(
                x for x in (s["onset"], s["change"], s["severity"]) if x
            )
            line = f"{bits}" + (f" - {extras}" if extras else "")
            p = doc.add_paragraph(line, style="List Bullet")
            p.add_run(f"\n\"{s['text']}\"")
    else:
        doc.add_paragraph("None detected.")

    doc.add_heading("Patient concerns", 1)
    if det["patient_concerns"]:
        for q in det["patient_concerns"]:
            doc.add_paragraph(q, style="List Bullet")
    else:
        doc.add_paragraph("None detected.")

    if det["medications"]:
        doc.add_heading("Medications mentioned", 1)
        for m in det["medications"]:
            doc.add_paragraph(_render_med(m), style="List Bullet")

    doc.add_heading("Plan / follow-ups", 1)
    if det.get("follow_up"):
        doc.add_paragraph(f"Follow-up: in {det['follow_up']}")
    if det["plan"]:
        for item in det["plan"]:
            doc.add_paragraph(item, style="List Bullet")
    elif not det.get("follow_up"):
        doc.add_paragraph("None detected.")

    doc.add_heading("Recommendation", 1)
    if det.get("sparse_transcript"):
        doc.add_paragraph(
            "The patient had difficulty describing their concern verbally. "
            "Ask them to show you \u2014 photos, the symptom itself, whatever they have."
        )
    else:
        doc.add_paragraph(
            "Review this summary with the patient and confirm nothing was "
            "missed before filing."
        )

    doc.add_paragraph(
        "Privacy: deterministic extraction never leaves this machine. "
        "LLM enrichment sends transcript text to the configured provider."
    )
    doc.save(path)


# ---------------------------------------------------------------------------
# Fetch + run
# ---------------------------------------------------------------------------

def fetch_encounters(limit=10):
    """Pull raw encounter transcripts via the Bee CLI.

    Returns (encounters, info); each encounter is {"id", "title", "date",
    "parts", "events"}. Unlike fetch_report_data this never scores and
    never touches the coaching dashboard - clinical mode is extraction
    only. Empty when the CLI is missing/unauthenticated (use the simulator
    to demo without hardware).
    """
    from bee_fetcher import (
        MOCK_FORCED,
        BEE_CMD,
        cli_available,
        is_authenticated,
        list_conversations,
        _conv_id,
        _recording_date,
        _resolve_source,
    )

    if MOCK_FORCED or not cli_available() or not is_authenticated():
        return [], {
            "mode": "unavailable",
            "detail": (
                f"'{BEE_CMD}' not ready - clinical mode needs transcripts; "
                "run with the simulator on PATH to demo without hardware"
            ),
        }
    encounters = []
    for conv in list_conversations(limit=limit):
        conv_id = _conv_id(conv)
        source, parts, events = _resolve_source(conv)
        if not parts:
            continue
        title = (
            source.get("title")
            or source.get("summary")
            or (f"Encounter {conv_id}" if conv_id is not None else "Encounter")
        )
        encounters.append({
            "id": conv_id,
            "title": str(title)[:80],
            "date": _recording_date(source),
            "parts": parts,
            "events": events,
        })
    return encounters, {"mode": "live",
                        "detail": f"{len(encounters)} encounters via Bee CLI"}


def run_clinical(limit=10, out_dir=None):
    """Run clinical mode: extract + write one summary docx per encounter."""
    out_dir = Path(out_dir or Path(__file__).resolve().parent / "family")
    out_dir.mkdir(parents=True, exist_ok=True)

    encounters, info = fetch_encounters(limit)
    if not encounters:
        print(f"Clinical mode: {info['detail']}.")
        return []

    llm_map = (clinical_batch([(str(e["id"]), e["parts"]) for e in encounters])
               if llm_available() else {})
    if llm_map:
        print("LLM enrichment: on (handoff refined by provider)")
    else:
        print("LLM enrichment: off (deterministic only - nothing leaves this machine)")

    saved = []
    for e in encounters:
        det = extract_clinical(e["parts"])
        llm = llm_map.get(str(e["id"]))
        slug = re.sub(r"\W+", "_", e["title"]).strip("_")[:40] or "encounter"
        day = e["date"] or date.today()
        fname = f"Clinical_Summary_{day}_{slug}.docx"
        write_clinical_docx(out_dir / fname, e["title"], day, det, llm)
        saved.append(fname)
        print(f"\n=== {e['title']} ({day}) ===")
        handoff = [llm["handoff"]] if llm and llm.get("handoff") else det["handoff"]
        for bullet in handoff:
            print(f"  - {bullet}")
        print(f"  Saved: {fname}")
    return saved


if __name__ == "__main__":
    run_clinical()
