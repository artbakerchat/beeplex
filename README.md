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

`llm_scoring.py` scores all of a run's transcripts in a single Gemini call:
a second-opinion engagement score plus a one-line rationale per
conversation, averaged with the deterministic score — and a
tone/positivity rating (`Warm (8/10)`), which can't be done
deterministically. Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) to enable it;
`GEMINI_MODEL` overrides the model (default `gemini-3.5-flash`). With no key
— or if the API fails — the deterministic score stands alone and the
pipeline never breaks. Note: enabling this sends your transcript text to
Google's API; the key lives only in your environment, never in the repo.

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

Pace + responsiveness form temporal **energy**, blended into Engagement as
a third domain alongside the deterministic and LLM scores (mean of
whichever domains are available). Circularity + novelty form **Forward
Motion**, reported as its own axis: engagement measures the heat, forward
motion measures whether the heat is cooking anything. A heated argument
and a sharp debate can share an engagement score while splitting on
forward motion. The LLM also rates progress 1–10 ("Spinning"…"Advancing")
and blends with the deterministic forward-motion score; paraphrase-level
going-in-circles can't be caught by word counting, so that half is the
LLM's job. When timestamps are missing the temporal domain abstains and
the other domains carry the score.

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
