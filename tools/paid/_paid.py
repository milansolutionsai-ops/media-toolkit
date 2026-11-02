"""Shared helpers for the paid routes: key loading, the --go spend gate, JSON over HTTP, polling, downloads.

Keys come from the environment, then from .env.local at the toolkit root (gitignored). Values are never printed.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = "milan-media-toolkit/1.0"


def key(name):
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit(f"{name} is not set. Add {name}=... to {env} (gitignored). See tools/paid/README.md.")


def gate(go, what, out=None):
    """Paid calls run only with --go, and never twice for a file that already exists."""
    if out and Path(out).exists():
        sys.exit(f"{out} already exists: not paying twice. Delete it to regenerate.")
    print(f"PAID: {what}")
    if not go:
        sys.exit("Dry run, nothing spent. Re-run with --go to spend.")


def call(url, body=None, headers=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": UA, **({"Content-Type": "application/json"} if data else {}), **(headers or {})}
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {url.split('?')[0]}: {e.read()[:400].decode(errors='replace')}")


def poll(check, every=8, max_s=1800):
    """Call check() until it returns something other than None."""
    t0 = time.time()
    while time.time() - t0 < max_s:
        r = check()
        if r is not None:
            return r
        time.sleep(every)
    sys.exit(f"Timed out after {max_s}s. The job may still finish on the provider's side: check its dashboard.")


def download(url, out, headers=None):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    out.write_bytes(urllib.request.urlopen(req, timeout=600).read())
    print("saved", out)
    return out
