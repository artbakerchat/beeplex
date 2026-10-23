# Friction log — BeePlex (Bee track, Build, Ship, Shape: Amazon Developer Hackathon)

Format per the Devpost guidance: task attempted · steps taken · expected vs actual · severity · workaround · actionable suggestion.

---
### 1. Mic-recording dependencies on the user's own machine (record.py)

- **Task attempted:** Run the simulator's mic-recording path
  (`python3 record.py --id mic-test --title "Mic test" --seconds 60`) on the
  user's machine to create real voice scenarios for the demo.
- **Steps taken:** Ran the script from the repo's `simulator/` directory on
  2026-09-25.
- **Expected vs actual:** Expected it to record and transcribe. Got
  `ModuleNotFoundError: No module named 'numpy'` — the audio/ML
  dependencies were never installed on that machine.
- **Severity:** Low (environment setup, not a product defect).
- **Workaround:** `pip install numpy sounddevice faster-whisper` — one
  command; on Windows, sounddevice's wheel already bundles the PortAudio
  DLL, so no separate PortAudio install. First run downloads the Whisper
  base model (~150 MB, one-time).
- **Actionable suggestion:** Ship a `requirements-mic.txt` (or document the
  one-command install) and surface the ~150 MB first-run model download in
  the README so it doesn't surprise anyone mid-demo.

### 2. `bee login` documented for iOS only; user on Android early-access

- **Task attempted:** Verify the `bee login` developer-mode unlock on the
  early-access Android app (device-setup milestone).
- **Steps taken:** Read the available documentation for the login/unlock flow.
- **Expected vs actual:** Expected an Android path. The documented flow is
  iOS-centric (tap Version 5× to unlock developer mode); no Android
  equivalent was documented.
- **Severity:** Moderate — for any Android early-access user, the first-run
  login is a guessing game.
- **Workaround:** None verified — the device was never purchased (see #4),
  so this was never tested end-to-end.
- **Actionable suggestion:** Document the Android unlock/login flow with the
  same care as the iOS one; Android early-access users are exactly the
  developers building on the API.

### 3. Bee cloud API uses a private CA

- **Task attempted:** Call the Bee cloud API directly at api.bee.computer.
- **Steps taken:** Followed the documented transport setup.
- **Expected vs actual:** Expected standard TLS. The API presents a private
  CA, so HTTPS clients must pin the `bee-ca.pem` shipped with the CLI.
- **Severity:** Low.
- **Workaround:** Pin `bee-ca.pem` as documented; works fine after that.
- **Actionable suggestion:** Either move to a public CA or put the pinning
  snippet (per language: Python requests, curl, Node) in the quickstart —
  it's currently a "read the fine print" step.

### 4. Bee Pioneer: US-only shipping reshaped the whole entry

- **Task attempted:** Acquire a Bee Pioneer ($49.99 USD) for live-data
  testing ahead of the demo.
- **Steps taken:** Checked bee.computer (ships US-only, ~2 weeks) and
  watched Amazon weekly for a genuine listing — none exists.
- **Expected vs actual:** Expected the hardware to be obtainable for a
  Bee-track entry. US-only shipping meant a cross-border parcel run to
  Point Roberts; in the end the purchase was dropped.
- **Severity:** Moderate — it changed the architecture of the entry: the
  demo is software/API-first (Bee API transcripts + scripted simulator +
  mic recordings) instead of wearable-first.
- **Workaround:** Built the simulator (scripted Bee CLI producing realistic
  transcript JSON) and the `record.py` mic path so every Bee-dependent
  feature works with zero hardware.
- **Actionable suggestion:** For the Bee track specifically, either make the
  hardware obtainable for international developers or bless the API +
  simulator path as a first-class way to enter (the judging criteria already
  do — but the marketing leans hardware).

---
