"""Kie.ai: one key for Kling (image to video), Seedream (stills) and Suno (instrumental music).

Paid per call on your own Kie credits. Adapted from nateherkai/herk-edit-kit,
.claude/skills/motion-showreel/scripts/kie.mjs (MIT, Copyright (c) Nate Herk).
Key: KIE_API_KEY in .env.local. Docs: https://docs.kie.ai/

  python tools/paid/kie.py credit                     (free: shows the balance)
  python tools/paid/kie.py music --style "punchy electronic, 128 bpm, riser into a big drop" --out music/ --go
  python tools/paid/kie.py image --prompt "studio shot of ..., plain black background" [--ref logo.png] [--aspect 9:16] --out still.png --go
  python tools/paid/kie.py video --image still.png --prompt "slow orbit, object stays rigid" [--duration 5] --out clip.mp4 --go

Nate's product-shot recipe: two stills (closed / open state) with `image`, then `video` from the first with a prompt
describing the change. Kling returns 24 fps: conform before editing,
  ffmpeg -i clip.mp4 -an -vf fps=30 -c:v libx264 -crf 16 -pix_fmt yuv420p clip30.mp4
Model ids drift; --model overrides the default for any command.
"""
import argparse
import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _paid import call, download, gate, key, poll  # noqa: E402

API = "https://api.kie.ai/api/v1"
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def headers():
    return {"Authorization": f"Bearer {key('KIE_API_KEY')}"}


def upload(path):
    """Host a local file on Kie's upload service and return its URL (also usable for higgsfield.py inputs)."""
    p = Path(path)
    b64 = base64.b64encode(p.read_bytes()).decode()
    r = call("https://kieai.redpandaai.co/api/file-base64-upload", {
        "base64Data": f"data:{MIME.get(p.suffix.lower(), 'application/octet-stream')};base64,{b64}",
        "uploadPath": "media-toolkit", "fileName": p.name}, headers())
    url = (r.get("data") or {}).get("downloadUrl")
    if not url:
        sys.exit("upload failed: " + json.dumps(r)[:300])
    return url


def run(model, inp, every):
    r = call(f"{API}/jobs/createTask", {"model": model, "input": inp}, headers())
    if r.get("code") != 200:
        sys.exit(f"create {model} failed: " + json.dumps(r)[:300])
    task = r["data"]["taskId"]
    print("task", task)

    def check():
        d = call(f"{API}/jobs/recordInfo?taskId={task}", headers=headers()).get("data") or {}
        if d.get("state") == "fail":
            sys.exit("task failed: " + json.dumps(d)[:300])
        return json.loads(d["resultJson"]) if d.get("state") == "success" else None
    return poll(check, every)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["credit", "music", "image", "video"])
    for f in ("prompt", "style", "title", "ref", "image", "out", "model"):
        ap.add_argument(f"--{f}")
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--duration", default="5")
    ap.add_argument("--negative", default="vocals, singing, lyrics, choir, lo-fi")
    ap.add_argument("--go", action="store_true", help="actually spend credits")
    a = ap.parse_args()

    if a.cmd == "credit":
        print(call(f"{API}/chat/credit", headers=headers()))
    elif a.cmd == "music":
        out = Path(a.out or ".")
        gate(a.go, f"Suno instrumental via Kie ({a.style!r}), 2 takes", out / "take-0.mp3")
        r = run(a.model or "ai-music-api/generate", {
            "custom_mode": True, "instrumental": True, "model": "V6", "title": a.title or "Bed", "prompt": "",
            "style": a.style or "modern electronic, instrumental, 120 bpm, riser into a drop, no vocals",
            "negative_tags": a.negative}, 10)
        urls = [u for u in dict.fromkeys(re.findall(r"https?:[^\"]+?\.(?:mp3|wav)", json.dumps(r))) if "/stream/" not in u]
        for i, u in enumerate(urls):
            download(u, out / f"take-{i}.mp3")
    elif a.cmd == "image":
        out = a.out or "still.png"
        gate(a.go, f"Seedream still {a.aspect}" + (f" from {a.ref}" if a.ref else ""), out)
        inp = {"prompt": a.prompt, "aspect_ratio": a.aspect, "quality": "high", "output_format": "png"}
        if a.ref:
            inp["image_urls"] = [upload(a.ref)]
        model = a.model or ("seedream/5-pro-image-to-image" if a.ref else "seedream/5-pro-text-to-image")
        download(run(model, inp, 6)["resultUrls"][0], out)
    elif a.cmd == "video":
        out = a.out or "clip.mp4"
        gate(a.go, f"Kling {a.duration}s 1080p from {a.image}", out)
        r = run(a.model or "kling/v3-turbo-image-to-video", {
            "prompt": a.prompt, "image_urls": [upload(a.image)], "duration": a.duration, "resolution": "1080p"}, 10)
        download(r["resultUrls"][0], out)


if __name__ == "__main__":
    main()
