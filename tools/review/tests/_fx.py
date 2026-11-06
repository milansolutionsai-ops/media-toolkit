"""Test fixtures: tiny generated clips where frame N has luma N*8, so exact frames can be checked."""
import subprocess
from pathlib import Path


def make_clip(path: Path, seconds: float = 2, rate: str = "30", w: int = 64, h: int = 96, audio: bool = True) -> Path:
    vid = f"nullsrc=s={w}x{h}:r={rate},geq=lum='mod(N*8\\,256)':cb=128:cr=128"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", vid]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "10"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True)
    return path


def ffprobe_json(path: Path, *args) -> dict:
    import json
    out = subprocess.run(["ffprobe", "-v", "error", "-of", "json", *args, str(path)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def mean_luma(jpg: Path) -> float:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(jpg), "-vf", "format=gray,scale=8:8",
                          "-f", "rawvideo", "-"], check=True, capture_output=True).stdout
    return sum(out) / len(out)
