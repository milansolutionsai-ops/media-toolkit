"""Higgsfield API: one key for 50+ image and video models (Kling, Seedance, Wan, MiniMax, Soul...).

Paid per generation from a prepaid balance. This is the API, not Katana (the claude.ai connector, used by hand).
Key: HF_KEY=<key id>:<key secret> in .env.local. Model list and each model's fields: https://docs.higgsfield.ai/

  python tools/paid/higgsfield.py <model-path> --set prompt="..." [--set image_url=...] --out clip.mp4 --go
  python tools/paid/higgsfield.py kling-video/v2.6/pro/image-to-video --set prompt="slow push-in" --set image_url=still.png --out clip.mp4 --go
  python tools/paid/higgsfield.py higgsfield-ai/soul/v2/standard --set prompt="editorial portrait, soft daylight" --out portrait.png --go

Any --set value that is a local file path is uploaded first (through Kie's file host, so KIE_API_KEY is needed for
that; otherwise pass a public URL). Values that parse as JSON (numbers, true/false, lists) are sent as JSON.
"""
import argparse
import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _paid import call, download, gate, key, poll  # noqa: E402

API = "https://api.higgsfield.ai"
FAILED = {"failed", "nsfw", "canceled", "cancelled", "error"}


def value(v):
    if Path(v).is_file():
        from kie import upload
        return upload(v)
    try:
        return json.loads(v)
    except ValueError:
        return v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", help="model path from the docs, e.g. kling-video/v2.6/pro/image-to-video")
    ap.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    ap.add_argument("--out", required=True)
    ap.add_argument("--go", action="store_true", help="actually spend credits")
    a = ap.parse_args()

    fields = dict(s.split("=", 1) for s in a.set)
    gate(a.go, f"Higgsfield {a.model} with {sorted(fields)}", a.out)
    h = {"Authorization": f"Key {key('HF_KEY')}", "Idempotency-Key": str(uuid.uuid4())}
    r = call(f"{API}/{a.model}", {k: value(v) for k, v in fields.items()}, h)
    print("request", r.get("request_id"))

    def check():
        s = call(r["status_url"], headers=h)
        if s.get("status") in FAILED:
            sys.exit("generation failed: " + json.dumps(s)[:300])
        return s if s.get("status") == "completed" else None
    done = poll(check, 8)
    urls = [u for u in re.findall(r"https?://[^\"]+", json.dumps(done)) if "api.higgsfield.ai" not in u]
    if not urls:
        sys.exit("completed, but no media URL in: " + json.dumps(done)[:300])
    download(urls[0], a.out)


if __name__ == "__main__":
    main()
