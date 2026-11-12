"""Auphonic: one-pass "studio voice" processing through its API (leveler, noise and hum reduction, loudness).

  auphonic.py IN [-o OUT] [--loudness -14] [--denoise 12] [--method dynamic] [--deverb 0] [--leveler 80]
              [--preset NAME] [--fetch UUID]

Uploads IN (audio or video), runs a production, waits, downloads the processed audio to OUT
(default: IN's name + .auphonic.wav next to IN). Needs env AUPHONIC_API_KEY (Account > API key on
auphonic.com); the key is read by name and never printed. Free plan: 2 hours of audio a month, and it
appends a jingle, so the output is trimmed back to IN's length.
Defaults are the chain Milan picked blind (round 9): dynamic denoise at 12 dB (soft pauses, no hard
cut-offs), full reverb removal, leveler 80%. Speech isolation (--method speech_isolation --denoise 18
--deverb 6) is cleaner on a noisy room but sounds more processed.
Docs: https://auphonic.com/help/api/simple_api.html, https://auphonic.com/help/api/query.html
"""
from __future__ import annotations

import argparse
import subprocess
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

API = "https://auphonic.com/api"


def _key() -> str:
    k = os.environ.get("AUPHONIC_API_KEY")
    if not k:
        sys.exit("AUPHONIC_API_KEY is not set (create one under Account > API key on auphonic.com)")
    return k


def _req(url: str, data: bytes | None = None, headers: dict | None = None) -> dict:
    r = urllib.request.Request(url, data=data, headers={"Authorization": f"bearer {_key()}", **(headers or {})})
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:   # Auphonic explains a 400 in the body
        sys.exit(f"auphonic HTTP {e.code}: {e.read().decode(errors='replace')[:800]}")


def multipart(fields: dict[str, str], file_field: str, path: Path) -> tuple[bytes, str]:
    """multipart/form-data body (stdlib only)."""
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    return b"".join(parts) + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def fields(title: str, loudness: float = -14, denoise: int = 12, method: str | None = "dynamic",
           deverb: int | None = 0, leveler: int | None = 80) -> dict[str, str]:
    """Production fields. denoise/deverb are dB of reduction (0 = full, -1 = off); a gentler denoise
    (e.g. 12) avoids the hard cut-offs at pauses. deverb needs method static/dynamic/speech_isolation."""
    f = {"title": title, "action": "start", "loudnesstarget": str(loudness),
         "denoise": "true", "denoiseamount": str(denoise), "output_files": json.dumps([{"format": "wav"}])}
    if method:
        f["denoisemethod"] = method
    if deverb is not None:
        f["deverbamount"] = str(deverb)
    if leveler is not None:
        f["levelerstrength"] = str(leveler)
    return f


def process(src: Path, out: Path, loudness: float = -14, denoise: int = 12, preset: str | None = None,
            method: str | None = "dynamic", deverb: int | None = 0, leveler: int | None = 80) -> Path:
    fields_ = fields(src.stem, loudness, denoise, method, deverb, leveler)
    if preset:
        fields_["preset"] = preset
    body, ctype = multipart(fields_, "input_file", src)
    prod = _req(f"{API}/simple/productions.json", body, {"Content-Type": ctype})["data"]
    pid = prod["uuid"]
    print(f"auphonic production {pid} started", flush=True)
    while True:
        st = _req(f"{API}/production/{pid}/status.json")["data"]
        if st.get("status_string") == "Done":
            break
        if "error" in str(st.get("status_string", "")).lower():
            sys.exit(f"auphonic error: {st}")
        time.sleep(5)
    return trim_to(src, download(pid, out))


def _dur(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout)


def trim_to(src: Path, out: Path) -> Path:
    """Cut the free plan's jingle: trim OUT to SRC's length when it runs longer."""
    keep = _dur(src)
    if _dur(out) > keep + 0.05:
        tmp = out.with_name(out.stem + ".trim" + out.suffix)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-t", f"{keep:.3f}", str(tmp)], check=True)
        tmp.replace(out)
    return out


def download(pid: str, out: Path) -> Path:
    """Fetch a finished production's first output file. With an API key the token goes in the URL
    (bearer_token=...); the Authorization header is refused (HTTP 400) on download links."""
    url = _req(f"{API}/production/{pid}.json")["data"]["output_files"][0]["download_url"]
    url += ("&" if "?" in url else "?") + "bearer_token=" + _key()
    with urllib.request.urlopen(url, timeout=300) as resp:
        out.write_bytes(resp.read())
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--loudness", type=float, default=-14)
    ap.add_argument("--denoise", type=int, default=12, help="dB of noise reduction (0 = full)")
    ap.add_argument("--method", default="dynamic", choices=["classic", "static", "dynamic", "speech_isolation"])
    ap.add_argument("--deverb", type=int, default=0, help="reverb reduction in dB (0 full, -1 off)")
    ap.add_argument("--leveler", type=int, default=80, help="leveler strength %%")
    ap.add_argument("--preset")
    ap.add_argument("--fetch", metavar="UUID", help="only download an already finished production")
    a = ap.parse_args(argv)
    out = a.output or a.input.with_suffix(".auphonic.wav")
    print("done:", trim_to(a.input, download(a.fetch, out)) if a.fetch else process(a.input, out, a.loudness, a.denoise, a.preset,
                                                                         a.method, a.deverb, a.leveler))


if __name__ == "__main__":
    main()
