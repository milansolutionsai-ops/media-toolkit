"""Transcribe a video (Groq Whisper, ElevenLabs Scribe, or local faster-whisper).

Extracts mono 16kHz audio via ffmpeg and transcribes it with word-level
timestamps. Scribe adds diarization and audio events; the Whisper backends
are converted to the same Scribe shape so everything downstream reads one
format. Writes <edit_dir>/transcripts/<video_stem>.json.

Cached: if the output file already exists, the upload is skipped.

Usage:
    python helpers/transcribe.py <video_path>
    python helpers/transcribe.py <video_path> --backend local
    python helpers/transcribe.py <video_path> --edit-dir /custom/edit
    python helpers/transcribe.py <video_path> --language en
    python helpers/transcribe.py <video_path> --num-speakers 2
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import requests

import align_words


SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"
GROQ_MAX_BYTES = 25 * 1024 * 1024  # free-tier upload limit

# Whisper tends to clean fillers out of transcripts. A prompt written the way
# people actually talk nudges it to keep "um" / "uh" so filler cuts still work.
FILLER_PROMPT = "Umm, so, uh, I mean, like, you know, hmm. Let me, let me start that again."


def load_env_value(name: str) -> str:
    """Value of `name` from the repo .env, ./.env, or the environment. '' if missing."""
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == name:
                    v = v.strip().strip('"').strip("'")
                    if v:
                        return v
    return os.environ.get(name, "")


def pick_backend(requested: str | None = None) -> tuple[str, str]:
    """(backend, api_key). Default order: groq, elevenlabs, local (free, no key)."""
    if requested == "local":
        return "local", ""
    for backend, env in (("groq", "GROQ_API_KEY"), ("elevenlabs", "ELEVENLABS_API_KEY")):
        if requested not in (None, backend):
            continue
        key = load_env_value(env)
        if key:
            return backend, key
        if requested == backend:
            sys.exit(f"{env} not found in .env or environment")
    return "local", ""


def count_audio_tracks(video_path: Path) -> int:
    """How many audio streams the container holds."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def peak_dbfs(wav_path: Path) -> float:
    """Peak level of a 16-bit PCM wav, in dBFS. -inf for digital silence."""
    peak = 0
    with wave.open(str(wav_path), "rb") as w:
        # A chunk at a time: batch mode runs several of these at once, and a two-hour
        # take is 230 MB of 16 kHz mono before the array copy doubles it.
        while frames := w.readframes(1 << 16):
            samples = array.array("h", frames)
            peak = max(peak, max(samples), -min(samples))
    return 20 * math.log10(peak / 32768) if peak > 0 else float("-inf")


def extract_audio(video_path: Path, dest: Path, audio_track: int = 0) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-map", f"0:a:{audio_track}",
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def to_upload_audio(wav_path: Path, dest: Path) -> None:
    """Opus at 32 kbps: ~0.24 MB/min, so takes up to ~100 min fit Groq's 25 MB.

    Lossless FLAC (~1 MB/min) capped a free upload at ~25 min. Speech at this
    bitrate transcribes as well as the original.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libopus", "-b:a", "32k", str(dest)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def whisper_to_scribe(payload: dict, source: str) -> dict:
    """Whisper word list -> the Scribe shape pack_transcripts reads.

    Whisper has no diarization or audio events, so every word is speaker_0 and
    the gaps between words become 'spacing' entries, which is how the packer
    finds silences.
    """
    words: list[dict] = []
    prev_end: float | None = None
    for w in payload.get("words", []):
        start, end = float(w["start"]), float(w["end"])
        if prev_end is not None and start > prev_end:
            words.append({"text": " ", "start": prev_end, "end": start,
                          "type": "spacing", "speaker_id": "speaker_0"})
        words.append({"text": str(w["word"]).strip(), "start": start, "end": end,
                      "type": "word", "speaker_id": "speaker_0"})
        prev_end = end
    return {
        "language_code": payload.get("language"),
        "text": str(payload.get("text", "")).strip(),
        "words": words,
        "source": source,
    }


def call_groq(
    audio_path: Path,
    api_key: str,
    language: str | None = None,
    prompt: str = FILLER_PROMPT,
) -> dict:
    size = audio_path.stat().st_size
    if size > GROQ_MAX_BYTES:
        raise RuntimeError(
            f"{audio_path.name} is {size / (1024 * 1024):.1f} MB, over Groq's 25 MB "
            "free-tier limit. Rerun with --backend local."
        )
    data = [
        ("model", GROQ_MODEL),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
        ("timestamp_granularities[]", "segment"),
        ("temperature", "0"),
        ("prompt", prompt),
    ]
    if language:
        data.append(("language", language))
    with open(audio_path, "rb") as f:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, f, f"audio/{audio_path.suffix.lstrip('.')}")},
            data=data,
            timeout=600,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq returned {resp.status_code}: {resp.text[:300]}")
    return whisper_to_scribe(resp.json(), source=f"groq/{GROQ_MODEL}")


def call_local_whisper(
    audio_path: Path,
    language: str | None = None,
    prompt: str = FILLER_PROMPT,
    model_size: str = "small",
) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "local backend needs faster-whisper: run `uv sync --python 3.12 --extra local`"
        ) from None
    import numpy as np

    # Decode the 16 kHz mono wav ourselves: faster-whisper's own decoder goes
    # through PyAV, whose newer releases reject the arguments it passes.
    with wave.open(str(audio_path), "rb") as w:
        pcm = w.readframes(w.getnframes())
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        samples, language=language, initial_prompt=prompt, word_timestamps=True,
    )
    words = [{"word": w.word, "start": w.start, "end": w.end}
             for seg in segments for w in (seg.words or [])]
    return whisper_to_scribe(
        {"language": info.language, "text": "".join(w["word"] for w in words), "words": words},
        source=f"local/faster-whisper-{model_size}",
    )


def call_scribe(
    audio_path: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
) -> dict:
    data: dict[str, str] = {
        "model_id": "scribe_v1",
        "diarize": "true",
        "tag_audio_events": "true",
        "timestamps_granularity": "word",
    }
    if language:
        data["language_code"] = language
    if num_speakers:
        data["num_speakers"] = str(num_speakers)

    with open(audio_path, "rb") as f:
        resp = requests.post(
            SCRIBE_URL,
            headers={"xi-api-key": api_key},
            files={"file": (audio_path.name, f, "audio/wav")},
            data=data,
            timeout=1800,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Scribe returned {resp.status_code}: {resp.text[:500]}")

    return resp.json()


def transcript_path(edit_dir: Path, video: Path, audio_track: int = 0) -> Path:
    """Where a video's transcript lands.

    The track belongs in the name, or a rerun with --audio-track hands back the transcript of
    the track it is meant to replace. Track 0 keeps the plain name, so transcripts made before
    the flag existed stay valid. Batch mode tests its cache with this too — one function, so
    the two cannot drift apart.
    """
    suffix = "" if audio_track == 0 else f".track{audio_track}"
    return edit_dir / "transcripts" / f"{video.stem}{suffix}.json"


WHISPER_BACKENDS = ("groq", "local")


def finalize_payload(payload: dict, backend: str, audio: Path) -> dict:
    """Whisper stretches words across pauses; snap them to the real speech.

    Scribe's word times are already tight, so its payload passes through.
    """
    if backend not in WHISPER_BACKENDS:
        return payload
    try:
        silences, duration = align_words.detect_silences(audio)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        # Never lose a finished transcript to a failed probe; align_words.py can re-snap it later.
        print(f"  warning: silence detection failed ({e}); saving unaligned transcript", flush=True)
        return payload
    return align_words.align_transcript(
        payload, silences, duration, align_words.NOISE_DB, align_words.MIN_SILENCE_S
    )


def transcribe_one(
    video: Path,
    edit_dir: Path,
    backend: str,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
    verbose: bool = True,
    audio_track: int = 0,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists.
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcript_path(edit_dir, video, audio_track)

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    if verbose:
        print(f"  extracting audio from {video.name}", flush=True)

    n_tracks = count_audio_tracks(video)
    if n_tracks > 1 and verbose:
        print(f"  note: {video.name} has {n_tracks} audio tracks, using track "
              f"{audio_track + 1} (--audio-track to change)", flush=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.wav"
        extract_audio(video, audio, audio_track)

        # Uploading silence costs the same as uploading speech and returns
        # nothing, so catch the wrong-track case before paying for it.
        peak = peak_dbfs(audio)
        if peak < -60.0:
            raise RuntimeError(
                f"track {audio_track + 1} of {video.name} is silent "
                f"(peak {peak:.1f} dBFS) - not uploading. "
                + (f"The file has {n_tracks} audio tracks; try --audio-track "
                   + " or ".join(str(i) for i in range(n_tracks) if i != audio_track) + "."
                   if n_tracks > 1 else "Check the source audio.")
            )

        if backend == "groq":
            upload = Path(tmp) / f"{video.stem}.ogg"
            to_upload_audio(audio, upload)
            if verbose:
                print(f"  groq: uploading {upload.name} "
                      f"({upload.stat().st_size / (1024 * 1024):.1f} MB)", flush=True)
            payload = call_groq(upload, api_key, language)
        elif backend == "elevenlabs":
            if verbose:
                print(f"  scribe: uploading {audio.name} "
                      f"({audio.stat().st_size / (1024 * 1024):.1f} MB)", flush=True)
            payload = call_scribe(audio, api_key, language, num_speakers)
        else:
            if verbose:
                print("  local: faster-whisper on CPU (first run downloads the model)",
                      flush=True)
            payload = call_local_whisper(audio, language)

        payload = finalize_payload(payload, backend, audio)

    out_path.write_text(json.dumps(payload, indent=2))
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s")
        if isinstance(payload, dict) and "words" in payload:
            print(f"    words: {len(payload['words'])}")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video (groq, elevenlabs or local)")
    ap.add_argument("video", type=Path, help="Path to video file")
    ap.add_argument(
        "--backend",
        choices=["groq", "elevenlabs", "local"],
        default=None,
        help="Transcription backend. Default: groq if GROQ_API_KEY is set, "
             "else elevenlabs if ELEVENLABS_API_KEY is set, else local.",
    )
    ap.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit output directory (default: <video_parent>/edit)",
    )
    ap.add_argument(
        "--language",
        type=str,
        default=None,
        help="Optional ISO language code (e.g., 'en'). Omit to auto-detect.",
    )
    ap.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Optional number of speakers when known. Improves diarization accuracy.",
    )
    ap.add_argument(
        "--audio-track",
        type=int,
        default=0,
        help="Zero-based audio track to transcribe. OBS writes the game on track 0 "
             "and the mic on track 1; without this ffmpeg applies its default audio "
             "stream selection, which picks the track with the most channels.",
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    backend, api_key = pick_backend(args.backend)

    try:
        transcribe_one(
            video=video,
            edit_dir=edit_dir,
            backend=backend,
            api_key=api_key,
            language=args.language,
            num_speakers=args.num_speakers,
            audio_track=args.audio_track,
        )
    except RuntimeError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
