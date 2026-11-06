"""Localhost server for the review app (127.0.0.1 only).

API responses never carry file names or paths: media goes out through opaque /media/<project>/<slug>/<asset>
URLs whose asset part is whitelisted. Everything is re-read from disk per request, so CLI changes show on refresh.
"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import media  # noqa: E402
import store  # noqa: E402
from review import open_notes, review_root  # noqa: E402

PORT = 47615
UI_DIR = HERE / "ui"
NAME = r"[A-Za-z0-9_.-]+"
ASSET_RE = re.compile(r"^(r\d+\.mp4|r\d+/(sprite\.jpg|sprite\.json|peaks\.json)|fixcheck-r\d+/[A-Za-z0-9_-]+(-\d+)?\.(jpg|mp4))$")
TYPES = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".json": "application/json", ".html": "text/html; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
CHUNK = 1 << 20


def _vdir(root: Path, project: str, slug: str) -> Path | None:
    if not (re.fullmatch(NAME, project) and re.fullmatch(NAME, slug)) or ".." in (project, slug):
        return None
    d = store.video_dir(root, project, slug)
    return d if (d / "video.json").exists() else None


def video_summary(vdir: Path, v: dict) -> dict:
    n = store.latest_round(v)
    notes = store.round_notes(vdir, n) if n else {"notes": []}
    claim = store.read_json(vdir / f"r{n}" / "claim.json") if n else None
    return {"id": v["id"], "title": v["title"], "project": v["project"], "status": v["status"],
            "status_label": store.STATUS_LABELS.get(v["status"], v["status"]),
            "round_label": store.round_label(n) if n else "", "notes_count": len(notes.get("notes", [])),
            "claimed_at": (claim or {}).get("at"), "updated": v.get("updated")}


def video_detail(vdir: Path, v: dict) -> dict:
    base = f"/media/{v['project']}/{v['slug']}"
    rounds = []
    for r in v["rounds"]:
        n = r["n"]
        notes = store.round_notes(vdir, n)
        fixes = store.read_json(vdir / f"fixes-r{n}.json", {}) or {}
        fc_index = store.read_json(vdir / f"fixcheck-r{n}" / "index.json", {}) or {}
        prev_open = open_notes(vdir, n - 1) if n > 1 else {}
        answers = []
        for a in fixes.get("answers", []):
            fc = fc_index.get(a["note_id"])
            answers.append({"note": prev_open.get(a["note_id"]), "note_id": a["note_id"],
                            "explanation": a.get("explanation", ""),
                            "fixcheck": {"kind": fc["kind"], "urls": [f"{base}/fixcheck-r{n}/{f}" for f in fc["files"]]}
                            if fc else None})
        rounds.append({"n": n, "label": store.round_label(n), "sent": bool(r.get("sent_at")),
                       "notes": notes.get("notes", []), "verdicts": notes.get("verdicts", {}), "answers": answers,
                       "video_url": f"{base}/r{n}.mp4", "peaks_url": f"{base}/r{n}/peaks.json",
                       "sprite": {"url": f"{base}/r{n}/sprite.jpg",
                                  "meta": store.read_json(vdir / f"r{n}" / "sprite.json", {})}})
    out = video_summary(vdir, v)
    out.update({k: v[k] for k in ("fps", "width", "height", "orientation", "windows")})
    out["rounds"] = rounds
    return out


def handle_send(root: Path, vdir: Path, body: dict) -> dict:
    v = store.load_video(vdir)
    n = int(body.get("round", 0))
    if n != store.latest_round(v) or v["status"] not in ("waiting", "fixes_ready"):
        raise ValueError("this round can't be sent")
    notes = body.get("notes") or []
    verdicts = {str(k): val for k, val in (body.get("verdicts") or {}).items() if val in ("fixed", "not-fixed")}
    for nt in notes:
        nt["round"], nt["author"] = n, "Milan"
        nt["start"], nt["end"] = int(nt["start"]), int(nt["end"])
        if nt.get("tag") not in ("picture", "sound", "cut"):
            raise ValueError("bad tag")
    status = store.apply_send(vdir, n, notes, verdicts)
    frames = sorted({f for nt in notes if nt["tag"] in ("picture", "cut")
                     for f in (nt["start"], (nt["start"] + nt["end"]) // 2, nt["end"])})
    if frames:
        media.extract_stills(vdir / f"r{n}.mp4", frames, vdir / f"r{n}" / "stills")
    store.rebuild_index(root)
    return {"status": status}


class Handler(BaseHTTPRequestHandler):
    root: Path = Path(".")

    def log_message(self, *args):  # silent: runs without a console
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _404(self):
        self._json({"error": "not found"}, 404)

    def _file(self, path: Path):
        size = path.stat().st_size
        ctype = TYPES.get(path.suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m or (m.group(1) == "" and m.group(2) == ""):
                start = size  # malformed: treat as unsatisfiable
            elif m.group(1) == "":
                start, end = max(0, size - int(m.group(2))), size - 1
            else:
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    buf = f.read(min(CHUNK, left))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    left -= len(buf)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass  # the player cancels range requests all the time

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            return self._json({"ok": True})
        if path == "/api/videos":
            return self._json([video_summary(d, v) for d, v in store.iter_videos(self.root)])
        m = re.fullmatch(rf"/api/videos/({NAME})/({NAME})", path)
        if m:
            vdir = _vdir(self.root, *m.groups())
            return self._json(video_detail(vdir, store.load_video(vdir))) if vdir else self._404()
        m = re.fullmatch(rf"/media/({NAME})/({NAME})/(.+)", path)
        if m:
            vdir = _vdir(self.root, m.group(1), m.group(2))
            asset = m.group(3)
            if not vdir or not ASSET_RE.fullmatch(asset) or ".." in asset:
                return self._404()
            f = vdir / asset
            return self._file(f) if f.is_file() else self._404()
        if path in ("/", "/index.html"):
            return self._file(UI_DIR / "index.html")
        m = re.fullmatch(r"/ui/([A-Za-z0-9_-]+\.(js|css|svg|html))", path)
        if m and (UI_DIR / m.group(1)).is_file():
            return self._file(UI_DIR / m.group(1))
        return self._404()

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        m = re.fullmatch(rf"/api/videos/({NAME})/({NAME})/send", path)
        vdir = _vdir(self.root, *m.groups()) if m else None
        if not vdir:
            return self._404()
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            return self._json(handle_send(self.root, vdir, body))
        except (ValueError, KeyError, TypeError) as e:
            return self._json({"error": str(e)}, 400)


def make_server(root: Path, port: int = PORT) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"root": Path(root)})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    return srv


if __name__ == "__main__":
    make_server(review_root()).serve_forever()
