"""Gemini Omni Flash video (gemini-omni-1.1-flash): text or image(s) to video with sound.

Same Interactions API as tools/voice/gemini_vo.py. Replaces Veo, which the Gemini API shut down on 2026-10-22.
Needs a key from an AI Studio project WITH billing: GEMINI_VIDEO_API_KEY in .env.local. A separate name on purpose,
so a free TTS key or a stray GEMINI_API_KEY in the environment is never billed by accident.
Docs and prompt guide: https://ai.google.dev/gemini-api/docs/video

  python tools/paid/omni_video.py "Single continuous shot of ... No scene cuts. Sound: ..." --out clip.mp4 --go
      [--aspect 9:16|16:9] [--res 360p|720p|1080p|4k] [--image first.png [--image last.png]]

Prompt rules from the docs: it cuts between shots unless told "single continuous shot, no scene cuts"; describe the
audio or it invents some; timecodes like [0-3s] ... [3-6s] work; with images, start the prompt with <FIRST_FRAME>
(and <LAST_FRAME>) or <IMAGE_REF_0> to bind each one. Output carries an invisible SynthID watermark.
"""
import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _paid import call, download, gate, key  # noqa: E402

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--image", action="append", default=[])
    ap.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    ap.add_argument("--res", default="720p", choices=["360p", "720p", "1080p", "4k"])
    ap.add_argument("--model", default="gemini-omni-1.1-flash")
    ap.add_argument("--go", action="store_true", help="actually spend")
    a = ap.parse_args()

    gate(a.go, f"{a.model} {a.aspect} {a.res}" + (f" from {len(a.image)} image(s)" if a.image else ""), a.out)
    k = key("GEMINI_VIDEO_API_KEY")
    images = [{"type": "image", "mime_type": MIME[Path(p).suffix.lower()],
               "data": base64.b64encode(Path(p).read_bytes()).decode()} for p in a.image]
    body = {"model": a.model, "input": images + [{"type": "text", "text": a.prompt}] if images else a.prompt,
            "response_format": {"type": "video", "aspect_ratio": a.aspect, "resolution": a.res, "delivery": "uri"}}
    r = call("https://generativelanguage.googleapis.com/v1beta/interactions", body, {"x-goog-api-key": k}, timeout=1200)
    video = [c for s in r.get("steps", []) for c in s.get("content", []) if c.get("type") == "video"]
    if not video:
        sys.exit(f"no video in the response (status {r.get('status')}). Blocked prompts come back empty.")
    if video[0].get("uri"):
        download(video[0]["uri"], a.out, {"x-goog-api-key": k})
    else:
        Path(a.out).write_bytes(base64.b64decode(video[0]["data"]))
        print("saved", a.out)


if __name__ == "__main__":
    main()
