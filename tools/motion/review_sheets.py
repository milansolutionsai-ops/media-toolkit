"""Review sheets for a rendered video (or a reference video you want to learn from).

  python review_sheets.py <video> [--out DIR] [--strips 4.2,9.8] [--frames]

Writes into DIR (default: <video dir>/review/):
  contact.png   2 frames per second, 6 across          (pacing: a dead beat shows as two equal frames)
  phone.png     1 frame per second at 360px wide         (is the text readable on a phone?)
  strip-<t>.png 12 consecutive frames around each --strips time (glitches in fast moves, overlaps on swaps)
  frames/       with --frames: one PNG every 0.5s        (reference study: palette, type, shot lengths)
Needs only ffmpeg.
"""
import argparse, os, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("--out"); ap.add_argument("--strips", default="")
ap.add_argument("--frames", action="store_true")
a = ap.parse_args()
out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.video)), "review")
os.makedirs(out, exist_ok=True)

def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)

ff("-i", a.video, "-vf", "fps=2,scale=270:-1,tile=6x8", "-frames:v", "1", os.path.join(out, "contact.png"))
ff("-i", a.video, "-vf", "fps=1,scale=360:-1,tile=5x3", "-frames:v", "1", os.path.join(out, "phone.png"))
for t in filter(None, a.strips.split(",")):
    ff("-ss", str(max(0.0, float(t) - 0.2)), "-i", a.video, "-vf", "scale=320:-1,tile=12x1", "-frames:v", "1",
       os.path.join(out, f"strip-{float(t):g}s.png"))
if a.frames:
    os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    ff("-i", a.video, "-vf", "fps=2", os.path.join(out, "frames", "f%03d.png"))
print(out)
