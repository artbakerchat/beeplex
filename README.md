# BeePlex — Bee wearable transcript reports

Generates Word (action log), Excel (metrics), and PowerPoint (insights) reports
from your Bee wearable conversations.

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

## Simulator (no device needed)

`simulator/` is a fake `bee` CLI so you can test the real live path without
hardware or a login. It emulates `bee me`, `conversations list/get/transcript`
with scripted conversations (`simulator/conversations.json`) shaped like the
documented Bee payloads — verbatim utterances with speaker and timestamps.

Run the whole pipeline against it:

    ./simulator/run.sh

That's `./simulator/run.sh` = `PATH="simulator:$PATH" python family.py` — the
fetcher sees a `bee` binary, authenticates, and runs in live mode against the
six scripted scenarios (heated argument, balanced debate, monologue,
backchannel ping-pong, short Q&A, unlabeled transcript). Add your own
scenarios to `conversations.json` (timestamps are relative `minutes_ago`, so
dates stay fresh). Each utterance accepts an optional `pause_s` — seconds of
silence after it before the next turn — so a scenario can script its rhythm
(rapid-fire argument: 1.5, thoughtful debate: 4, slow monologue: 8); the
fake CLI spaces utterance timestamps by estimated speech time plus the
pause, like real Bee captures. `SIM_BEE_FAIL_AUTH=1` simulates a logged-out CLI (tests the
mock fallback); `SIM_BEE_EMPTY=1` returns zero conversations.

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
