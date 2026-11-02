"""Render a Blender scene headless on whatever GPU the machine has.

Picks NVIDIA (OptiX, then CUDA), AMD (HIP), Apple (Metal) or Intel (oneAPI), else CPU. Blender is free; the cost is
the GPU: your own RTX card, or a rented one (RunPod, Vast...) where you install Blender, copy this file and the .blend,
and run the same command. Blender: https://www.blender.org/download/ (or set BLENDER=<path to blender.exe>).

  python tools/paid/blender_render.py --probe                       (which devices Blender sees, renders nothing)
  python tools/paid/blender_render.py scene.blend --out renders/frame_#### [--start 1 --end 120]
      [--device AUTO|OPTIX|CUDA|HIP|METAL|ONEAPI|CPU] [--samples 128] [--engine CYCLES|BLENDER_EEVEE_NEXT] [--format PNG]
  then: ffmpeg -framerate 30 -i renders/frame_%04d.png -c:v libx264 -crf 16 -pix_fmt yuv420p shot.mp4

Without --start/--end the scene's own frame range renders. Engine, samples and format default to the scene's.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

SETUP = r'''
import bpy, sys
want, samples = sys.argv[sys.argv.index("--") + 1:][:2]
prefs = bpy.context.preferences.addons["cycles"].preferences
used = "CPU"
for dev in (["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"] if want == "AUTO" else [want]):
    if dev == "CPU":
        break
    try:
        prefs.compute_device_type = dev
    except TypeError:
        continue
    prefs.get_devices()
    if any(d.type == dev for d in prefs.devices):
        for d in prefs.devices:
            d.use = d.type == dev
            print(f"[blender_render]   {d.type:7} {d.name} {'ON' if d.use else 'off'}")
        used = dev
        break
scene = bpy.context.scene
if scene.render.engine == "CYCLES":
    scene.cycles.device = "CPU" if used == "CPU" else "GPU"
    if int(samples):
        scene.cycles.samples = int(samples)
print(f"[blender_render] device={used} engine={scene.render.engine} frames={scene.frame_start}-{scene.frame_end}")
'''


def find_blender():
    found = os.environ.get("BLENDER") or shutil.which("blender")
    if not found:
        hits = sorted(glob.glob("C:/Program Files/Blender Foundation/Blender */blender.exe"))
        found = hits[-1] if hits else None
    if not found:
        sys.exit("Blender not found. Install it from https://www.blender.org/download/ or set BLENDER=<path>.")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blend", nargs="?")
    ap.add_argument("--out", default="renders/frame_####")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--device", default="AUTO", choices=["AUTO", "OPTIX", "CUDA", "HIP", "METAL", "ONEAPI", "CPU"])
    ap.add_argument("--samples", type=int, default=0)
    ap.add_argument("--engine")
    ap.add_argument("--format")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    if not a.probe and not a.blend:
        ap.error("give a .blend file, or --probe")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(SETUP)
    cmd = [find_blender(), "-b"]
    if a.probe:
        cmd += ["--python", f.name]
    else:
        cmd += [a.blend] + (["-E", a.engine] if a.engine else []) + ["--python", f.name]
        cmd += ["-o", os.path.abspath(a.out)] + (["-F", a.format] if a.format else [])
        cmd += (["-s", str(a.start)] if a.start else []) + (["-e", str(a.end)] if a.end else []) + ["-a"]
    cmd += ["--", a.device, str(a.samples)]
    try:
        sys.exit(subprocess.call(cmd))
    finally:
        os.unlink(f.name)


if __name__ == "__main__":
    main()
