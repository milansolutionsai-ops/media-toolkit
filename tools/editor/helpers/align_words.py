"""Snap Whisper word times to the speech the audio actually contains.

Whisper (Groq turbo and faster-whisper alike) stretches a word across the pause
next to it: "video" listed 13.96-15.72 when it was spoken at 15.33-15.72. Captions
built from those times lag, and a word whose stretched midpoint lands in a cut
disappears. ffmpeg's silencedetect knows where the speech really is, so each word
is clamped into the speech span it belongs to.

Raw times are kept as raw_start/raw_end so re-aligning with other thresholds
starts from Whisper's numbers, not from an earlier snap. A word with no speech
under it (a hallucinated "Thank you" on trailing silence) keeps its times and is
marked in_silence; captions skip it.

Usage:
    uv run python helpers/align_words.py <video> [--edit-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NOISE_DB = -35.0      # below this counts as silence
MIN_SILENCE_S = 0.15  # shorter dips are mid-phrase, not pauses
MIN_WORD_S = 0.08     # a squeezed word still gets this much screen time; less overlap is a graze

_START = re.compile(r"silence_start: (-?[\d.]+)")
_END = re.compile(r"silence_end: (-?[\d.]+)")


def parse_silencedetect(stderr: str, duration: float) -> list[tuple[float, float]]:
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in stderr.splitlines():
        if m := _START.search(line):
            start = max(0.0, float(m.group(1)))
        elif (m := _END.search(line)) and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    if start is not None:
        silences.append((start, duration))
    return silences


def speech_spans(silences: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    t = 0.0
    for a, b in silences:
        if a > t:
            spans.append((t, a))
        t = max(t, b)
    if t < duration:
        spans.append((t, duration))
    return spans


def _pick_span(start: float, end: float, spans, prev_end: float):
    """The latest speech span the word really reaches into.

    A stretched word's start drifts back into the pause; its end sits on the
    real speech. Checked against Groq on isolated snippets of a real take:
    "test", "video", "I'll" and "start" were each spoken in the span holding
    their Whisper end, never in the earlier span with the bigger overlap.
    An overlap under MIN_WORD_S is a graze, not the word.
    """
    cands = [(min(end, b) - max(start, a), a, b) for a, b in spans
             if min(end, b) > max(start, a) and b > prev_end]
    if not cands:
        return None
    real = [c for c in cands if c[0] >= MIN_WORD_S] or [max(cands)]
    return real[-1][1], real[-1][2]


def snap_words(words: list[dict], spans: list[tuple[float, float]]) -> list[dict]:
    placed: list[dict] = []
    prev_end = 0.0
    for entry in words:
        if entry.get("type") == "spacing":
            continue
        e = dict(entry)
        if e.get("type") != "word" or e.get("start") is None or e.get("end") is None:
            placed.append(e)
            continue
        raw_s = float(e.get("raw_start", e["start"]))
        raw_e = float(e.get("raw_end", e["end"]))
        e["raw_start"], e["raw_end"] = raw_s, raw_e
        e.pop("in_silence", None)
        span = _pick_span(raw_s, raw_e, spans, prev_end)
        if span is None:
            e["start"], e["end"], e["in_silence"] = raw_s, raw_e, True
            placed.append(e)
            continue
        a, b = span
        s = max(raw_s, a, prev_end)
        t = min(raw_e, b)
        if t <= s:
            t = min(b, s + MIN_WORD_S)
        e["start"], e["end"] = round(s, 3), round(t, 3)
        prev_end = e["end"]
        placed.append(e)

    out: list[dict] = []
    last_end: float | None = None
    for e in placed:
        if e.get("type") == "word" and not e.get("in_silence"):
            if last_end is not None and e["start"] > last_end:
                out.append({"text": " ", "start": last_end, "end": e["start"],
                            "type": "spacing", "speaker_id": e.get("speaker_id", "speaker_0")})
            last_end = e["end"]
        out.append(e)
    return out


def align_transcript(transcript: dict, silences, duration: float,
                     noise_db: float, min_silence: float) -> dict:
    out = dict(transcript)
    out["words"] = snap_words(transcript.get("words", []), speech_spans(silences, duration))
    out["silences"] = [[round(a, 3), round(b, 3)] for a, b in silences]
    out["alignment"] = {"method": "silence-snap", "noise_db": noise_db, "min_silence": min_silence}
    return out


def media_duration(media: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def detect_silences(media: Path, noise_db: float = NOISE_DB,
                    min_silence: float = MIN_SILENCE_S) -> tuple[list[tuple[float, float]], float]:
    duration = media_duration(media)
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return parse_silencedetect(proc.stderr, duration), duration


def main() -> None:
    ap = argparse.ArgumentParser(description="Snap a cached Whisper transcript to the real speech")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None, help="default: <video dir>/edit")
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--noise-db", type=float, default=NOISE_DB)
    ap.add_argument("--min-silence", type=float, default=MIN_SILENCE_S)
    args = ap.parse_args()

    from transcribe import transcript_path

    video = args.video.resolve()
    edit_dir = (args.edit_dir or video.parent / "edit").resolve()
    tr_path = transcript_path(edit_dir, video, args.audio_track)
    if not tr_path.exists():
        sys.exit(f"error: no transcript at {tr_path}; run transcribe.py first")
    transcript = json.loads(tr_path.read_text(encoding="utf-8"))
    silences, duration = detect_silences(video, args.noise_db, args.min_silence)
    aligned = align_transcript(transcript, silences, duration, args.noise_db, args.min_silence)
    tr_path.write_text(json.dumps(aligned, indent=2), encoding="utf-8")
    moved = sum(1 for e in aligned["words"] if e.get("type") == "word"
                and (e["start"], e["end"]) != (e.get("raw_start"), e.get("raw_end")))
    flagged = sum(1 for e in aligned["words"] if e.get("in_silence"))
    print(f"aligned {tr_path.name}: {moved} words snapped, {flagged} in silence, "
          f"{len(silences)} silences")


if __name__ == "__main__":
    main()
