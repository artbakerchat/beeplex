# BeePlex — Quick Bees

1. Prerequisites

Python 3.12, git
Bee CLI installed (for live data — without it everything still runs on mock/sim data)
Optional: a GEMINI_API_KEY for LLM scoring; AWS credentials for the my-agent conversational agent

2. Clone and set up

git clone https://github.com/artbakerchat/beeplex.git
cd beeplex/my-agent
./setup.sh — creates the shared .venv, installs all dependencies (report libs + agent libs), checks the Bee CLI and AWS creds

3. Try it with no hardware (simulator)

cd beeplex → ./simulator/run.sh
Exercises the real pipeline on 9 scripted scenarios: fetch → score → reports
Outputs land in family/: Word/Excel/PowerPoint reports + dashboard.html (coaching dashboard)

4. Go live with your Bee

bee login
my-agent/.venv/bin/python family.py — pulls today's real conversations, scores them, writes fresh reports and refreshes the dashboard

5. Add the LLM layer (optional)

Put GEMINI_API_KEY=... in a .env file next to family.py
Next family.py run: Gemini scores engagement/meaning and writes the one-sentence memory per conversation (Bedrock Nova is the automatic fallback)

6. Meet Bee

my-agent/.venv/bin/python bee_fetcher.py --persona — prints tonight's diary entry and saves family/Bee_YYYY-MM-DD.md
The persona deepens with every family.py run (history + moments accumulate)

7. Use the copilot (my-agent)

Web console, no AWS needed: cd my-agent → streamlit run ui/app.py — tabs for Conversations, Scores, Report, Diary, Picker
Conversational agent: agentcore dev (needs AWS creds, Nova Micro in ca-central-1) — ask "How engaging were my conversations today?" or "What did Bee write about today?"

8. Clinical mode (separate track)

my-agent/.venv/bin/python bee_fetcher.py --clinical — doctor-visit summaries. Deliberately not wired into my-agent.

## Bee CLI integration

`bee_fetcher.py` pulls real conversation data through the official Bee CLI:

1. Install: `npm install -g @beeai/cli`
2. Unlock Developer Mode in the Bee iOS app (tap app Version 5 times)
3. Authenticate: `bee login` (or `bee login --no-wait` for agents)
4. Run: `python family.py`

`family.py` fetches the 10 most recent conversations (`bee conversations list`
+ `bee conversations get`, all `--json`), maps them onto the report schema,
and uses each transcript's actual Bee recording date in the report titles and
filenames. If the CLI is missing or not logged in, it falls back to
clearly-labelled `[MOCK]` sample data so the reports still build.

Env vars: `BEEX_MOCK=1` forces mock mode; `BEE_CLI` overrides the `bee`
binary path.

## LLM layer (optional)

`llm_scoring.py` scores all of a run's transcripts in a single LLM call:
a second-opinion engagement score plus a one-line rationale per
conversation, averaged with the deterministic score — and a
tone/positivity rating (`Warm (8/10)`), which can't be done
deterministically. Two providers, one shared prompt: Gemini is tried first
— set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`); `GEMINI_MODEL` overrides the
model (default `gemini-3.5-flash`). You can put the key in a `.env` file
next to `family.py` (`GEMINI_API_KEY=...`) instead of exporting it — it's
gitignored, so it never reaches the repo. If Gemini is missing or its call
fails, AWS Bedrock Nova is tried next via boto3 with your local AWS
credentials (region defaults to `ca-central-1`, override with
`BEDROCK_REGION`/`AWS_REGION`; model defaults to `us.amazon.nova-lite-v1:0`
— Nova isn't served in-region in Canada, so this is the US cross-region
inference profile AWS documents for ca-central-1; override with
`BEDROCK_MODEL`). With no working provider — or if the API
fails — the deterministic score stands alone and the
pipeline never breaks. Note: enabling this sends your transcript text to
Google's and/or Amazon's API; keys live only in your environment or `.env`,
never in the repo.

## Temporal dynamics (third scoring domain)

`temporal_scoring.py` reads how a conversation *moves* through time, from
the per-utterance timestamps Bee provides — no API calls, no key:

- **pace**: words per minute per turn vs a ~150 wpm conversational norm
- **responsiveness**: reply latency *relative to the turn being answered*
  (a 3-second gap after a 25-word turn is an instant reply; after "yeah"
  it's just a pause — the 20+ word "substantial turn" bar doubles as the
  timing hint)
- **circularity**: 3–4 word phrases repeated 2x+ inside 20+ word turns
  (the "one thought on loop" detector; also discounts those turns'
  contribution to the deterministic depth signal)
- **novelty**: share of each turn's phrases never seen before in the
  conversation (restating vs advancing)
- **spinning**: structural signs of going in circles — questions answered
  with questions, absolutist language ("you always/never", "exact same"),
  circling rhetoric ("as I said", "don't even start", "for a change").
  Reads the *shape* of the exchange, not its meaning: an argument that
  restates one fight in fresh words scores novelty ~1.0 while going
  nowhere, and spinning is the signal that catches it

Repetition is not automatically treated as failure. The scorer also looks
for productive-progress markers such as explanations, examples, contrasts,
and conclusions, which soften the spinning penalty. This helps music and
sports discussions where revisiting a subject can still add analysis.

Pace + responsiveness form temporal **energy**, blended into Engagement as
a third domain alongside the deterministic and LLM scores (mean of
whichever domains are available). Circularity + novelty form lexical
motion, which spinning discounts multiplicatively — forward motion is
10 × motion × (1 − spin penalty). On the sim scenarios the heated argument
scores FM Moderate (6.8, spinning 0.51) while the product debate scores
High (9.8, spinning 0.0): same heat, honestly different progress. The LLM
also rates progress 1–10 ("Spinning"…"Advancing") and blends with the
deterministic score; pure paraphrase-level restating — same point, fresh
words, no circling rhetoric — can't be caught without semantics, so that
last part is the LLM's half. The dashboard says so explicitly when no key
is set: without the semantic domain, forward motion is labeled a
structural read.

## Coaching dashboard (auto-generated)

Every run also writes `family/dashboard.html` — a local coaching dashboard
that opens in your browser. No data leaves your machine. It shows:

- **This run, ranked** — your conversations ordered by engagement, each
  with the one-line reason it sits where it does, plus a trend arrow
  (▲/▼/—) against its previous runs
- **Coaching cards** — per conversation: the three domain scores and every
  sub-signal as a bar, plain-language tips derived from the signals
  ("One voice is doing 80% of the talking — draw the other person out
  with a direct question", "Looping detected — 'as I was saying' (3×).
  Say it once and move on."), a trend sparkline, and the LLM's one-line
  rationale when a key is set
- **Weight lab** — sliders that re-blend the three domains live, so you
  can feel how the engagement score is built (equal weights reproduce the
  report scores; uncheck the LLM box to see the no-key blend)

**Trend history:** each live run appends its per-conversation scores to
`family/history.json` — scores and signal values only, never transcripts
(capped at 200 runs; delete the file to start fresh). Mock runs regenerate
the page from history without appending. The tips are deterministic and
free — the same signals that built the score say how to move it.

## Clinical mode (doctor-worn Bee)

A second mode for a different job: the doctor wears the Bee during patient
encounters, and instead of scoring how the conversation *felt*, the tool
extracts what the doctor needs — reason for visit, what changed, what the
patient is worried about, what was ordered. Two or three handoff bullets,
not a rubric.

    python3 bee_fetcher.py --clinical

`clinical_extraction.py` runs a deterministic pass over each transcript
(heuristic doctor/patient role detection, symptom spotting with
onset/change/severity markers, medication mentions with dose and change
verbs, follow-up timeframes, patient questions, plan items like
prescriptions, referrals, tests, follow-ups) and writes a one-page
**Clinical Encounter Summary** (`.docx`) per conversation into `family/`.
With an LLM configured, the same Gemini → Bedrock Nova chain used by
`llm_scoring.py` refines the handoff into two or three plain sentences —
one API call for the whole run. Without it, the deterministic layer stands
alone and nothing leaves the machine.

Try it without hardware — the simulator ships two scripted visits:
`sim_doctor_visit` (a knee-pain workup) and `sim_followup_visit` (a blood
pressure medication review with a dose change):

    PATH="simulator:$PATH" python3 bee_fetcher.py --clinical

Privacy: deterministic mode sends nothing anywhere. The LLM pass sends
transcript text to the configured provider. Summaries land in `family/`,
which is gitignored — never commit real patient transcripts. This is a
hackathon demo aid, not a medical device: review every summary before
filing.

## Persona mode (Bee's diary)

The third pillar. Scoring reads *how* people talk, clinical reads *what*
was said — persona is *who was listening*. Bee has no default
personality; it grows one from what it hears. `bee_persona.py` derives
Bee's character as a pure function of the listening history
(`family/history.json`): a Bee raised on dinner-table debates is wry and
steady, one raised on quiet evenings is gentle and comfortable with
silence, and a brand-new Bee is curious and tentative. The longer it
listens, the more defined it becomes.

    python3 bee_fetcher.py --persona

writes tonight's first-person diary entry to `family/Bee_YYYY-MM-DD.md`.
With an LLM configured, the same Gemini → Bedrock Nova provider chain
writes the entry in Bee's voice; without one, deterministic templates
carry it. Reading mode — it never appends to the history.

Scores alone give Bee the *shape* of your days, so every live run also
records one remembered line per conversation in `family/moments.json` —
the phrase it kept circling, or a fragment of what was actually said.
When an LLM is configured, the same single batch call that scores the
run also writes a one-sentence semantic memory of what each conversation
was *about* — that wins over the deterministic note, at zero extra API
cost. Never a transcript, just enough for Bee to remember *about* your days
rather than only their rhythms. Pocketed keepsakes and the diary entry
both draw on it. Local and gitignored like everything in `family/`.

The standing rules of the voice: witness, not participant (loyal,
observant, never judgmental); collects moments the way bees collect
pollen; never nags, never therapy-speak; and honest about not knowing —
it hears words, not faces, so "you went quiet, I don't know why" beats
an invented reason.

## Simulator (no device needed)

`simulator/` is a fake `bee` CLI so you can test the real live path without
hardware or a login. It emulates `bee me`, `conversations list/get/transcript`
with scripted conversations (`simulator/conversations.json`) shaped like the
documented Bee payloads — verbatim utterances with speaker and timestamps.

Run the whole pipeline against it:

    ./simulator/run.sh

That's `./simulator/run.sh` = `PATH="simulator:$PATH" python family.py` — the
fetcher sees a `bee` binary, authenticates, and runs in live mode against the
seven scripted scenarios (heated argument, balanced debate, monologue,
backchannel ping-pong, short Q&A, unlabeled transcript, doctor-patient
visit). Add your own
scenarios to `conversations.json` (timestamps are relative `minutes_ago`, so
dates stay fresh). Each utterance accepts an optional `pause_s` — seconds of
silence after it before the next turn — so a scenario can script its rhythm
(rapid-fire argument: 1.5, thoughtful debate: 4, slow monologue: 8); the
fake CLI spaces utterance timestamps by estimated speech time plus the
pause, like real Bee captures. `SIM_BEE_FAIL_AUTH=1` simulates a logged-out CLI (tests the
mock fallback); `SIM_BEE_EMPTY=1` returns zero conversations.

## Scoring test harness

`bench.py` benchmarks candidate engagement formulas against the same fixed
fixtures, so a new formula is judged on the simulator scenarios instead of
gut feel. One command runs everything:

    python3 bench.py

It reads `simulator/conversations.json` read-only and prints a
scenario-by-formula score table plus a "where the baseline misses" summary.
Ships with the naive utterance-count heuristic as the baseline anchor and
three seed alternates (talk balance, question rate, turn length). Register a
new formula with a few lines at the bottom of `bench.py`:

    def my_formula(utterances):
        ...
        return score  # 0..10

    register("my_formula", my_formula)

### Recording from your microphone

`simulator/record.py` simulates what the Bee device itself does — capture
audio, transcribe it, split it into speaker turns — so you can test scoring
on your own voice:

    pip install sounddevice faster-whisper numpy
    python3 simulator/record.py --title "Lunch with Sam" --seconds 60

It records, transcribes locally with Whisper, appends the result as a new
scenario in `conversations.json`, and prints its engagement score. Then
`./simulator/run.sh` shows it in the full reports. Ctrl+C stops early.
Everything is local; the wav is deleted after transcription unless you pass
`--keep-wav` (kept files land in `simulator/recordings/`, git-ignored).
By default everyone is one speaker ("You"); for real two-speaker
diarization, `pip install pyannote.audio` and set `HF_TOKEN`.

**Chunked mode** — `--chunk 15` records in 15-second chunks: chunk N is
transcribed (and its wav deleted) while chunk N+1 records, so only one
chunk of audio ever sits on disk. Without `--chunk`, the whole recording
is captured first, then transcribed.
