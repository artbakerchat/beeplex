#!/usr/bin/env python3
"""Record from your microphone and add it as a simulator scenario.

Simulates what the Bee device itself does (capture -> transcribe ->
speaker-segmented utterances) so you can test engagement scoring on your
own voice, no hardware needed:

    pip install sounddevice faster-whisper numpy
    python3 simulator/record.py --title "Lunch with Sam" --seconds 60

Records, transcribes locally with Whisper, appends a scenario to
simulator/conversations.json, then prints its engagement score. Run
./simulator/run.sh afterwards to see it in the full reports.

Nothing leaves your machine (unless you later enable the Gemini LLM
layer, which sends transcript text to Google's API).

Speaker labels: everything is one speaker ("You") by default. For real
two-speaker diarization:

    pip install pyannote.audio
    # accept the model terms at huggingface.co/pyannote/speaker-diarization-3.1
    export HF_TOKEN=<your-huggingface-token>

Ctrl+C stops the recording early and keeps what was captured.

Chunked mode: --chunk 15 records in 15s chunks; each chunk is transcribed
(and its wav deleted) while the next chunk records, so only one chunk of
audio ever sits on disk. Without --chunk the whole recording is captured
first, then transcribed.
"""
import argparse
import json
import os
import queue
import sys
import tempfile
import threading
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "conversations.json")
RECORDINGS_DIR = os.path.join(HERE, "recordings")
SAMPLE_RATE = 16000


def record_audio(seconds):
    """Record mono 16kHz audio. Returns (samples, seconds_recorded)."""
    import numpy as np
    import sounddevice as sd

    frames = int(seconds * SAMPLE_RATE)
    print(f"Recording for {seconds}s... (Ctrl+C to stop early)")
    try:
        samples = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        samples = sd.rec(0, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        print("\nStopped early.")
    recorded = len(samples) / SAMPLE_RATE
    return samples, recorded


def save_wav(samples, path):
    import numpy as np

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(np.asarray(samples).tobytes())


def transcribe(wav_path, model_name):
    """Return [(start, end, text)] via local Whisper."""
    from faster_whisper import WhisperModel

    print(f"Transcribing with whisper-{model_name} (first run downloads the model)...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    return transcribe_with_model(model, wav_path)


def transcribe_with_model(model, wav_path):
    """Transcribe with an already-loaded model. Returns [(start, end, text)]."""
    segments, _ = model.transcribe(wav_path, beam_size=5)
    return [(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]


def transcribe_samples(samples, model, chunk_start_epoch):
    """Write samples to a temp wav, transcribe, delete the wav immediately.

    Returns [(abs_start, abs_end, text)] with absolute epoch times so chunks
    can be merged in order afterwards.
    """
    import numpy as np

    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as fh:
            with wave.open(fh, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(np.asarray(samples).tobytes())
        rel = transcribe_with_model(model, wav_path)
    finally:
        os.remove(wav_path)
    return [(chunk_start_epoch + s, chunk_start_epoch + e, t) for s, e, t in rel]


def record_rolling(seconds_total, chunk_seconds, model_name):
    """Record in chunks; transcribe chunk N while chunk N+1 records.

    Returns all segments as [(abs_start, abs_end, text)] in time order.
    Only one chunk's wav ever exists on disk at a time.
    """
    import sounddevice as sd

    from faster_whisper import WhisperModel
    print(f"Loading whisper-{model_name} (first run downloads the model)...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    work = queue.Queue()
    results = {}
    errors = []

    def transcribe_worker():
        while True:
            item = work.get()
            if item is None:
                work.task_done()
                break
            idx, samples, t0 = item
            try:
                results[idx] = transcribe_samples(samples, model, t0)
                print(f"  chunk {idx + 1} transcribed "
                      f"({len(results[idx])} segments), wav deleted")
            except Exception as exc:  # noqa: BLE001 - keep recording on failure
                errors.append(f"chunk {idx + 1}: {exc}")
                results[idx] = []
            finally:
                work.task_done()

    worker = threading.Thread(target=transcribe_worker, daemon=True)
    worker.start()

    record_start = time.time()
    idx = 0
    try:
        print(f"Recording in {chunk_seconds}s chunks... (Ctrl+C to stop early)")
        while idx * chunk_seconds < seconds_total:
            dur = min(chunk_seconds, seconds_total - idx * chunk_seconds)
            samples = sd.rec(int(dur * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                             channels=1, dtype="int16")
            sd.wait()
            work.put((idx, samples, record_start + idx * chunk_seconds))
            idx += 1
    except KeyboardInterrupt:
        sd.stop()
        print("\nStopped early - finishing transcription of recorded chunks...")
    finally:
        work.join()
        work.put(None)
        worker.join()

    for err in errors:
        print(f"WARNING: {err}", file=sys.stderr)
    segments = []
    for i in sorted(results):
        segments.extend(results[i])
    return segments


def diarize(wav_path, segments):
    """Return a speaker label per segment, or None when unavailable."""
    token = os.environ.get("HF_TOKEN")
    if not token:
        return None
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        return None
    print("Running speaker diarization (pyannote)...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=token
    )
    diarization = pipeline(wav_path)
    labels = []
    for start, end, _text in segments:
        best, best_overlap = "SPEAKER_00", 0.0
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            overlap = max(0.0, min(end, turn.end) - max(start, turn.start))
            if overlap > best_overlap:
                best, best_overlap = speaker, overlap
        labels.append(best)
    return labels


def build_scenario(conv_id, title, segments, labels):
    """Merge segments into utterances; group consecutive same-speaker runs."""
    utterances = []
    for (start, end, text), label in zip(segments, labels):
        # minutes_ago relative to now, like the other scripted scenarios
        minutes_ago = max(0.0, (segments[-1][1] - end) / 60.0)
        if utterances and utterances[-1]["speaker"] == label:
            utterances[-1]["text"] += " " + text
            utterances[-1]["_end"] = end
        else:
            utterances.append({
                "speaker": label,
                "text": text,
                "minutes_ago": round(minutes_ago, 2),
                "_start": start,
                "_end": end,
            })
    # Real inter-turn pauses from the recording itself: the gap between
    # this utterance's end and the next one's start. The fake bee uses
    # these for utterance timestamps (default 1.0s when absent).
    for prev, nxt in zip(utterances, utterances[1:]):
        prev["pause_s"] = round(max(0.0, nxt["_start"] - prev["_end"]), 2)
    for u in utterances:
        u.pop("_start", None)
        u.pop("_end", None)
    return {
        "id": conv_id,
        "title": title,
        "summary": f"Mic recording: {title}",
        "minutes_ago": 0,
        "utterances": utterances,
    }


def append_scenario(scenario):
    with open(DATA_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    data = [c for c in data if c["id"] != scenario["id"]]
    data.insert(0, scenario)
    with open(DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Saved scenario '{scenario['id']}' "
          f"({len(scenario['utterances'])} utterances) to conversations.json")


def preview_score(scenario):
    """Score the new scenario with the repo's own pipeline pieces."""
    sys.path.insert(0, os.path.dirname(HERE))
    import bee_fetcher

    conv = {
        "utterances": [
            {"speaker": u["speaker"], "text": u["text"]}
            for u in scenario["utterances"]
        ]
    }
    parts = bee_fetcher._utterance_parts(conv)
    events = bee_fetcher._utterance_events(conv)
    engagement, _tone, forward_motion = bee_fetcher._engagement_cells(parts, events)
    print(f"Engagement: {engagement} | Forward motion: {forward_motion}"
          f"  (tone needs GEMINI_API_KEY)")


def main():
    ap = argparse.ArgumentParser(description="Record mic audio as a simulator scenario.")
    ap.add_argument("--title", default="Mic recording", help="Scenario title")
    ap.add_argument("--seconds", type=int, default=60, help="Max recording length")
    ap.add_argument("--model", default="base", help="Whisper model (tiny/base/small/...)")
    ap.add_argument("--id", default=None, help="Scenario id (default: mic-<timestamp>)")
    ap.add_argument("--chunk", type=int, default=0,
                    help="Record in N-second chunks, transcribing (and deleting) "
                         "each while the next records. 0 = record whole, then transcribe")
    ap.add_argument("--keep-wav", action="store_true",
                    help="Keep the wav file after transcription (default: deleted)")
    args = ap.parse_args()

    conv_id = args.id or f"mic-{int(time.time())}"

    if args.chunk and args.chunk > 0:
        segments = record_rolling(args.seconds, args.chunk, args.model)
        if not segments:
            sys.exit("Transcription came back empty - try speaking closer to the mic.")
        print(f"Transcribed {len(segments)} segments across chunks.")
        print("Note: chunk mode labels everyone 'You' - "
              "diarization needs the full audio at once.")
        labels = ["You"] * len(segments)
    else:
        samples, recorded = record_audio(args.seconds)
        if recorded < 2:
            sys.exit("Too short - nothing to transcribe.")
        wav_path = os.path.join(RECORDINGS_DIR, conv_id + ".wav")
        save_wav(samples, wav_path)
        print(f"Saved audio to {wav_path}")

        segments = transcribe(wav_path, args.model)
        if not segments:
            sys.exit("Transcription came back empty - try speaking closer to the mic.")
        print(f"Transcribed {len(segments)} segments.")

        labels = diarize(wav_path, segments)
        if labels is None:
            print("No diarization (pyannote/HF_TOKEN not set up) - single speaker 'You'.")
            labels = ["You"] * len(segments)

        if args.keep_wav:
            print(f"Kept audio at {wav_path}")
        else:
            os.remove(wav_path)
            print(f"Deleted {wav_path}")

    scenario = build_scenario(conv_id, args.title, segments, labels)
    append_scenario(scenario)
    preview_score(scenario)
    print("Run ./simulator/run.sh to see it in the full reports.")


if __name__ == "__main__":
    main()
