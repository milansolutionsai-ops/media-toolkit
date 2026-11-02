"""Measure a music track: tempo, beat grid, downbeats and hits (strong onsets) → JSON.

  cd tools/editor && uv run python ../audio/beats.py <track.mp3|wav> > beats.json

Output: {"bpm", "beats": [s...], "downbeats": [s...], "hits": [s...], "builds": [{start,end,rise_db,...}], "duration"}
Use it to land scene changes on beats, big moments on downbeats, SFX on hits, a build under the CTA.
numpy + ffmpeg only (no librosa). Tempo search 70-180 BPM; check halving/doubling by ear.
Downbeats assume 4/4 and pick the beat phase with the most low-end energy.
"""
import json, subprocess, sys
import numpy as np

SR, HOP, WIN = 22050, 512, 2048
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[1], "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True, check=True).stdout
x = np.frombuffer(raw, dtype=np.float32)
fps = SR / HOP
frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (0, WIN)), WIN)[::HOP] * np.hanning(WIN)
S = np.abs(np.fft.rfft(frames, axis=1))
flux = np.r_[0, np.maximum(np.diff(np.log1p(S), axis=0), 0).sum(1)]
low = S[:, 1:12].sum(1)  # under ~250 Hz: kick / bass

o = flux - flux.mean()
ac = np.correlate(o, o, "full")[len(o) - 1:]
cands = np.arange(70, 180.01, 0.1)
score = [np.interp([60 / b * fps * m for m in (1, 2, 4)], np.arange(len(ac)), ac).sum() for b in cands]
bpm = float(cands[int(np.argmax(score))])
period = 60 / bpm
dur = len(x) / SR

# Phase from the KICK band with short windows (idea from herk-edit-kit music-grid.mjs, MIT, (c) 2026 Nate Herk):
# long windows register an attack when it enters the window, so the grid ran ~0.14 s early; hats can pull the
# full band half a beat off. A 12 ms window, shifted by its own length, lands on the transient.
kick = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[1], "-ac", "1", "-ar", str(SR),
                                     "-af", "lowpass=f=120,lowpass=f=120", "-f", "f32le", "-"],
                                    capture_output=True, check=True).stdout, dtype=np.float32)
SH, SW = 64, 256
ke = (np.lib.stride_tricks.sliding_window_view(np.pad(kick, (0, SW)), SW)[::SH] ** 2).mean(1)
ko = np.r_[0, np.maximum(np.diff(np.log(ke + 1e-10)), 0)]
phases = np.arange(0, period, 0.002)
ph = phases[int(np.argmax([np.interp((np.arange(p, dur, period) - SW / SR) * SR / SH, np.arange(len(ko)), ko).sum()
                           for p in phases]))]
beats = np.arange(ph, dur, period)
lowv = np.interp(beats * fps, np.arange(len(low)), low)
off = int(np.argmax([lowv[i::4].mean() for i in range(4)]))

thr = flux.mean() + 3 * flux.std()
peaks = [i for i in range(1, len(flux) - 1) if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
hits, last = [], -1.0
for i in peaks:
    t = i / fps
    if t - last >= 0.25:
        hits.append(round(t, 3)); last = t

# Build-ups: stretches where loudness climbs steadily (often with brightness rising: risers, snare rolls) into a peak.
# Use one under a CTA instead of a track's ending (docs/knowledge/ad-craft.md §3). Start snaps to a downbeat, end
# (the peak or the drop) to a beat. kind "ramp" = loudness climbs; "pre-drop" = level loudness, brightening, then a drop.
# Cut a CTA bed to end just BEFORE a pre-drop's end to leave the viewer on the tension.
def find_builds(rms_db, bright, fps, downbeats, beats, min_len=4.0, max_len=16.0, min_rise=4.0):
    step = max(1, int(fps / 4))                                  # analyse at 4 Hz
    k = int(fps)                                                 # 1 s smoothing
    sm = lambda v: (np.convolve(v, np.ones(k), "same") / np.convolve(np.ones_like(v), np.ones(k), "same"))[::step]
    e, c, hz = sm(rms_db), sm(bright), fps / step
    cands = []
    for L in range(int(min_len * hz), int(max_len * hz) + 1, int(hz)):
        for a0 in range(0, len(e) - L, int(hz / 2)):
            w = e[a0:a0 + L]
            top = int(np.argmax(w >= w.max() - 1.0)) + 1         # ends where it first reaches its peak (±1 dB)
            lo = int(np.nonzero(w[:top] <= w[:top].min() + 1.0)[0][-1])  # starts where it leaves the floor
            a, L2 = a0 + lo, top - lo
            if L2 < min_len * hz:
                continue
            seg, t = e[a:a + L2], np.arange(L2)
            slope, icpt = np.polyfit(t, seg, 1)
            rise = slope * L2
            jump = (seg[int(hz):] - seg[:-int(hz)]).max() if L2 > hz else rise
            if rise < min_rise or jump > 0.5 * rise:              # a step (the drop itself) is not a build
                continue
            r2 = 1 - ((seg - (slope * t + icpt)) ** 2).sum() / (((seg - seg.mean()) ** 2).sum() + 1e-9)
            cands.append((rise * r2 * r2, a / hz, (a + L2) / hz, rise, float(c[a + L2 - 1] - c[a])))
    # Club/EDM style: loudness holds level while the sound gets brighter, then steps up into a drop.
    H = int(hz)
    d = np.r_[e[H:] - e[:-H], np.zeros(H)]                       # loudness gained over the next second
    for j in range(1, len(e) - 3 * H):
        if d[j] < 3.0 or d[j] < d[max(0, j - 2 * H):j + 2 * H].max():
            continue                                             # strongest step within ±2 s
        if e[j + H:j + 3 * H].mean() - e[j] < 3.0:
            continue                                             # and it holds: a drop, not a hit
        i = j + H // 2                                           # drop lands mid-step
        back = c[max(0, i - int(max_len * hz)):i]
        lo = int(np.argmin(back)); s = i - len(back) + lo
        if (i - s) < min_len * hz or c[i - 1] - back[lo] < 0.3:   # brightness must climb (≥0.3 octave)
            continue
        cands.append((100 + float(c[i - 1] - back[lo]), s / hz, i / hz, float(e[i - 1] - e[s]), 1.0))
    out = []
    for score, s, t_end, rise, cr in sorted(cands, reverse=True):
        if any(s < o["end"] and t_end > o["start"] for o in out):
            continue
        snap = lambda v, g: float(g[np.argmin(np.abs(g - v))]) if len(g) else v
        out.append({"start": round(snap(s, downbeats), 3), "end": round(snap(t_end, beats), 3), "rise_db": round(rise, 1),
                    "kind": "pre-drop" if score >= 100 else "ramp", "brightening": cr > 0})
        if len(out) == 5:
            break
    return sorted(out, key=lambda b: b["start"])

rms_db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-6)
centroid = (S * np.arange(S.shape[1])).sum(1) / (S.sum(1) + 1e-9) * SR / WIN
downs = beats[off::4]
builds = find_builds(rms_db, np.log2(centroid + 1), fps, downs, beats)
drops = [b["end"] for b in builds if b["kind"] == "pre-drop"]
if drops:  # a drop lands on bar 1: let it set the downbeat phase (every beat has a kick in club music)
    off = int(np.argmin(np.abs(beats - drops[0]))) % 4
    downs = beats[off::4]
    builds = find_builds(rms_db, np.log2(centroid + 1), fps, downs, beats)

json.dump({"bpm": round(bpm, 2), "duration": round(dur, 3), "beats": [round(b, 3) for b in beats],
           "downbeats": [round(b, 3) for b in downs], "hits": hits, "builds": builds}, sys.stdout, indent=1)
