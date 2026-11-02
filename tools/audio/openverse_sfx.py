"""Find and download real (recorded) sound effects from Openverse. No key. CC0 by default: free for any use,
no credit needed.

  python tools/audio/openverse_sfx.py search "whoosh" [--max-sec 3] [--n 15] [--license cc0]
  python tools/audio/openverse_sfx.py get "whoosh" [--max-sec 3] [--n 5]
      → tools/audio/sfx/openverse/<query>/NN-<title>.<ext> + credits.json (title, creator, licence, source page)

Then pick by ear-proxy: `earshot rank "a short airy whoosh" tools/audio/sfx/openverse/whoosh/*` (tools/audio/README.md).
Most results come from Freesound. The API is slow and often answers 504 on a cold query: the script retries.
--license accepts Openverse codes (cc0, by, by-sa, pdm...); anything but cc0/pdm needs the credit in credits.json.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.openverse.org/v1/audio/"
UA = {"User-Agent": "milan-media-toolkit/1.0"}
OUT = Path(__file__).parent / "sfx" / "openverse"


def fetch(url, timeout=60):
    for wait in (5, 15, 30, 0):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            if (code is not None and code < 500 and code != 429) or not wait:
                raise
            print(f"  openverse: {code or type(e).__name__}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)


def search(q, license="cc0", max_sec=None, n=15):
    params = urllib.parse.urlencode({"q": q, "license": license, "page_size": 20})
    res = json.loads(fetch(f"{API}?{params}"))["results"]
    if max_sec:
        res = [r for r in res if r.get("duration") and r["duration"] <= max_sec * 1000]
    return res[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["search", "get"])
    ap.add_argument("query")
    ap.add_argument("--license", default="cc0")
    ap.add_argument("--max-sec", type=float)
    ap.add_argument("--n", type=int)
    a = ap.parse_args()
    res = search(a.query, a.license, a.max_sec, a.n or (15 if a.cmd == "search" else 5))
    if a.cmd == "search":
        for i, r in enumerate(res, 1):
            print(f"{i:2d}. {r['title'][:50]:50s} {(r.get('duration') or 0) / 1000:5.1f}s  {r['license']:6s} "
                  f"{(r.get('creator') or '?')[:20]:20s} {r['foreign_landing_url']}")
        return
    folder = OUT / re.sub(r"[^a-z0-9]+", "-", a.query.lower()).strip("-")
    folder.mkdir(parents=True, exist_ok=True)
    credits = []
    for i, r in enumerate(res, 1):
        ext = r.get("filetype") or Path(urllib.parse.urlparse(r["url"]).path).suffix.lstrip(".") or "mp3"
        name = f"{i:02d}-{re.sub(r'[^a-z0-9]+', '-', r['title'].lower()).strip('-')[:40]}.{ext}"
        (folder / name).write_bytes(fetch(r["url"]))
        credits.append({"file": name, "title": r["title"], "creator": r.get("creator"), "license": r["license"],
                        "license_url": r.get("license_url"), "source": r["foreign_landing_url"],
                        "seconds": (r.get("duration") or 0) / 1000})
        print(f"  {name}  {credits[-1]['seconds']:.1f}s  {r['license']}")
    (folder / "credits.json").write_text(json.dumps(credits, indent=1), encoding="utf-8")
    print(folder)


if __name__ == "__main__":
    main()
