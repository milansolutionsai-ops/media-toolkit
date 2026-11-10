"""Render a video from an EDL.

Implements the HEURISTICS render pipeline in the correct order:

  1. Per-segment extract with color grade + 30ms audio fades baked in
  2. Lossless -c copy concat into base.mp4
  3. If overlays or subtitles: single filter graph that overlays animations
     (with PTS shift so frame 0 lands at the overlay window start)
     and applies `subtitles` filter LAST → final.mp4

Optionally builds a master SRT from the per-source transcripts + EDL
output-timeline offsets, applies the proven force_style (2-word
UPPERCASE chunks, Helvetica 18 Bold, MarginV=50).

Usage:
    python helpers/render.py <edl.json> -o final.mp4
    python helpers/render.py <edl.json> -o preview.mp4 --preview
    python helpers/render.py <edl.json> -o final.mp4 --build-subtitles
    python helpers/render.py <edl.json> -o final.mp4 --no-subtitles
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

# Windows consoles default to cp1252, which cannot print the arrows in the
# progress lines and crashes the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ass_captions  # noqa: E402
import clean_audio  # noqa: E402  (same directory; also when loaded by path from tests)

try:
    from grade import get_preset, auto_grade_for_clip  # same directory
except Exception:
    def get_preset(name: str) -> str:
        return ""

    def auto_grade_for_clip(video, start=0.0, duration=None, verbose=False):  # type: ignore
        return "eq=contrast=1.03:saturation=0.98", {}


# -------- Subtitle style (bold-overlay, proven at 1920×1080 and 1080×1920) --
#
# MarginV is a platform safe-zone call. libass scales against PlayResY=288, so
# MarginV=50 puts the baseline ~17% up from the bottom. That clears LinkedIn's
# feed controls (progress bar, mute/captions buttons), the primary platform.
# TikTok / Reels / Shorts cover the bottom ~25-30% with UI: use ~90 there.
SUB_MARGIN_V = 50
SUB_FORCE_STYLE = (
    "FontName=Helvetica,FontSize=18,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H00000000,"
    "BorderStyle=1,Outline=2,Shadow=0,"
    f"Alignment=2,MarginV={SUB_MARGIN_V}"
)

# -------- Helpers ------------------------------------------------------------


def run(cmd: list[str], quiet: bool = False) -> None:
    if not quiet:
        print(f"  $ {' '.join(str(c) for c in cmd[:6])}{' …' if len(cmd) > 6 else ''}")
    subprocess.run(cmd, check=True)


def resolve_grade_filter(grade_field: str | None) -> str:
    """The EDL's 'grade' field can be a preset name, a raw ffmpeg filter, or 'auto'.

    Returns the filter string to embed into the per-segment -vf chain.
    For 'auto', returns the sentinel "__AUTO__" which is resolved per-segment.
    """
    if not grade_field:
        return ""
    if grade_field == "auto":
        return "__AUTO__"
    # Preset names are short identifiers, filter strings contain '=' or ','.
    if re.fullmatch(r"[a-zA-Z0-9_\-]+", grade_field):
        try:
            return get_preset(grade_field)
        except KeyError:
            print(f"warning: unknown preset '{grade_field}', using as raw filter")
            return grade_field
    return grade_field


def resolve_path(maybe_path: str, base: Path) -> Path:
    """Resolve a path that may be absolute or relative to `base`."""
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return (base / p).resolve()


def resolve_subtitles_path(maybe_path: str, edit_dir: Path) -> Path:
    """Resolve the EDL's subtitles path: relative to the EDL's directory, else the
    current directory (agents often write "edit/master.srt"). A missing file is an
    error: rendering on without it silently ships a video with no captions."""
    candidates = [resolve_path(maybe_path, edit_dir)]
    if not Path(maybe_path).is_absolute():
        candidates.append(Path(maybe_path).resolve())
    for c in candidates:
        if c.exists():
            return c
    tried = ", ".join(str(c) for c in candidates)
    sys.exit(f"subtitles file in EDL not found (tried {tried}). Fix the path or pass --no-subtitles.")


# -------- HDR → SDR tone mapping (HLG / PQ sources) --------------------------
#
# iPhone defaults to HLG HDR in Rec.2020 (and many mirrorless cameras ship PQ).
# If the source is HDR and we only downconvert bit depth (yuv420p10le → yuv420p)
# without tone-mapping, the output is 8-bit but still carries HLG/PQ transfer
# metadata. Players that honor the metadata (screen recorders, most social
# upload re-encodes) interpret 8-bit values in an HDR container and the result
# looks oversaturated / blown out. QuickTime on macOS can hide this locally —
# screen recording and uploaded renders cannot.
#
# Fix: detect HDR via color_transfer and prepend a zscale+tonemap chain to the
# vf graph so the output is clean Rec.709 SDR.

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}  # PQ (HDR10) and HLG

TONEMAP_CHAIN = (
    "zscale=t=linear:npl=100,"
    "format=gbrpf32le,"
    "zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,"
    "format=yuv420p"
)


def is_hdr_source(video: Path) -> bool:
    """Return True if the source uses a PQ or HLG transfer function."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() in HDR_TRANSFERS
    except subprocess.CalledProcessError:
        return False


def is_portrait_source(video: Path) -> bool:
    """Return True if the displayed video is portrait, including rotation."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height:stream_side_data=rotation",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if not streams:
            return False
        stream = streams[0]
        w, h = int(stream["width"]), int(stream["height"])

        # ffmpeg autorotates display-matrix side data before applying filters.
        # Swap coded dimensions for quarter-turns so the scale axis is selected
        # from the dimensions the filter actually sees. A plain metadata tag is
        # intentionally ignored because it does not guarantee autorotation.
        rotation = 0
        for side_data in stream.get("side_data_list") or []:
            if side_data.get("rotation") is not None:
                rotation = side_data["rotation"]
                break
        if int(round(float(rotation))) % 360 in (90, 270):
            w, h = h, w
        return h > w
    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        OSError,
        OverflowError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return False


def parse_fps(value: str) -> str:
    """Validate and canonicalize an ffmpeg frame rate."""
    text = value.strip()
    if len(text) > 32 or not re.fullmatch(
        r"(?:[0-9]+(?:\.[0-9]+)?|[0-9]+/[0-9]+)", text
    ):
        raise argparse.ArgumentTypeError(
            "FPS must be a positive number or rational, e.g. 30 or 30000/1001"
        )
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError(
            "FPS must be a positive number or rational, e.g. 30 or 30000/1001"
        ) from exc
    if rate <= 0:
        raise argparse.ArgumentTypeError("FPS must be greater than zero")
    # FFmpeg stores video rates as AVRational (signed 32-bit components).
    # Bounding the reduced fraction keeps every accepted canonical value safe
    # for ffmpeg and makes parse_fps(parse_fps(value)) idempotent.
    max_component = 2_147_483_647
    if rate.numerator > max_component or rate.denominator > max_component:
        raise argparse.ArgumentTypeError("FPS precision or magnitude is too large")
    return f"{rate.numerator}/{rate.denominator}"


def probe_source_fps(video: Path) -> str | None:
    """Return an ffmpeg-ready source rate, preferring the average frame rate.

    ``avg_frame_rate`` represents the observed average and is the better default
    for variable-frame-rate inputs. ``r_frame_rate`` remains a fallback for
    streams where the average is unavailable. Values are normalized to an exact
    rational so rates such as ``30000/1001`` survive without rounding.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate,r_frame_rate",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if not streams:
            return None
        for field in ("avg_frame_rate", "r_frame_rate"):
            value = streams[0].get(field)
            if value and value != "0/0":
                try:
                    return parse_fps(value)
                except argparse.ArgumentTypeError:
                    continue
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        return None
    return None


# -------- Per-segment extraction (Rule 2 + Rule 3) --------------------------


def scaled_size(src: tuple[int, int], portrait: bool, draft: bool) -> tuple[int, int]:
    """Frame size the plain segment scale (-2:1920 / 1920:-2, or 1280 for drafts) gives this source."""
    sw, sh = sorted(src) if portrait else sorted(src, reverse=True)   # phone files store 1920x1080 + rotation
    long = 1280 if draft else 1920
    if portrait:
        return 2 * round(long * sw / sh / 2), long
    return long, 2 * round(long * sh / sw / 2)


def segment_vf(portrait: bool, hdr: bool, draft: bool, grade_filter: str, zoom: float = 1.0,
               size: tuple[int, int] | None = None) -> str:
    """Video filter for one segment: tonemap, scale, optional punch-in, grade.

    A punch-in (zoom > 1) crops the centre and scales back to the same frame,
    so every segment keeps one size for the lossless concat. Pass `size` (scaled_size) so the
    scale-back is exact: crop rounding otherwise left zoomed segments 2px narrower.
    """
    if draft:
        scale = "scale=-2:1280" if portrait else "scale=1280:-2"
    else:
        scale = "scale=-2:1920" if portrait else "scale=1920:-2"
    parts: list[str] = []
    if hdr:
        parts.append(TONEMAP_CHAIN)
    parts.append(scale)
    if zoom and zoom > 1.0:
        parts.append(f"crop=trunc(iw/{zoom:g}/2)*2:trunc(ih/{zoom:g}/2)*2")
        parts.append(f"scale={size[0]}:{size[1]}" if size else scale)
    if grade_filter:
        parts.append(grade_filter)
    return ",".join(parts)


def extract_segment(
    source: Path,
    seg_start: float,
    duration: float,
    grade_filter: str,
    out_path: Path,
    preview: bool = False,
    draft: bool = False,
    rate: str | None = None,
    zoom: float = 1.0,
) -> None:
    """Extract a cut range as its own MP4 with grade + 30ms audio fades baked in.

    `-ss` before `-i` for fast accurate seeking. Scale to 1080p from 4K.
    Portrait sources (height > width) are scaled by height to preserve orientation.

    Quality ladder:
      - final (default): 1080p libx264 fast CRF 20
      - preview:         1080p libx264 medium CRF 22 (evaluable for QC)
      - draft:           720p libx264 ultrafast CRF 28 (cut-point check only)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    portrait = is_portrait_source(source)
    size = scaled_size(probe_frame_size(source), portrait, draft) if zoom and zoom > 1.0 else None
    vf = segment_vf(portrait, is_hdr_source(source), draft, grade_filter, zoom, size)

    # 30ms audio fades at both edges (Rule 3) — prevent pops
    fade_out_start = max(0.0, duration - 0.03)
    af = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.03"

    if draft:
        preset, crf = "ultrafast", "28"
    elif preview:
        preset, crf = "medium", "22"
    else:
        preset, crf = "fast", "20"

    # Frame rate: use the rate the caller resolved once for the whole render
    # (every segment must share it — concat -c copy in Rule 2 requires a uniform
    # frame rate). When called standalone with no rate, preserve this source's
    # own rate; fall back to 24 only if it can't be probed.
    out_rate = rate if rate is not None else (probe_source_fps(source) or "24")

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seg_start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p", "-r", out_rate,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probe_frame_size(video: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def prepare_sources(edl: dict, edit_dir: Path, clean: bool) -> dict:
    """Swap each source for its noise-cleaned copy (see clean_audio.py) unless
    --no-clean-audio. The EDL's own "audio_clean" field can also switch it off."""
    if not clean:
        return edl
    return clean_audio.with_clean_sources(edl, edit_dir)


def extract_all_segments(
    edl: dict,
    edit_dir: Path,
    preview: bool,
    draft: bool = False,
    fps: str | None = None,
) -> list[Path]:
    """Extract every EDL range into edit_dir/clips_graded/seg_NN.mp4.
    Returns the ordered list of segment paths.

    If the EDL `grade` is "auto", analyze each segment range with
    `auto_grade_for_clip` and apply a per-segment subtle correction.
    Otherwise, apply the same preset/raw filter to every segment.
    """
    resolved = resolve_grade_filter(edl.get("grade"))
    is_auto = resolved == "__AUTO__"
    clips_dir = edit_dir / (
        "clips_draft" if draft else ("clips_preview" if preview else "clips_graded")
    )
    clips_dir.mkdir(parents=True, exist_ok=True)

    ranges = edl["ranges"]
    sources = edl["sources"]

    # Resolve ONE output frame rate for the entire render and apply it to every
    # segment. The lossless concat (Rule 2, `-c copy`) requires all segments to
    # share a frame rate; probing per-segment would diverge for multi-source
    # EDLs that mix rates (e.g. a 30fps and a 60fps source) and break the concat.
    # Explicit --fps wins; otherwise preserve the first source's rate.
    if fps is not None:
        out_rate = parse_fps(str(fps))
    elif ranges:
        first_src = resolve_path(sources[ranges[0]["source"]], edit_dir)
        out_rate = probe_source_fps(first_src) or "24"
    else:
        out_rate = "24"

    seg_paths: list[Path] = []
    print(f"extracting {len(ranges)} segment(s) → {clips_dir.name}/  @ {out_rate} fps"
          f"{' (forced)' if fps is not None else ' (from source)'}")
    if is_auto:
        print("  (auto-grade per segment: analyzing each range)")
    zooms = effective_zooms(ranges, edl.get("reframe"))
    for i, r in enumerate(ranges):
        src_name = r["source"]
        src_path = resolve_path(sources[src_name], edit_dir)
        start = float(r["start"])
        end = float(r["end"])
        duration = end - start
        out_path = clips_dir / f"seg_{i:02d}_{src_name}.mp4"

        if is_auto:
            seg_filter, _stats = auto_grade_for_clip(src_path, start=start, duration=duration, verbose=False)
        else:
            seg_filter = resolved

        note = r.get("beat") or r.get("note") or ""
        print(f"  [{i:02d}] {src_name}  {start:7.2f}-{end:7.2f}  ({duration:5.2f}s)  {note}")
        if is_auto:
            print(f"        grade: {seg_filter or '(none)'}")
        extract_segment(src_path, start, duration, seg_filter, out_path, preview=preview, draft=draft,
                        rate=out_rate, zoom=zooms[i])
        seg_paths.append(out_path)

    return seg_paths


# -------- Lossless concat ----------------------------------------------------


def concat_segments(segment_paths: list[Path], out_path: Path, edit_dir: Path) -> None:
    """Lossless concat via the concat demuxer. No re-encode."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = edit_dir / "_concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"concat → {out_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    concat_list.unlink(missing_ok=True)


# -------- Master SRT (Rule 5) ------------------------------------------------


PUNCT_BREAK = set(".,!?;:")


def _srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_in_range(transcript: dict, t_start: float, t_end: float) -> list[dict]:
    out: list[dict] = []
    for w in transcript.get("words", []):
        if w.get("type") != "word":
            continue
        if w.get("in_silence"):
            continue  # no speech under it: a Whisper hallucination, never caption it
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        # A word belongs to the segment its midpoint falls in. Plain overlap let
        # a word the cut removed (a dropped "um" grazing the range by 5 ms) still
        # flash on screen as a caption.
        mid = (ws + we) / 2
        if mid < t_start or mid >= t_end:
            continue
        out.append(w)
    return out


CHUNK_WORDS = 2         # target words per cue
CHUNK_MAX_WORDS = 3     # a too-short chunk may grow to this many words
CHUNK_MIN_S = 0.35      # a cue shorter than this reads as a flash
CHUNK_PAUSE_S = 0.3     # a gap this long between words ends the cue


def chunk_words(words: list[dict]) -> list[list[dict]]:
    """Group transcript words into caption cues.

    A cue closes on trailing punctuation or on a pause before the next word.
    Otherwise it closes at CHUNK_WORDS words, unless it would be on screen for
    less than CHUNK_MIN_S; then it takes up to CHUNK_MAX_WORDS words. So
    "does | is" across a pause stays split, and fast "what a" does not flash.
    """
    words = [w for w in words if (w.get("text") or "").strip()]
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for i, w in enumerate(words):
        current.append(w)
        text = w["text"].strip()
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 0.0
        dur = w["end"] - current[0]["start"]
        if (
            nxt is None
            or text[-1] in PUNCT_BREAK
            or gap >= CHUNK_PAUSE_S
            or len(current) >= CHUNK_MAX_WORDS
            or (len(current) >= CHUNK_WORDS and dur >= CHUNK_MIN_S)
        ):
            chunks.append(current)
            current = []
    return chunks


SENTENCE_MAX_WORDS = 9  # a longer sentence splits so the pill stays within two lines


def chunk_sentences(words: list[dict]) -> list[list[dict]]:
    """Group words into sentence cues (EDL "captions": "sentence"): close on . ? !
    or at SENTENCE_MAX_WORDS words."""
    words = [w for w in words if (w.get("text") or "").strip()]
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        current.append(w)
        if w["text"].strip()[-1] in ".?!" or len(current) >= SENTENCE_MAX_WORDS:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def active_word_events(words: list[dict], seg_start: float, seg_offset: float,
                       seg_end: float, brand: dict | None = None) -> list[tuple[float, float, str]]:
    """EDL "captions": "active": the chunk stays on screen, one cue per word, the spoken word on a teal box."""
    texts = [(w.get("text") or "").strip().rstrip(",;:") for w in words]
    ev = []
    for i, w in enumerate(words):
        a = max(seg_start, w["start"]) - seg_start + seg_offset
        nxt = words[i + 1]["start"] if i + 1 < len(words) else min(seg_end, w["end"])
        b = max(a + 0.05, min(seg_end, nxt) - seg_start + seg_offset)
        ev.append((a, b, ass_captions.active_text(texts, i, (brand or {}).get("active", "box"),
                                                  (brand or {}).get("accent"))))
    return ev


WHIP_S = 0.2          # whip-pan length on each side of the cut (6 frames at 30 fps)
WHIP_SHIFT = 0.08     # slide, as a share of the frame width
WHIP_BLUR = 30        # boxblur radius at full whip


def whip_exit(idx: int, start: float, duration: float, d: float = WHIP_S) -> tuple[list[str], str]:
    """Overlay `idx` leaves with a whip pan: its last `d` seconds blur up while it slides left.
    Returns the filter lines that build [a{idx}] and the overlay x expression."""
    end = start + duration
    parts = [
        f"[{idx}:v]setpts=PTS-STARTPTS,format=yuva420p,split[s{idx}][b{idx}]",
        f"[b{idx}]boxblur={WHIP_BLUR}:1,fade=t=in:st={duration - d:.3f}:d={d:.3f}:alpha=1[bf{idx}]",
        f"[s{idx}][bf{idx}]overlay=0:0,tpad=start_duration={start:.3f}:color=black@0[a{idx}]",
    ]
    x = f"'-W*{WHIP_SHIFT}*pow(clip((t-{end - d:.3f})/{d:.3f},0,1),2)'"
    return parts, x


def whip_settle(current: str, out_label: str, end: float, d: float = WHIP_S) -> list[str]:
    """The shot after a whip starts shifted right and blurred, and settles into place over `d` seconds."""
    k = out_label.strip("[]")
    return [
        f"{current}split[{k}m][{k}c]",
        f"[{k}c]boxblur={WHIP_BLUR}:1,format=yuva420p,fade=t=out:st={end:.3f}:d={d:.3f}:alpha=1[{k}b]",
        f"[{k}m][{k}b]overlay=x='W*{WHIP_SHIFT}*pow(1-clip((t-{end:.3f})/{d:.3f},0,1),2)':y=0"
        f":enable='between(t,{end:.3f},{end + d:.3f})'{out_label}",
    ]


def drawtext_escape(text: str) -> str:
    return text.replace("\\", "").replace("'", "").replace(":", r"\:").replace("%", r"\%")


def finalize_active(entries: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Active-word cues: trim each to the next one's start and drop flashes. Joining (finalize_cues)
    would put two copies of the same chunk on screen. A gap under CUE_GAP_CLOSE_S (a cut between two
    chunks) is closed, so captions don't blink off for a few frames at every cut."""
    entries = sorted(entries, key=lambda e: e[0])
    out = []
    for i, (a, b, t) in enumerate(entries):
        if i + 1 < len(entries):
            nxt = entries[i + 1][0]
            b = nxt if 0 <= nxt - b < CUE_GAP_CLOSE_S else min(b, nxt)
        if b - a >= MIN_CUE_S:
            out.append((a, b, t))
    return out


def hook_behind_text(current: str, out_label: str, lines: list[str], seconds: float, height: int,
                     width: int = 1080, color: str = "0xE9E8E4", top: float = 0.17, fill: bool = False,
                     shadow: bool = False, font_file: str | None = None, em: float = 0.62) -> str:
    """Hook title lines drawn on the footage (the person cutout goes on top, so the head covers them).
    Each line fades up and rises 2% of the frame; the second starts 0.13s after the first. The text fades out over
    the last 0.25s and is gone one frame early, so it never shows without the cutout in front of it.
    fill: each line sized on its own to fill 92% of the width (short lines set huge, capped at 14% of the height).
    shadow: a soft dark drop shadow so light text reads on a light wall.
    em: the font's average uppercase glyph width in ems (Plex Bold 0.62; wide faces ~0.8, condensed ~0.5)."""
    font = subtitles_filter_path(font_file or str(FONTS_DIR / "IBMPlexSans-Bold.ttf"))
    if fill:
        sizes = [round(min(height * 0.14, width * 0.92 / (em * max(1, len(x))))) for x in lines]
    else:
        size = round(min(height * 0.075, width * 0.9 / (em * max(len(x) for x in lines))))
        sizes = [size] * len(lines)
    rise = height * 0.02
    end, fade = seconds - 0.05, 0.25
    out_alpha = f"clip(({seconds:.3f}-t)/{fade:.3f}\,0\,1)"
    chain, y = [], height * top
    for i, (line, size) in enumerate(zip(lines, sizes)):
        t0 = 0.15 + i * 0.13
        p = f"clip((t-{t0:.3f})/0.4\,0\,1)"
        ease = f"(1-pow(1-{p}\,3))"
        sh = f":shadowcolor=0x000000@0.55:shadowx={max(2, size // 25)}:shadowy={max(2, size // 25)}" if shadow else ""
        chain.append(
            f"drawtext=fontfile='{font}':text='{drawtext_escape(line)}':fontsize={size}:fontcolor={color}{sh}"
            f":x=(w-text_w)/2:y='{y:.0f}+{rise:.0f}*(1-{ease})':alpha='{ease}*{out_alpha}'"
            f":enable='lt(t,{end:.3f})'"
        )
        y += size * 1.0
    return f"{current}{','.join(chain)}{out_label}"


MATTING_DIR = Path(__file__).resolve().parents[2] / "matting"


def make_cutout(base_path: Path, seconds: float, edit_dir: Path, key: str | None = None,
                engine: str = "u2net") -> Path:
    """Person cutout (VP9 + alpha) of the first `seconds` of the cut; only its alpha is used (as a mask on the
    current picture), so one cutout serves every grade. HyperFrames remove-background (u2net_human_seg, local, CPU).
    With `key` (mask_key: the cut itself) it's cached across renders; without, it's redone when the base changes."""
    clip = edit_dir / "hook_clip.mp4"
    cut = edit_dir / (f"cutout_{key}.webm" if key else f"hook_cutout_{seconds + 0.3:.2f}s.webm")
    if cut.exists() and (key or cut.stat().st_mtime > base_path.stat().st_mtime):
        return cut
    run(["ffmpeg", "-y", "-i", str(base_path), "-t", f"{seconds + 0.3:.3f}", "-an", "-c:v", "libx264",
         "-crf", "12", "-pix_fmt", "yuv420p", str(clip)], quiet=True)
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    if engine == "rvm":   # temporal matting: no edge flicker (tools/matting)
        print("person mask (Robust Video Matting, CPU) ...")
        subprocess.run(["uv", "run", "--project", str(MATTING_DIR), "python", str(MATTING_DIR / "rvm.py"),
                        str(clip), str(cut)], check=True, env=env)
        return cut
    print("person cutout for the hook (remove-background, CPU) ...")
    subprocess.run(["npx", "--yes", "hyperframes@0.8.157", "remove-background", str(clip), "-o", str(cut),
                    "--quality", "best"], check=True, env=env, shell=os.name == "nt")
    return cut


def mask_key(ranges: list[dict], reframe: float | None, seconds: float, engine: str = "u2net") -> str:
    """Cache key for a person mask: what was cut (sources, times, zooms) and by which matting engine, not how it
    was graded."""
    import hashlib
    cut = [[r["source"], float(r["start"]), float(r["end"]), r.get("zoom")] for r in ranges]
    key = hashlib.sha1(json.dumps([cut, reframe, round(seconds, 2)]).encode()).hexdigest()[:10]
    return key if engine == "u2net" else f"{key}_{engine}"


TRANS_S = {"whip": 0.15, "zoom": 0.2, "flash": 0.07, "leak": 0.22, "wipe": 0.18}   # half-length (s) each side of the cut


def transition_filters(current: str, out_label: str, kind: str, t: float, n: int, w: int, h: int,
                       fps: int = 30) -> list[str]:
    """A transition laid over the frames around a hard cut at `t`, so cut timing and audio stay as they are.
    whip: the picture streaks out to the left and the next shot streaks in from the right (horizontal blur).
    zoom: zooms hard into the outgoing shot; the incoming shot starts zoomed and settles (zoom-through).
    flash: a white light flash peaking on the cut."""
    k, d = f"tr{n}", TRANS_S.get(kind)
    if kind == "flash":
        return [f"{current}eq=brightness='0.75*exp(-pow((t-{t:.3f})/{d:.3f},2))':eval=frame{out_label}"]
    if d is None:
        raise ValueError(f"unknown transition {kind!r} (whip, zoom, flash, leak, wipe)")
    a, b = t - d, t + d
    if kind == "wipe":   # a teal panel sweeps across, covering the cut at its middle
        x = f"if(lt(t,{t:.3f}),-W+W*pow(clip((t-{a:.3f})/{d:.3f},0,1),2),W*pow(clip((t-{t:.3f})/{d:.3f},0,1),0.5))"
        return [f"color=c=0x00B4B4:s={w}x{h}:r={fps}:d={2 * d:.3f},format=yuva420p,"
                f"tpad=start_duration={a:.3f}:color=black@0[{k}p]",
                f"{current}[{k}p]overlay=x='{x}':y=0:enable='between(t,{a:.3f},{b:.3f})'{out_label}"]
    if kind == "leak":   # a warm light leak drifts across and blooms on the cut
        return [f"color=c=0xFFB070:s={w // 4}x{h // 4}:r={fps}:d={2 * d:.3f},format=yuva420p,"
                f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                f"a='150*exp(-pow(hypot(X-W*(0.1+0.8*T/{2 * d:.3f}),Y-H*0.4)/(W*0.45),2))*sin(PI*T/{2 * d:.3f})',"
                f"scale={w}:{h},tpad=start_duration={a:.3f}:color=black@0[{k}l]",
                f"{current}eq=brightness='0.25*exp(-pow((t-{t:.3f})/0.08,2))':eval=frame[{k}e]",
                f"[{k}e][{k}l]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'{out_label}"]
    window = f"trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS"
    pad = f"format=yuva420p,tpad=start_duration={a:.3f}:color=black@0"
    if kind == "whip":
        s = (f"if(lt(t,{t:.3f}),-W*0.18*pow(clip((t-{a:.3f})/{d:.3f},0,1),2),"
             f"W*0.18*pow(1-clip((t-{t:.3f})/{d:.3f},0,1),2))")
        layer = f"[{k}s]{window},scale=iw*1.4:ih*1.4,avgblur=sizeX=70:sizeY=1,{pad}[{k}l]"
        place = f"x='-(w-W)/2+{s}':y='-(h-H)/2'"
    else:  # zoom
        z = f"if(lt(it,{d:.3f}),1+0.7*pow(it/{d:.3f},2),1+0.7*pow(1-(it-{d:.3f})/{d:.3f},2))"
        layer = (f"[{k}s]{window},zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={w}x{h}:fps={fps},"
                 f"gblur=sigma=5,{pad}[{k}l]")
        place = "x=0:y=0"
    return [f"{current}split[{k}m][{k}s]", layer,
            f"[{k}m][{k}l]overlay={place}:enable='between(t,{a:.3f},{b:.3f})'{out_label}"]


def xray_filters(current: str, out_label: str, start: float, duration: float, n: int, scan: float = 0.45) -> list[str]:
    """X-ray look (inverted, teal, glowing edges) revealed by a scan line moving down from `start`, held to the end."""
    k, end = f"xr{n}", start + duration
    return [
        f"{current}split[{k}m][{k}s]",
        f"[{k}s]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,format=gray,negate,"
        f"curves=all='0/0 0.45/0.12 1/1',format=gbrp,split[{k}a][{k}b]",
        f"[{k}b]edgedetect=low=0.06:high=0.18,format=gbrp[{k}e]",
        f"[{k}a][{k}e]blend=all_mode=screen,colorchannelmixer=rr=0.15:gg=0.85:bb=0.85,format=yuva420p,"
        f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='255*lt(Y,H*clip(T/{scan:.3f},0,1))',"
        f"tpad=start_duration={start:.3f}:color=black@0[{k}x]",
        f"[{k}m][{k}x]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})',"
        f"drawbox=x=0:y='ih*clip((t-{start:.3f})/{scan:.3f},0,1)-4':w=iw:h=8:color=0x00E5E5@0.9:t=fill"
        f":enable='between(t,{start:.3f},{start + scan:.3f})'{out_label}",
    ]


SFX_REL_DB = -15   # default: an effect's loudest moment sits 15 dB under the voice (Milan, round 7)


def sfx_gain(voice_lufs: float, sfx_peak_lufs: float, rel_db: float = SFX_REL_DB) -> float:
    """Gain (dB) that puts an SFX's loudest moment rel_db under the voice's integrated loudness."""
    return min(0.0, voice_lufs + rel_db - sfx_peak_lufs)   # never boost: a bad reading must not blow the mix up


def ebur128_levels(path: Path) -> tuple[float | None, float | None]:
    """(integrated LUFS, loudest momentary LUFS) of a file's audio, or None where unmeasurable."""
    # apad: the momentary meter needs 400 ms, so a 0.2 s hit would read as near-silence and get a huge gain
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "apad=pad_dur=0.5,ebur128",
                        "-f", "null", "-"], capture_output=True, text=True)
    err = r.stderr
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    ms = [float(m) for m in re.findall(r"\bM:\s*(-?[\d.]+)", err[:err.rfind("Summary:")] if summary else err)]
    return (float(i.group(1)) if i else None, max(ms) if ms else None)


def bg_zoom_expr(windows: list[tuple[float, float, float]]) -> str:
    """zoompan z for the background: the punch-in zoom inside each (start, end, zoom) window, else 1."""
    z = "1"
    for a, b, f in windows:
        z = f"if(between(it,{a:.3f},{b:.3f}),{f:g},{z})"
    return z


def bubble_layer(current: str, out_main: str, out_bubble: str, e: dict, n: int) -> list[str]:
    """Picture-in-picture: a round crop of the footage (crop [x, y, side]) scaled to `size`, made from the frames
    before any overlay so it can sit on top of a full-frame insert graphic."""
    k, start, end = f"bb{n}", float(e["start"]), float(e["start"]) + float(e["duration"])
    if "w" in e:   # wide rounded box: crop [x, y, w, h] scaled to w x h, corner radius
        cx, cy, cw, ch = e["crop"]
        bw, bh, r = int(e["w"]), int(e["h"]), int(e.get("radius", 36))
        shape = f"crop={cw}:{ch}:{cx}:{cy},scale={bw}:{bh}"
        alpha = f"255*lte(hypot(max(abs(X-W/2)-(W/2-{r}),0),max(abs(Y-H/2)-(H/2-{r}),0)),{r})"
    else:          # round bubble: crop [x, y, side] scaled to size
        cx, cy, cs = e["crop"]
        size = int(e["size"])
        shape = f"crop={cs}:{cs}:{cx}:{cy},scale={size}:{size}"
        alpha = "255*lte(hypot(X-W/2,Y-H/2),W/2-1)"
    return [
        f"{current}split{out_main}[{k}s]",
        f"[{k}s]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,{shape},"
        f"format=yuva420p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='{alpha}',"
        f"tpad=start_duration={start:.3f}:color=black@0{out_bubble}",
    ]


def effective_zooms(ranges: list[dict], reframe: float | None) -> list[float]:
    """Per-range zoom. With EDL "reframe" (e.g. 1.15) plain ranges alternate wide / tight,
    a one-camera stand-in for a second angle. An explicit range zoom wins and counts as tight."""
    zooms, prev_tight = [], True  # so the first plain range stays wide
    for r in ranges:
        if r.get("zoom"):
            zooms.append(float(r["zoom"]))
            prev_tight = True
        elif reframe:
            zooms.append(1.0 if prev_tight else float(reframe))
            prev_tight = not prev_tight
        else:
            zooms.append(1.0)
    return zooms


def subtitles_filter_path(path: str) -> str:
    """Path as ffmpeg's subtitles filter needs it on any OS.

    Backslashes are escape characters inside a filter graph, so Windows paths
    lose them silently; forward slashes work on Windows too. The drive colon and
    quotes still need escaping.
    """
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


MIN_CUE_S = 0.05
CUE_GAP_CLOSE_S = 0.25


def finalize_cues(entries: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Sort cues and stop them overlapping: two cues on screen at once stack
    into an unreadable block. A cue squeezed to a flash keeps its words by
    joining the next cue (or the previous one, at the end)."""
    entries = sorted(entries, key=lambda e: e[0])
    out: list[tuple[float, float, str]] = []
    carry: tuple[float, str] | None = None
    for i, (a, b, t) in enumerate(entries):
        if carry:
            a, t = carry[0], f"{carry[1]} {t}"
            carry = None
        if i + 1 < len(entries):
            b = min(b, entries[i + 1][0])
            if b - a < MIN_CUE_S:
                carry = (a, t)
                continue
        elif b - a < MIN_CUE_S and out:
            pa, _, pt = out.pop()
            a, t = pa, f"{pt} {t}"
        out.append((a, b, t))
    return out


KEYWORD_TOLERANCE_S = 0.06


FONTS_DIR = Path(__file__).resolve().parents[1] / "fonts"


def subtitles_filter(subs_path: Path, fonts_dir: Path) -> str:
    """libass filter: bundled brand fonts always; the legacy SRT style only for .srt
    (an .ass file carries its own styles)."""
    f = (f"subtitles='{subtitles_filter_path(str(subs_path))}'"
         f":fontsdir='{subtitles_filter_path(str(fonts_dir))}'")
    if subs_path.suffix.lower() != ".ass":
        f += f":force_style='{SUB_FORCE_STYLE}'"
    return f


def build_master_srt(edl: dict, edit_dir: Path, out_path: Path,
                     frame_size: tuple[int, int] | None = None,
                     seg_durations: list[float] | None = None) -> None:
    """Build output-timeline subtitles from per-source transcripts.

    - phrase-aware ~2-word chunks (see chunk_words)
    - UPPERCASE text
    - Output times computed as word.start - segment_start + segment_offset
    - out_path ending in .ass (frame_size required): brand styles, EDL
      "keywords" ([{"source", "t": word start}]) in teal, EDL "hook_title"
      ({"text", "seconds"}) as a box at the top. Otherwise plain SRT.
    - seg_durations: the extracted segments' real lengths (each is rounded to
      whole frames). When given, segment offsets follow them instead of
      end - start, so captions don't drift ahead of the voice cut by cut.
    """
    as_ass = out_path.suffix.lower() == ".ass"
    sentence = edl.get("captions") == "sentence"
    keywords = [(k["source"], float(k["t"])) for k in edl.get("keywords", [])]

    def is_keyword(src: str, w: dict) -> bool:
        return any(s == src and abs(float(w.get("start", -1)) - t) <= KEYWORD_TOLERANCE_S
                   for s, t in keywords)

    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]

    entries: list[tuple[float, float, str]] = []
    seg_offset = 0.0

    for i, r in enumerate(edl["ranges"]):
        src_name = r["source"]
        seg_start = float(r["start"])
        seg_end = float(r["end"])
        seg_duration = seg_durations[i] if seg_durations else seg_end - seg_start

        tr_path = transcripts_dir / f"{src_name}.json"
        if not tr_path.exists():
            print(f"  no transcript for {src_name}, skipping captions for this segment")
            seg_offset += seg_duration
            continue

        transcript = json.loads(tr_path.read_text(encoding="utf-8"))
        words_in_seg = _words_in_range(transcript, seg_start, seg_end)

        for chunk in (chunk_sentences if sentence else chunk_words)(words_in_seg):
            if as_ass and edl.get("captions") == "active":
                entries += active_word_events(chunk, seg_start, seg_offset, seg_end, edl.get("brand"))
                continue
            local_start = max(seg_start, chunk[0].get("start", seg_start))
            local_end = min(seg_end, chunk[-1].get("end", seg_end))
            out_start = max(0.0, local_start - seg_start) + seg_offset
            out_end = max(0.0, local_end - seg_start) + seg_offset
            if out_end <= out_start:
                out_end = out_start + 0.4
            if as_ass:
                parts = [((w.get("text") or "").strip(), is_keyword(src_name, w)) for w in chunk]
                if parts:
                    parts[-1] = (parts[-1][0].rstrip(",;:"), parts[-1][1])
                text = ass_captions.caption_text(parts, upper=not sentence)
            else:
                text = " ".join((w.get("text") or "").strip() for w in chunk)
                text = re.sub(r"\s+", " ", text).strip()
                # Strip trailing punctuation for cleaner uppercase look
                text = text.rstrip(",;:")
                text = text.upper()
            entries.append((out_start, out_end, text))

        seg_offset += seg_duration

    entries = finalize_active(entries) if edl.get("captions") == "active" else finalize_cues(entries)
    if as_ass:
        if frame_size is None:
            raise ValueError("an .ass subtitle file needs frame_size (width, height)")
        ass_captions.write_ass(out_path, frame_size[0], frame_size[1], entries, edl.get("hook_title"),
                               style="Sentence" if sentence else "Caption",
                               watermark=edl.get("watermark"), total=seg_offset, brand=edl.get("brand"))
        print(f"master ASS → {out_path.name} ({len(entries)} cues"
              f"{', hook title' if edl.get('hook_title') else ''})")
        return
    lines: list[str] = []
    for i, (a, b, t) in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(a)} --> {_srt_timestamp(b)}")
        lines.append(t)
        lines.append("")
    out_path.write_text("\n".join(lines))
    print(f"master SRT → {out_path.name} ({len(entries)} cues)")


def real_output_time(t: float, ranges: list[dict], seg_durations: list[float]) -> float:
    """Map a time on the EDL's nominal timeline (sum of end - start) to the
    rendered one (sum of the real, frame-rounded segment lengths)."""
    nominal = real = 0.0
    for r, actual in zip(ranges, seg_durations):
        length = float(r["end"]) - float(r["start"])
        if t < nominal + length:
            return real + (t - nominal)
        nominal += length
        real += actual
    return real + (t - nominal)


def map_overlays(overlays: list[dict], ranges: list[dict], seg_durations: list[float]) -> list[dict]:
    """Overlay windows are authored on the nominal timeline; move them to the real one."""
    mapped = []
    for ov in overlays:
        start = float(ov["start_in_output"])
        new_start = real_output_time(start, ranges, seg_durations)
        new_end = real_output_time(start + float(ov["duration"]), ranges, seg_durations)
        mapped.append({**ov, "start_in_output": new_start, "duration": new_end - new_start})
    return mapped


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# -------- Loudness normalization (social-ready audio) -----------------------


# Social-media standard: -14 LUFS integrated, -1 dBTP peak, LRA 11 LU.
# Matches YouTube / Instagram / TikTok / X / LinkedIn normalization targets.
LOUDNORM_I = -14.0
LOUDNORM_TP = -1.0
LOUDNORM_LRA = 11.0
# The AAC encode after loudnorm overshoots true peak by ~0.3 dB (measured on a
# real take: a -1.0 target delivered -0.7). Aim lower so the file lands under -1.
AAC_HEADROOM_DB = 0.5


def loudnorm_filter(measurement: dict[str, str] | None = None) -> str:
    """loudnorm args: one-pass/measuring form, or the linear second pass."""
    f = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP - AAC_HEADROOM_DB}:LRA={LOUDNORM_LRA}"
    if measurement is None:
        return f
    return (
        f"{f}:measured_I={measurement['input_i']}"
        f":measured_TP={measurement['input_tp']}"
        f":measured_LRA={measurement['input_lra']}"
        f":measured_thresh={measurement['input_thresh']}"
        f":offset={measurement['target_offset']}"
        f":linear=true"
    )


def measure_loudness(video_path: Path) -> dict[str, str] | None:
    """Run ffmpeg loudnorm first pass and parse the JSON measurement.

    Returns a dict with measured_i, measured_tp, measured_lra, measured_thresh,
    target_offset, or None if measurement failed.
    """
    filter_str = f"{loudnorm_filter()}:print_format=json"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(video_path),
        "-af", filter_str,
        "-vn", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # loudnorm prints the JSON to stderr at the end of the run
    stderr = proc.stderr

    # Find the JSON block — loudnorm output contains a `{ ... }` block
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stderr[start : end + 1])
    except json.JSONDecodeError:
        return None
    needed = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not needed.issubset(data.keys()):
        return None
    return data


def apply_loudnorm_two_pass(
    input_path: Path,
    output_path: Path,
    preview: bool = False,
) -> bool:
    """Run two-pass loudnorm on input_path, write normalized copy to output_path.

    Returns True on success, False if measurement failed (caller should fall
    back to copying the input unchanged).

    In preview mode, skips the measurement pass and uses a one-pass approximation
    for speed. Final mode always does the proper two-pass.
    """
    if preview:
        # One-pass approximation — faster, slightly less accurate.
        filter_str = loudnorm_filter()
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-nostats",
            "-i", str(input_path),
            "-c:v", "copy",
            "-af", filter_str,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(output_path),
        ]
        print(f"  loudnorm (1-pass preview) → {output_path.name}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True

    # Full two-pass
    print(f"  loudnorm pass 1: measuring {input_path.name}")
    measurement = measure_loudness(input_path)
    if measurement is None:
        print("  loudnorm measurement failed — falling back to 1-pass")
        return apply_loudnorm_two_pass(input_path, output_path, preview=True)

    print(f"    measured: I={measurement['input_i']} LUFS  "
          f"TP={measurement['input_tp']}  LRA={measurement['input_lra']}")

    # brick-wall after the linear gain (SFX transients would otherwise poke above the true-peak target). Resample
    # to 48k FIRST: loudnorm runs at 192k, and resampling after the limiter recreated the peaks it had removed.
    filter_str = f"{loudnorm_filter(measurement)},aresample=48000,alimiter=limit=0.79:attack=5:release=50:level=false"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(input_path),
        "-c:v", "copy",
        "-af", filter_str,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(output_path),
    ]
    print(f"  loudnorm pass 2: normalizing → {output_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return True


# -------- Final compositing (Rule 1 + Rule 4) -------------------------------


def build_final_composite(
    base_path: Path,
    overlays: list[dict],
    subtitles_path: Path | None,
    out_path: Path,
    edit_dir: Path,
    speed: float = 1.0,
    hook_behind: dict | None = None,
    fonts_dir: Path | None = None,
    transitions: list[dict] | None = None,
    effects: list[dict] | None = None,
    background: dict | None = None,
    fps: int = 30,
    sfx: list[dict] | None = None,
) -> None:
    """Final pass: base → overlays (shifted to their window) → subtitles LAST → speed → out.

    An overlay's optional "fade_out" (seconds) dissolves it into the base at the
    end of its window. `speed` > 1 plays the finished cut faster, pitch kept
    (rubberband); captions and overlays are already burned in, so they stay in sync.
    If there are no overlays, no subtitles and no speed change, just copy base to out.
    """
    has_overlays = bool(overlays)
    has_subs = subtitles_path is not None and subtitles_path.exists()

    transitions, effects = transitions or [], effects or []
    sfx = sfx or []
    if not (has_overlays or has_subs or speed != 1.0 or hook_behind or transitions or effects or background or sfx):
        # Nothing to do — just rename/copy base to final name
        run(["ffmpeg", "-y", "-i", str(base_path), "-c", "copy", str(out_path)], quiet=True)
        return

    inputs: list[str] = ["-i", str(base_path)]
    for ov in overlays:
        inputs += ["-i", str(resolve_path(ov["file"], edit_dir))]
    nxt = len(overlays) + 1
    W, H = probe_frame_size(base_path)

    filter_parts: list[str] = []
    current = "[0:v]"
    # Person layer: the footage with the person mask as alpha (mask = remove-background cutout, grade-independent)
    hook_cut = bool(hook_behind and hook_behind.get("cutout"))
    mask = (background or {}).get("mask") or (hook_behind or {}).get("cutout")
    uses = int(bool(background)) + int(hook_cut)
    if mask and uses:
        inputs += ["-c:v", "libvpx-vp9", "-i", str(mask)]
        filter_parts.append(f"[{nxt}:v]setpts=PTS-STARTPTS,format=yuva420p,alphaextract,setsar=1,erosion,erosion,gblur=sigma=1.2[pmask]")
        nxt += 1
        filter_parts.append(f"{current}setsar=1,split[pbase][psrc]")
        filter_parts.append("[psrc][pmask]alphamerge" + (f",split={uses}" if uses > 1 else "")
                            + "".join(f"[p{i}]" for i in range(uses)))
        current = "[pbase]"
    person = iter(f"[p{i}]" for i in range(uses))
    # Background swap: backdrop image under the person
    if background:
        inputs += ["-loop", "1", "-framerate", str(fps), "-i", str(resolve_path(str(background["file"]), edit_dir))]
        zoom = bg_zoom_expr(background.get("zooms") or [])
        zp = (f",zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps}"
              if zoom != "1" else "")
        filter_parts.append(f"[{nxt}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
                            f"{zp},format=yuv420p[bgi]")
        nxt += 1
        filter_parts.append(f"{current}[bgi]overlay=0:0:shortest=1[bgu]")
        cur_bg = "[bgu]"
        for idx, ov in enumerate(overlays, start=1):   # graphics behind the person, in front of the backdrop
            if ov.get("layer") == "behind":
                t0 = float(ov["start_in_output"])
                filter_parts.append(f"{cur_bg}[a{idx}]overlay=0:0:enable='between(t,{t0:.3f},"
                                    f"{t0 + float(ov['duration']):.3f})'[bh{idx}]")
                cur_bg = f"[bh{idx}]"
        filter_parts.append(f"{cur_bg}{next(person)}overlay=0:0:eof_action=pass[bgc]")
        current = "[bgc]"
    # Text behind the head: title on the picture, then the person back on top
    if hook_cut:
        secs = float(hook_behind.get("seconds", 3))
        filter_parts.append(hook_behind_text(current, "[hbt]", hook_behind["lines"], secs, int(hook_behind["height"]),
                                             int(hook_behind["width"]), hook_behind.get("color", "0xE9E8E4"),
                                             float(hook_behind.get("top", 0.17)), bool(hook_behind.get("fill")),
                                             bool(hook_behind.get("shadow")), hook_behind.get("font_file"),
                                             float(hook_behind.get("em", 0.62))))
        filter_parts.append(f"[hbt]{next(person)}overlay=0:0:eof_action=pass:enable='between(t,0,{secs:.3f})'[hb]")
        current = "[hb]"

    # Frame effects on the footage, before graphics go on top
    bubbles = []
    for n, e in enumerate(effects):
        if e["type"] == "xray":
            filter_parts += xray_filters(current, f"[xo{n}]", float(e["start"]), float(e["duration"]), n)
            current = f"[xo{n}]"
        elif e["type"] == "bubble":
            filter_parts += bubble_layer(current, f"[bm{n}]", f"[bl{n}]", e, n)
            current = f"[bm{n}]"
            bubbles.append((n, e))
        else:
            raise ValueError(f"unknown effect {e['type']!r} (xray, bubble)")

    # Shift every overlay so its frame 0 lands at start_in_output. Pad the front
    # with transparent frames rather than offsetting PTS: on a real phone render
    # (concat base, 30.003 fps) a setpts offset made the overlay play ~0.9s
    # early, while padding kept it frame-exact (measured 2026-10-14).
    xexpr: dict[int, str] = {}
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        if ov.get("exit") == "whip":
            parts, xexpr[idx] = whip_exit(idx, t, float(ov["duration"]))
            filter_parts += parts
            continue
        fade = ""
        if ov.get("fade_out"):
            fo = float(ov["fade_out"])
            fade = f",format=yuva420p,fade=t=out:st={float(ov['duration']) - fo:.3f}:d={fo:.3f}:alpha=1"
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS{fade},tpad=start_duration={t:.3f}:color=black@0[a{idx}]")

    def chain(cur: str, over_captions: bool) -> str:
        for idx, ov in enumerate(overlays, start=1):
            if bool(ov.get("over_captions")) != over_captions or (background and ov.get("layer") == "behind"):
                continue
            t = float(ov["start_in_output"])
            end = t + float(ov["duration"])
            x = f"x={xexpr[idx]}:y=0:" if idx in xexpr else ""
            filter_parts.append(f"{cur}[a{idx}]overlay={x}enable='between(t,{t:.3f},{end:.3f})'[v{idx}]")
            cur = f"[v{idx}]"
            if idx in xexpr:  # the next shot settles in from the right
                filter_parts.extend(whip_settle(cur, f"[w{idx}]", end))
                cur = f"[w{idx}]"
        return cur

    current = chain(current, over_captions=False)
    for n, e in bubbles:
        s, d = float(e["start"]), float(e["duration"])
        filter_parts.append(f"{current}[bl{n}]overlay={int(e['x'])}:{int(e['y'])}"
                            f":enable='between(t,{s:.3f},{s + d:.3f})'[bo{n}]")
        current = f"[bo{n}]"
    for n, tr in enumerate(transitions):
        filter_parts += transition_filters(current, f"[tv{n}]", tr["type"], float(tr["t"]), n, W, H, fps)
        current = f"[tv{n}]"

    # Subtitles LAST — Rule 1 (speed only retimes the finished picture). Exception: a full-frame takeover graphic
    # marked over_captions goes on top, so the captions don't repeat the words it shows.
    if has_subs:
        filter_parts.append(f"{current}{subtitles_filter(subtitles_path.resolve(), fonts_dir or FONTS_DIR)}[subbed]")
        current = "[subbed]"
    current = chain(current, over_captions=True)
    speed_vf = f"setpts=PTS/{speed}" if speed != 1.0 else "null"
    filter_parts.append(f"{current}{speed_vf}[outv]")

    # Sound effects: each placed at its composite time, mixed under the voice, then the speed change on the whole mix.
    # Level: "gain_db" if given, else measured so its loudest moment sits rel_db (default -15) under the voice.
    amap = "0:a"
    voice = ebur128_levels(base_path)[0] if any("gain_db" not in e for e in sfx) else None
    if sfx:
        for i, e in enumerate(sfx):
            if "gain_db" not in e:
                peak = ebur128_levels(resolve_path(str(e["file"]), edit_dir))[1]
                e = {**e, "gain_db": sfx_gain(voice, peak, float(e.get("rel_db", SFX_REL_DB)))
                     if voice is not None and peak is not None else -24}
            inputs += ["-i", str(resolve_path(str(e["file"]), edit_dir))]
            ms = max(0, round((float(e["t"]) - float(e.get("apex", 0))) * 1000))
            filter_parts.append(f"[{nxt}:a]aresample=48000,aformat=channel_layouts=stereo,"
                                f"volume={float(e.get('gain_db', -6)):g}dB,adelay={ms}|{ms}[sx{i}]")
            nxt += 1
        filter_parts.append("[0:a]aresample=48000,aformat=channel_layouts=stereo[vo];[vo]"
                            + "".join(f"[sx{i}]" for i in range(len(sfx)))
                            + f"amix=inputs={len(sfx) + 1}:duration=first:normalize=0[mix]")
        amap = "[mix]"
    if sfx and speed != 1.0:   # -af can't follow a filter_complex output: speed the mix inside the graph
        filter_parts.append(f"[mix]rubberband=tempo={speed}[mixs]")
        amap = "[mixs]"
        audio = ["-c:a", "aac", "-b:a", "192k"]
    elif speed != 1.0:
        audio = ["-af", f"rubberband=tempo={speed}", "-c:a", "aac", "-b:a", "192k"]
    else:
        audio = ["-c:a", "aac", "-b:a", "192k"] if sfx else ["-c:a", "copy"]
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        "-map", amap,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        *audio,
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"compositing → {out_path.name}")
    print(f"  overlays: {len(overlays)}, subtitles: {'yes' if has_subs else 'no'}"
          f"{f', speed x{speed}' if speed != 1.0 else ''}")
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode:
        sys.exit("composite failed: " + r.stderr.decode(errors="replace")[-3000:] + " | filter: " + ";".join(filter_parts))


# -------- Main ---------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a video from an EDL")
    ap.add_argument("edl", type=Path, help="Path to edl.json")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output video path")
    ap.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: 1080p, medium, CRF 22 — evaluable for QC, faster than final.",
    )
    ap.add_argument(
        "--draft",
        action="store_true",
        help="Draft mode: 720p, ultrafast, CRF 28 — cut-point verification only.",
    )
    ap.add_argument(
        "--build-subtitles",
        action="store_true",
        help="Build master.srt from transcripts + EDL offsets before compositing",
    )
    ap.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip subtitles even if the EDL references one",
    )
    ap.add_argument(
        "--no-loudnorm",
        action="store_true",
        help="Skip audio loudness normalization. Default is on (-14 LUFS, -1 dBTP, LRA 11).",
    )
    ap.add_argument(
        "--no-clean-audio",
        action="store_true",
        help="Skip background-noise cleanup. Default is on (RNNoise + 25%% original, cached in clean/).",
    )
    ap.add_argument(
        "--fps",
        type=parse_fps,
        default=None,
        help="Output frame rate. Default: preserve the source's frame rate "
             "(falls back to 24 if it can't be probed). Pass e.g. --fps 30 or "
             "--fps 30000/1001 to force.",
    )
    args = ap.parse_args()

    edl_path = args.edl.resolve()
    if not edl_path.exists():
        sys.exit(f"edl not found: {edl_path}")

    edl = json.loads(edl_path.read_text())
    edit_dir = edl_path.parent
    out_path = args.output.resolve()

    # 0. Clean background noise once per source, before any cut
    edl = prepare_sources(edl, edit_dir, clean=not args.no_clean_audio)

    # 1. Extract per-segment (auto-grade per range if EDL grade is "auto")
    segment_paths = extract_all_segments(
        edl, edit_dir, preview=args.preview, draft=args.draft, fps=args.fps
    )

    # 2. Concat → base
    if args.draft:
        base_name = "base_draft.mp4"
    elif args.preview:
        base_name = "base_preview.mp4"
    else:
        base_name = "base.mp4"
    base_path = edit_dir / base_name
    concat_segments(segment_paths, base_path, edit_dir)
    # the concat demuxer places each segment after the previous file's real length
    seg_durations = [probe_duration(p) for p in segment_paths]

    # 3. Subtitles: build if requested, resolve final path
    subs_path: Path | None = None
    if not args.no_subtitles:
        if args.build_subtitles:
            subs_path = edit_dir / "master.ass"
            build_master_srt(edl, edit_dir, subs_path, frame_size=probe_frame_size(base_path),
                             seg_durations=seg_durations)
        elif edl.get("subtitles"):
            subs_path = resolve_subtitles_path(edl["subtitles"], edit_dir)

    # 4. Composite (overlays + subtitles LAST) → intermediate (pre-loudnorm) path
    overlays = map_overlays(edl.get("overlays") or [], edl["ranges"], seg_durations)
    speed = float(edl.get("speed", 1.0))
    brand = edl.get("brand") or {}
    fonts_dir = resolve_path(brand["fonts_dir"], edit_dir) if brand.get("fonts_dir") else None
    # Person mask: the whole cut when the background is swapped, else just the hook seconds
    starts = [sum(seg_durations[:i]) for i in range(len(seg_durations) + 1)]
    background = None
    if edl.get("background"):
        total = starts[-1]
        engine = edl["background"].get("matting", "u2net")
        background = {"file": edl["background"]["file"],
                      "mask": make_cutout(base_path, total, edit_dir,
                                          mask_key(edl["ranges"], edl.get("reframe"), total, engine), engine)}
    hook_behind = None
    if edl.get("hook_behind"):
        hb = edl["hook_behind"]
        secs = float(hb.get("seconds", 3))
        fw, fh = probe_frame_size(base_path)
        cut = background["mask"] if background else make_cutout(base_path, secs, edit_dir,
                                                                  mask_key(edl["ranges"], edl.get("reframe"), secs))
        hook_behind = {"lines": hb["lines"], "seconds": secs, "height": fh, "width": fw,
                       "color": hb.get("color", "0xE9E8E4"), "top": hb.get("top", 0.17),
                       "fill": hb.get("fill"), "shadow": hb.get("shadow"), "font_file": hb.get("font_file"),
                       "em": hb.get("em", 0.62), "cutout": cut}
    # Transitions sit on cuts ({"cut": i} = the cut into range i); effects on ranges ({"range": i})
    transitions = [{**tr, "t": starts[int(tr["cut"])] if "cut" in tr else starts[int(tr["range"])] + float(tr.get("offset", 0))}
                   for tr in edl.get("transitions") or []]
    effects = []
    for e in edl.get("effects") or []:
        r = int(e["range"])
        start = starts[r] + float(e.get("offset", 0))
        effects.append({**e, "start": start, "duration": float(e.get("duration", starts[r + 1] - start))})
    # SFX: {"file", "t"} or {"cut": i} or {"range": i, "offset": s}; "apex" = where in the file the hit is
    sfx = []
    for e in edl.get("sfx") or []:
        t = e.get("t")
        if t is None:
            t = starts[int(e["cut"])] if "cut" in e else starts[int(e["range"])] + float(e.get("offset", 0))
        sfx.append({**e, "t": float(t)})
    if background:   # the backdrop zooms with every punch-in, like a real camera move
        zs = effective_zooms(edl["ranges"], edl.get("reframe"))
        background["zooms"] = [(starts[i], starts[i + 1], z) for i, z in enumerate(zs) if z > 1.0]
    fx = {"transitions": transitions, "effects": effects, "background": background, "sfx": sfx}
    if args.no_loudnorm:
        # Composite directly to final output
        build_final_composite(base_path, overlays, subs_path, out_path, edit_dir, speed, hook_behind, fonts_dir, **fx)
    else:
        # Composite to a temp file, then run loudnorm → final output
        tmp_composite = out_path.with_suffix(".prenorm.mp4")
        build_final_composite(base_path, overlays, subs_path, tmp_composite, edit_dir, speed, hook_behind, fonts_dir,
                              **fx)
        print("loudness normalization → social-ready (-14 LUFS / -1 dBTP / LRA 11)")
        apply_loudnorm_two_pass(tmp_composite, out_path, preview=args.draft)
        tmp_composite.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\ndone: {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
