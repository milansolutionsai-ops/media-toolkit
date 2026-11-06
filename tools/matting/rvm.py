"""Temporal person matting: Robust Video Matting (Lin et al. 2021, GPL-3.0, github.com/PeterL1n/RobustVideoMatting).

  uv run --project tools/matting python tools/matting/rvm.py IN.mp4 OUT.webm [--ratio 0.25] [--model mobilenetv3]

Writes a VP9 webm with alpha (same frames as IN, alpha = the person), the format render.py's person mask reads.
Unlike per-frame models it carries memory between frames, so edges don't flicker. The model code and weights are
fetched by torch.hub on first run (cached in ~/.cache/torch/hub); nothing from the repo is vendored here.
"""
import argparse
import json
import subprocess

import numpy as np
import torch


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"], s["r_frame_rate"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--ratio", type=float, default=0.25, help="downsample ratio (0.25 for HD, 0.4 for closer shots)")
    ap.add_argument("--model", default="mobilenetv3", choices=["mobilenetv3", "resnet50"])
    a = ap.parse_args()

    w, h, rate = probe(a.src)   # expects an unrotated clip (render.py passes one cut from its base)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    model = torch.hub.load("PeterL1n/RobustVideoMatting", a.model, trust_repo=True).eval()
    torch.set_num_threads(max(1, torch.get_num_threads()))
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                            "-r", rate, "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
                            "-crf", "18", "-b:v", "0", "-deadline", "good", "-cpu-used", "4", a.out],
                           stdin=subprocess.PIPE)
    rec, n, buf = [None] * 4, 0, b""
    with torch.no_grad():
        while True:
            need = w * h * 3 - len(buf)
            if need > 0:
                buf += dec.stdout.read(need)
            if len(buf) < w * h * 3:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            buf = b""
            src = torch.from_numpy(frame.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255
            _fgr, pha, *rec = model(src, *rec, a.ratio)
            alpha = (pha[0, 0].clamp(0, 1) * 255).byte().numpy()
            enc.stdin.write(np.dstack([frame, alpha]).tobytes())
            n += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"matted {n} frames -> {a.out}")


if __name__ == "__main__":
    main()
