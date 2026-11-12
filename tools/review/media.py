"""ffmpeg work for the review app: review copies, filmstrip sprite, waveform peaks, stills, fix-check assets.

Review copies are exact constant frame rate and all-intra (every frame a keyframe), so the browser lands on
the exact frame on every seek. Masters are never touched; every output is write-once.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from fractions import Fraction
from pathlib import Path

DEFAULT_WINDOWS = {"picture_frames": 4, "sound_seconds": 2, "cut_seconds": 1}
PAIRS_MAX_FRAMES = 24
GAP_SECONDS = 0.5
X264_INTRA = ["-c:v", "libx264", "-crf", "16", "-preset", "veryfast", "-g", "1", "-keyint_min", "1",
              "-pix_fmt", "yuv420p"]


class MediaError(Exception):
    pass


def _run(cmd: list[str]) -> bytes:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        err = r.stderr.decode(errors="replace").strip().splitlines()
        raise MediaError(f"{cmd[0]} failed: {' | '.join(err[-3:]) or 'exit ' + str(r.returncode)}")
    return r.stdout


def probe(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-of", "json", "-show_entries",
                "stream=codec_type,width,height,avg_frame_rate,nb_frames:format=duration", str(path)])
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    dur = float(info["format"].get("duration", 0))
    fps = v.get("avg_frame_rate", "0/1")
    nb = v.get("nb_frames")
    frames = int(nb) if nb and nb.isdigit() else round(dur * float(Fraction(fps))) if fps != "0/0" else 0
    return {"fps": fps, "width": int(v["width"]), "height": int(v["height"]), "duration": dur,
            "frames": frames, "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def snap_fps(rate: str) -> str:
    f = float(Fraction(rate))
    ntsc = round(f * 1001 / 1000)
    if ntsc and abs(f - ntsc * 1000 / 1001) / f <= 0.0002:
        return f"{ntsc * 1000}/1001"
    n = round(f)
    if n and abs(f - n) / n <= 0.001:
        return f"{n}/1"
    fr = Fraction(rate).limit_denominator(1001)
    return f"{fr.numerator}/{fr.denominator}"


def _tmp_then_replace(dst: Path, build) -> None:
    dst = Path(dst)
    if dst.exists():
        raise FileExistsError(f"{dst.name} already exists (review files are write-once)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".part" + dst.suffix)
    build(tmp)
    os.replace(tmp, dst)


def make_review_copy(src: Path, dst: Path, fps: str) -> None:
    has_audio = probe(src)["has_audio"]

    def build(tmp):
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-vf", f"fps={fps}", "-r", fps,
               *X264_INTRA]
        if has_audio:
            cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-movflags", "+faststart", str(tmp)]
        _run(cmd)

    _tmp_then_replace(dst, build)


def make_sprite(review: Path, dst: Path, fps: str, every: int = 10, thumb_h: int = 96) -> dict:
    p = probe(review)
    count = max(1, math.ceil(p["frames"] / every))
    thumb_w = max(2, round(p["width"] * thumb_h / p["height"] / 2) * 2)
    cols = min(count, 10)
    rows = math.ceil(count / cols)

    def build(tmp):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(review), "-vf",
              f"select='not(mod(n\\,{every}))',scale={thumb_w}:{thumb_h},tile={cols}x{rows}",
              "-frames:v", "1", "-q:v", "4", str(tmp)])

    _tmp_then_replace(dst, build)
    return {"every": every, "cols": cols, "thumb_w": thumb_w, "thumb_h": thumb_h, "count": count}


def make_peaks(review: Path, dst: Path, per_second: int = 100) -> int:
    rate = 8000
    vals: list[float] = []
    if probe(review)["has_audio"]:
        pcm = _run(["ffmpeg", "-v", "error", "-i", str(review), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"])
        n = len(pcm) // 2
        samples = memoryview(pcm).cast("h")
        step = rate // per_second
        for i in range(0, n, step):
            chunk = samples[i:i + step]
            vals.append(round(max(abs(min(chunk)), abs(max(chunk))) / 32768, 3))
    _tmp_then_replace(dst, lambda tmp: Path(tmp).write_text(json.dumps(vals), encoding="utf-8"))
    return len(vals)


def plan_still(src: Path, dst: Path, max_w: int = 540) -> None:
    """One plan still as a light jpg (any image or video's first frame)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-frames:v", "1",
          "-vf", f"scale='min({max_w},iw)':-2", "-q:v", "3", str(dst)])


def extract_stills(review: Path, frames: list[int], out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for n in frames:
        f = out_dir / f"frame-{n}.jpg"
        if not f.exists():
            _run(["ffmpeg", "-y", "-v", "error", "-i", str(review), "-vf", f"select='eq(n\\,{n})'",
                  "-frames:v", "1", "-q:v", "2", str(f)])
        files.append(f)
    return files


def pad_window(tag: str, rng: tuple[int, int], fps: float, total: int, windows: dict | None = None) -> tuple[int, int]:
    w = windows or DEFAULT_WINDOWS
    pad = {"picture": w["picture_frames"], "sound": round(w["sound_seconds"] * fps),
           "cut": round(w["cut_seconds"] * fps)}[tag]
    return max(0, rng[0] - pad), min(total - 1, rng[1] + pad)


def make_fixcheck(before: Path, after: Path, out_dir: Path, note_id: str, tag: str,
                  before_rng: tuple[int, int], after_rng: tuple[int, int], fps: str, orientation: str,
                  windows: dict | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fr = float(Fraction(fps))
    pb, pa = probe(before), probe(after)
    b0, b1 = pad_window(tag, before_rng, fr, pb["frames"], windows)
    a0, a1 = pad_window(tag, after_rng, fr, pa["frames"], windows)
    if b0 > b1 or a0 > a1:
        bad, n = (before_rng, pb["frames"]) if b0 > b1 else (after_rng, pa["frames"])
        raise ValueError(f"note {note_id}: frames {bad[0]}-{bad[1]} are past the end of the render ({n} frames); "
                         f"give 'before'/'after' ranges in the fixes file")
    size = f"scale={pb['width']}:{pb['height']}"
    stack = "hstack" if orientation == "vertical" else "vstack"
    vtrim = lambda i, s, e: f"[{i}:v]trim=start_frame={s}:end_frame={e + 1},setpts=PTS-STARTPTS"
    inputs = ["-i", str(before), "-i", str(after)]

    if tag == "sound":
        name = f"{note_id}.mp4"
        w, h = pb["width"], pb["height"]

        def aseg(i, has, s, e):
            if has:
                return f"[{i}:a]atrim=start={s / fr}:end={(e + 1) / fr},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo"
            return f"anullsrc=r=48000:cl=stereo,atrim=duration={(e - s + 1) / fr}"

        graph = ";".join([
            f"{vtrim(0, b0, b1)}[v0]", f"{aseg(0, pb['has_audio'], b0, b1)}[a0]",
            f"color=black:s={w}x{h}:r={fps}:d={GAP_SECONDS},format=yuv420p[vg]",
            f"anullsrc=r=48000:cl=stereo,atrim=duration={GAP_SECONDS}[ag]",
            f"{vtrim(1, a0, a1)},{size}[v1]", f"{aseg(1, pa['has_audio'], a0, a1)}[a1]",
            "[v0][a0][vg][ag][v1][a1]concat=n=3:v=1:a=1[v][a]",
        ])
        _tmp_then_replace(out_dir / name, lambda tmp: _run(
            ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
             "-r", fps, *X264_INTRA, "-c:a", "aac", str(tmp)]))
        return {"kind": "audio", "files": [name]}

    if tag == "picture" and max(b1 - b0, a1 - a0) + 1 <= PAIRS_MAX_FRAMES:
        pattern = out_dir / f"{note_id}-%03d.jpg"
        graph = f"{vtrim(0, b0, b1)}[v0];{vtrim(1, a0, a1)},{size}[v1];[v0][v1]{stack}=inputs=2[v]"
        _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]",
              "-q:v", "2", "-start_number", "0", str(pattern)])
        files = sorted(p.name for p in out_dir.glob(f"{note_id}-*.jpg"))
        return {"kind": "pairs", "files": files}

    name = f"{note_id}.mp4"
    graph = f"{vtrim(0, b0, b1)}[v0];{vtrim(1, a0, a1)},{size}[v1];[v0][v1]{stack}=inputs=2[v]"
    maps = ["-map", "[v]"]
    if pa["has_audio"]:  # audio from the new version
        graph += f";[1:a]atrim=start={a0 / fr}:end={(a1 + 1) / fr},asetpts=PTS-STARTPTS[a]"
        maps += ["-map", "[a]", "-c:a", "aac"]
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, *maps]
    _tmp_then_replace(out_dir / name, lambda tmp: _run([*cmd, "-r", fps, *X264_INTRA, str(tmp)]))
    return {"kind": "clip", "files": [name]}
