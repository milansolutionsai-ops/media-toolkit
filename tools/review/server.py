"""Localhost server for the review app (127.0.0.1 only).

API responses never carry file names or paths: media goes out through opaque /media/<project>/<slug>/<asset>
URLs whose asset part is whitelisted. Everything is re-read from disk per request, so CLI changes show on refresh.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import media  # noqa: E402
import store  # noqa: E402
import style  # noqa: E402
from review import open_notes, review_root  # noqa: E402

PORT = 47615
AUTHOR = os.environ.get("REVIEW_AUTHOR", "reviewer")
UI_DIR = HERE / "ui"
NAME = r"[A-Za-z0-9_.-]+"
ASSET_RE = re.compile(r"^(r\d+\.mp4|r\d+/(sprite\.jpg|sprite\.json|peaks\.json)|fixcheck-r\d+/[A-Za-z0-9_-]+(-\d+)?\.(jpg|mp4)|plan/p\d+\.jpg)$")
TYPES = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".json": "application/json", ".html": "text/html; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".webmanifest": "application/manifest+json"}
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
    planning = v["status"].startswith("plan_")
    if planning:
        claim = store.read_json(vdir / "plan" / "claim.json")
    return {"id": v["id"], "title": v["title"], "project": v["project"], "status": v["status"],
            "status_label": store.STATUS_LABELS.get(v["status"], v["status"]),
            "round_label": store.PLAN_LABEL if planning else (store.round_label(n) if n else ""),
            "notes_count": store.plan_changes(store.read_json(vdir / "plan.json")) if planning
            else store.feedback_count(notes),
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
        sprite_meta = store.read_json(vdir / f"r{n}" / "sprite.json", {}) or {}
        rounds.append({"n": n, "label": store.round_label(n), "sent": bool(r.get("sent_at")),
                       "frames": sprite_meta.get("frames", 0),
                       "notes": notes.get("notes", []), "verdicts": notes.get("verdicts", {}), "answers": answers,
                       "video_url": f"{base}/r{n}.mp4", "peaks_url": f"{base}/r{n}/peaks.json",
                       "sprite": {"url": f"{base}/r{n}/sprite.jpg",
                                  "meta": sprite_meta}})
    out = video_summary(vdir, v)
    out.update({k: v[k] for k in ("fps", "width", "height", "orientation", "windows")})
    out["rounds"] = rounds
    plan = store.read_json(vdir / "plan.json")
    out["plan"] = None if not plan else {
        "version": plan["version"], "sent": bool(plan.get("sent_at")), "verdicts": plan.get("verdicts", {}),
        "notes": plan.get("notes", {}), "note": plan.get("note", ""),
        "rows": [{"id": r["id"], "start": r["start"], "end": r["end"], "text": r["text"],
                  "still_url": f"{base}/plan/{r['id']}.jpg" if r.get("still") else None} for r in plan["rows"]]}
    return out


def handle_plan_send(root: Path, vdir: Path, body: dict) -> dict:
    v = store.load_video(vdir)
    if v["status"] != "plan_waiting":
        raise ValueError("this plan can't be sent")
    plan = store.read_json(vdir / "plan.json")
    ids = [r["id"] for r in plan["rows"]]
    verdicts = {k: x for k, x in (body.get("verdicts") or {}).items() if k in ids and x in ("ok", "change")}
    if len(verdicts) != len(ids):
        raise ValueError("every line needs OK or Change")
    notes = {k: str(t).strip() for k, t in (body.get("notes") or {}).items() if k in ids and str(t).strip()}
    if any(x == "change" and k not in notes for k, x in verdicts.items()):
        raise ValueError("say what to change on every line marked Change")
    status = store.apply_plan_send(vdir, verdicts, notes, str(body.get("note") or "").strip())
    store.rebuild_index(root)
    return {"status": status}


def style_summary(r: dict) -> dict:
    return {"id": f"{r['project']}/style-{r['n']}", "kind": "style", "title": r["title"], "project": r["project"],
            "status": r["status"], "status_label": {"waiting": "Waiting for you", "sent": "Reactions sent", "done": "Reactions sent"}.get(r["status"], "Cancelled"),
            "round_label": f"Style round {r['n']}", "notes_count": len(r["candidates"]), "claimed_at": None,
            "updated": r.get("sent_at") or r.get("created")}


def style_detail(root: Path, project: str, n: int) -> dict | None:
    if not re.fullmatch(NAME, project) or ".." in project:
        return None
    d = style.style_dir(root, project, n)
    r = store.read_json(d / "round.json")
    if not r:
        return None
    rx = store.read_json(d / "reactions.json", {}) or {}
    cands = [{"id": c["id"], "label": c["label"], "dimension": c["dimension"], "origin": c["origin"],
              "explain": c.get("explain", ""), "width": c["width"], "height": c["height"],
              "video_url": f"/media/{project}/style-{n}/{c['id']}.mp4"} for c in r["candidates"]]
    return {"project": project, "n": n, "title": r["title"], "status": r["status"], "candidates": cands,
            "reactions": rx.get("reactions", {}), "note": rx.get("note", "")}


def handle_send(root: Path, vdir: Path, body: dict) -> dict:
    v = store.load_video(vdir)
    n = int(body.get("round", 0))
    if n != store.latest_round(v) or v["status"] not in ("waiting", "fixes_ready"):
        raise ValueError("this round can't be sent")
    total = (store.read_json(vdir / f"r{n}" / "sprite.json", {}) or {}).get("frames") or 10**9
    verdicts = {str(k): val for k, val in (body.get("verdicts") or {}).items() if val in ("fixed", "not-fixed")}
    notes = []
    for raw in body.get("notes") or []:
        nid = raw.get("id") or secrets.token_hex(3)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(nid)):
            raise ValueError("bad note id")
        if raw.get("tag") not in ("picture", "sound", "cut") or not str(raw.get("text", "")).strip():
            raise ValueError("a note needs a tag and text")
        a, b = sorted((int(raw["start"]), int(raw["end"])))
        a, b = max(0, min(a, total - 1)), max(0, min(b, total - 1))
        notes.append({"id": str(nid), "round": n, "start": a, "end": b, "tag": raw["tag"],
                      "text": str(raw["text"]).strip(), "author": AUTHOR})
    fixes = store.read_json(vdir / f"fixes-r{n}.json", {}) or {}
    unanswered = [a["note_id"] for a in fixes.get("answers", []) if a["note_id"] not in verdicts]
    if unanswered:
        raise ValueError("every fix needs Fixed or Not fixed before sending")
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

    def _trusted(self) -> bool:
        """Only this machine's own pages: blocks other sites and DNS rebinding from reading or sending."""
        port = self.server.server_address[1]
        ok = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in ok:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in ok}

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
        if rng and "," not in rng:  # multi-range isn't supported: send the whole file
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
        if not self._trusted():
            return self._json({"error": "forbidden"}, 403)
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            return self._json({"ok": True})
        if path == "/api/videos":
            vids = [dict(video_summary(d, v), kind="video") for d, v in store.iter_videos(self.root)]
            claims = {e["id"]: e.get("claimed_at") for e in
                      (store.read_json(self.root / store.INDEX_NAME, {}) or {}).get("videos", [])}
            styles = [dict(style_summary(r), claimed_at=claims.get(f"{r['project']}/style-{r['n']}"))
                      for _, r in style.iter_rounds(self.root) if r["status"] != "cancelled"]
            return self._json(vids + styles)
        m = re.fullmatch(rf"/api/style/({NAME})/(\d+)", path)
        if m:
            d = style_detail(self.root, m.group(1), int(m.group(2)))
            return self._json(d) if d else self._404()
        m = re.fullmatch(rf"/media/({NAME})/style-(\d+)/(c\d+\.mp4)", path)
        if m:
            if ".." in m.group(1):
                return self._404()
            f = style.style_dir(self.root, m.group(1), int(m.group(2))) / m.group(3)
            return self._file(f) if f.is_file() else self._404()
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
        if path == "/sw.js":  # service worker at root scope, so the app is installable
            return self._file(UI_DIR / "sw.js")
        m = re.fullmatch(r"/ui/([A-Za-z0-9_-]+\.(js|css|svg|html|png|webmanifest))", path)
        if m and (UI_DIR / m.group(1)).is_file():
            return self._file(UI_DIR / m.group(1))
        return self._404()

    def do_POST(self):
        if not self._trusted():
            return self._json({"error": "forbidden"}, 403)
        path = unquote(urlparse(self.path).path)
        m = re.fullmatch(rf"/api/style/({NAME})/(\d+)/send", path)
        if m:
            if not style_detail(self.root, m.group(1), int(m.group(2))):
                return self._404()
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                style.apply_reactions(self.root, m.group(1), int(m.group(2)), body.get("reactions") or {},
                                      str(body.get("note") or ""))
                return self._json({"status": "sent"})
            except (ValueError, KeyError, TypeError) as e:
                return self._json({"error": str(e)}, 400)
        m = re.fullmatch(rf"/api/videos/({NAME})/({NAME})/(plan/)?send", path)
        vdir = _vdir(self.root, m.group(1), m.group(2)) if m else None
        if not vdir:
            return self._404()
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            fn = handle_plan_send if m.group(3) else handle_send
            return self._json(fn(self.root, vdir, body))
        except (ValueError, KeyError, TypeError) as e:
            return self._json({"error": str(e)}, 400)


def make_server(root: Path, port: int = PORT) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"root": Path(root)})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    return srv


if __name__ == "__main__":
    make_server(review_root()).serve_forever()
