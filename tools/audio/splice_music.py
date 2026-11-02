"""Rebuild a music track to an exact length from beat ranges, cuts landing on the beat.

  cd tools/editor && uv run python ../audio/beats.py track.mp3 > grid.json
  uv run python ../audio/splice_music.py track.mp3 grid.json --segments "8-32,140-156" --length 15 --gap 24 --out bed.wav

--segments  beat numbers (indexes into grid.json "beats", fractions allowed), played in order. Output t=0 is the
            first segment's start. Typical 15-30s ad bed: an intro bar or two, then a build that ENDS on the beat
            before a drop (grid.json "builds": end = the drop), then the drop for the payoff, or stop on the build
            to leave the CTA on the tension (docs/knowledge/ad-craft.md §3).
--gap N     duck the half beat before OUTPUT beat N to -16 dB (the breath before a drop)
--fade S    fade out the last S seconds (default 0.9; 0 = hard stop). Output is 1.5 dB down: hot sources clip.
Every cut lands 12 ms before its beat so the transient survives, joined by a 12 ms crossfade; each segment but
the last is lengthened by the crossfade so the beats stay on the grid. Check the result with beats.py: the
output's beats should sit on multiples of the period from 0.

Adapted from herk-edit-kit `motion-showreel/scripts/splice-music.mjs`:
Copyright (c) 2026 Nate Herk, MIT License (https://github.com/nateherkai/herk-edit-kit/blob/main/LICENSE).
"""
import argparse
import json
import subprocess

PRE = XF = 0.012


def build_filter(segs, period, phase, length, gap=None, fade=0.9):
    t = lambda beat: max(0.0, phase + beat * period - PRE)
    parts = [f"[0:a]asetpts=PTS-STARTPTS,atrim=start={t(a):.5f}:end={t(b) + (XF if i < len(segs) - 1 else 0):.5f},"
             f"asetpts=PTS-STARTPTS[s{i}]" for i, (a, b) in enumerate(segs)]
    chain = "[s0]"
    for i in range(1, len(segs)):
        parts.append(f"{chain}[s{i}]acrossfade=d={XF}:c1=qsin:c2=qsin[x{i}]")
        chain = f"[x{i}]"
    post = [f"apad=whole_dur={length}", f"atrim=0:{length}", "volume=-1.5dB"]  # club tracks clip at 0 dBFS
    if gap is not None:
        post.append(f"volume=0.158:enable='between(t,{(gap - 0.5) * period:.4f},{gap * period - 0.004:.4f})'")
    if fade > 0:
        post.append(f"afade=t=out:st={length - fade:.3f}:d={fade}")
    parts.append(f"{chain}{','.join(post)}[out]")
    return ";".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("track")
    ap.add_argument("grid", help="beats.py JSON")
    ap.add_argument("--segments", required=True)
    ap.add_argument("--length", type=float, required=True)
    ap.add_argument("--gap", type=float)
    ap.add_argument("--fade", type=float, default=0.9)
    ap.add_argument("--out", default="music-bed.wav")
    a = ap.parse_args()
    beats = json.load(open(a.grid, encoding="utf-8"))["beats"]
    period = (beats[-1] - beats[0]) / (len(beats) - 1)
    segs = [tuple(float(v) for v in s.split("-")) for s in a.segments.split(",")]
    fc = build_filter(segs, period, beats[0], a.length, a.gap, a.fade)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.track, "-filter_complex", fc, "-map", "[out]",
                    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", a.out], check=True)
    print(f"{a.out}: " + " + ".join(f"beats {x:g}-{y:g} ({beats[0] + x * period:.2f}-{beats[0] + y * period:.2f}s)"
                                    for x, y in segs) + f", {a.length}s")


if __name__ == "__main__":
    main()
