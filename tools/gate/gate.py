"""Quality gate: the measurable problems that make an edit look basic, checked before anyone watches it.

  gate.py RENDER [--ref-shots MIN MAX] [--json] [--sheets DIR [--events T1,T2] [--sweep-fps 3]]

Checks: shot lengths (pacing, optionally against a reference range), flash frames (a single frame that matches
neither neighbour: leftovers at a bad transition), loudness (-14 LUFS +/-1), true peak (<= -1 dBTP) and clicks at
cuts. Exit 0 when nothing is wrong, 1 otherwise. ffmpeg only.

--sheets writes contact sheets for the frame-by-frame look: the whole video at 3 fps plus every frame around each
cut and each --events time (title and graphic in/out). The measurable checks can't see a title over a head; these can.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

TARGET_LUFS, LUFS_TOL, MAX_TP = -14.0, 1.0, -1.0
SCENE_THRESHOLD = 10
FLASH_DIFF = 25          # mean-luma jump against both neighbours
CLICK_JUMP_DB, CLICK_WINDOW = 18.0, 0.04


def _ff(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True)


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-of", "json", "-show_entries",
                          "stream=codec_type,avg_frame_rate:format=duration", str(path)],
                         capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    return {"duration": float(info["format"]["duration"]), "fps": float(num) / float(den or 1),
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def scene_changes(path: Path) -> list[float]:
    r = _ff(["-i", str(path), "-vf", f"scdet=threshold={SCENE_THRESHOLD},metadata=print", "-an", "-f", "null", "-"])
    return [float(t) for t in re.findall(r"lavfi\.scd\.time=([\d.]+)", r.stderr.decode(errors="replace"))]


def frame_lumas(path: Path) -> list[float]:
    r = _ff(["-i", str(path), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-an", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stderr.decode(errors="replace"))]


def flash_frames(lumas: list[float]) -> list[int]:
    return [n for n in range(1, len(lumas) - 1)
            if abs(lumas[n] - lumas[n - 1]) > FLASH_DIFF and abs(lumas[n] - lumas[n + 1]) > FLASH_DIFF]


def loudness(path: Path) -> tuple[float, float] | None:
    r = _ff(["-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr.decode(errors="replace")
    summary = r[r.rfind("Summary:"):] if "Summary:" in r else ""
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not (i and tp):
        return None
    return float(i.group(1).replace("-inf", "-70")), float(tp.group(1).replace("-inf", "-70"))


def clicks_at(path: Path, cuts: list[float]) -> list[float]:
    if not cuts:
        return []
    rate, win = 48000, 480  # 10 ms windows
    pcm = _ff(["-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]).stdout
    s = memoryview(pcm).cast("h")
    db = []
    for i in range(0, len(s), win):
        chunk = s[i:i + win]
        peak = max(abs(min(chunk)), abs(max(chunk))) if len(chunk) else 0
        db.append(20 * math.log10(peak / 32768) if peak else -96.0)
    found = []
    for t in cuts:
        lo, hi = int((t - CLICK_WINDOW) * 100), int((t + CLICK_WINDOW) * 100)
        for k in range(max(1, lo), min(len(db), hi + 1)):
            if db[k] - db[k - 1] > CLICK_JUMP_DB and db[k] > -30:
                found.append(round(t, 2))
                break
    return found


def measure(path: Path, ref_shot_range: tuple[float, float] | None = None) -> dict:
    path = Path(path)
    p = _probe(path)
    cuts = scene_changes(path)
    bounds = [0.0, *cuts, p["duration"]]
    shots = [round(b - a, 3) for a, b in zip(bounds, bounds[1:]) if b - a > 0.02]
    flashes = flash_frames(frame_lumas(path))
    res = {"duration": p["duration"], "has_audio": p["has_audio"], "shots": shots,
           "median_shot": round(statistics.median(shots), 3) if shots else None, "flash_frames": flashes,
           "loudness_lufs": None, "true_peak_dbtp": None, "clicks": [], "problems": [], "notes": []}
    probs = res["problems"]
    if flashes:
        where = ", ".join(f"{n / p['fps']:.2f}s (frame {n})" for n in flashes[:8])
        probs.append(f"Flash frame{'s' if len(flashes) > 1 else ''} at {where}: a single frame that matches "
                     f"neither neighbour, usually a leftover at a transition")
    if ref_shot_range and res["median_shot"] is not None:
        lo, hi = ref_shot_range
        if res["median_shot"] < lo:
            probs.append(f"Median shot {res['median_shot']:.2f}s is faster than the reference ({lo}-{hi}s)")
        elif res["median_shot"] > hi:
            probs.append(f"Median shot {res['median_shot']:.2f}s is slower than the reference ({lo}-{hi}s)")
    if p["has_audio"]:
        lt = loudness(path)
    if p["has_audio"] and lt is None:
        res["notes"].append("Audio present but loudness couldn't be measured: check the track by ear")
    elif p["has_audio"]:
        lufs, tp = lt
        res["loudness_lufs"], res["true_peak_dbtp"] = lufs, tp
        if abs(lufs - TARGET_LUFS) > LUFS_TOL:
            probs.append(f"Loudness {lufs:.1f} LUFS, target {TARGET_LUFS:.0f} (+/-{LUFS_TOL:.0f})")
        if tp > MAX_TP:
            probs.append(f"True peak {tp:.1f} dBTP is above {MAX_TP:.0f}: it will distort on some phones")
        res["clicks"] = clicks_at(path, cuts)
        if res["clicks"]:
            probs.append("Click at cut " + ", ".join(f"{t:.2f}s" for t in res["clicks"]))
    else:
        res["notes"].append("No audio track: sound checks skipped")
    res["ok"] = not probs
    return res


EDGE_FRAMES = 6  # frames shown either side of a cut or event


def sheets(path: Path, out_dir: Path, events: list[float] = (), sweep_fps: float = 3) -> dict:
    """Contact sheets for a frame-by-frame look: the whole video at `sweep_fps` (6x3 tiles, 6s per sheet at 3 fps)
    plus every single frame around each cut and each event (title in/out, graphic edges). Edges closer than
    EDGE_FRAMES frames share one sheet. Returns {"sweep": [paths], "edges": [{"t", "first_frame", "sheet"}]}."""
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = _probe(path)
    fps, n = p["fps"], 2 * EDGE_FRAMES + 1
    for old in out_dir.glob("*.png"):
        old.unlink()
    _ff(["-y", "-v", "error", "-i", str(path), "-vf", f"fps={sweep_fps},scale=180:-2,tile=6x3:padding=4",
         "-an", str(out_dir / "sweep_%02d.png")])
    sweep = sorted(str(x) for x in out_dir.glob("sweep_*.png"))
    times = sorted({*scene_changes(path), *(float(e) for e in events)})
    merged: list[float] = []
    for t in times:
        if not merged or t - merged[-1] > EDGE_FRAMES / fps:
            merged.append(t)
    edges = []
    for t in merged:
        first = max(0, round(t * fps) - EDGE_FRAMES)
        sheet = out_dir / f"edge_{t:07.2f}s.png"
        _ff(["-y", "-v", "error", "-ss", f"{first / fps:.4f}", "-i", str(path), "-frames:v", str(n),
             "-vf", f"scale=160:-2,tile={n}x1:padding=3", "-an", str(sheet)])
        edges.append({"t": round(t, 3), "first_frame": first, "sheet": str(sheet)})
    return {"sweep": sweep, "edges": edges}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render")
    ap.add_argument("--ref-shots", nargs=2, type=float, metavar=("MIN", "MAX"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sheets", metavar="DIR", help="also write frame-by-frame contact sheets to DIR")
    ap.add_argument("--events", default="", help="comma-separated times (s) of title/graphic edges to sheet")
    ap.add_argument("--sweep-fps", type=float, default=3)
    a = ap.parse_args(argv)
    r = measure(Path(a.render), tuple(a.ref_shots) if a.ref_shots else None)
    if a.sheets:
        ev = [float(x) for x in a.events.split(",") if x.strip()]
        r["sheets"] = sheets(Path(a.render), Path(a.sheets), ev, a.sweep_fps)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {Path(a.render).name}  {r['duration']:.1f}s, {len(r['shots'])} shots, "
              f"median {r['median_shot']}s" + (f", {r['loudness_lufs']:.1f} LUFS, TP {r['true_peak_dbtp']:.1f}"
                                               if r["has_audio"] else ""))
        for line in r["problems"]:
            print(f"  - {line}")
        for line in r["notes"]:
            print(f"  ({line})")
        if "sheets" in r:
            sh = r["sheets"]
            print(f"  sheets: {len(sh['sweep'])} sweep + {len(sh['edges'])} edge in {a.sheets} (read every one)")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
