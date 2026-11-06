"""Localhost server: API, range serving, send."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import server  # noqa: E402
from _fx import make_clip  # noqa: E402

VID = "my-project/03-x"


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "my-project").mkdir()
        clip = make_clip(self.root / "c.mp4")
        env = dict(os.environ, REVIEW_ROOT=str(self.root))
        subprocess.run([sys.executable, str(HERE.parent / "review.py"), "register", "--project", "my-project",
                        "--title", "03 X", "--render", str(clip)], env=env, check=True, capture_output=True)
        self.srv = server.make_server(self.root, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def test_health(self):
        s, _, b = self.get("/api/health")
        self.assertEqual((s, json.loads(b)), (200, {"ok": True}))

    def test_list_and_detail_have_no_paths(self):
        s, _, b = self.get("/api/videos")
        lst = json.loads(b)
        self.assertEqual(lst[0]["id"], VID)
        self.assertEqual(lst[0]["status_label"], "Waiting for you")
        s, _, b = self.get(f"/api/videos/{VID}")
        self.assertEqual(s, 200)
        text = b.decode()
        for bad in [":\\\\", str(self.root).replace("\\", "\\\\"), "video.json", "notes-r", "_review"]:
            self.assertNotIn(bad, text)
        d = json.loads(b)
        self.assertEqual(d["rounds"][0]["label"], "First cut")
        self.assertTrue(d["rounds"][0]["video_url"].startswith("/media/"))
        self.assertEqual(d["rounds"][0]["frames"], 60)

    def test_range_206(self):
        s, h, b = self.get(f"/media/{VID}/r1.mp4", {"Range": "bytes=0-99"})
        size = (self.root / "my-project/_review/03-x/r1.mp4").stat().st_size
        self.assertEqual(s, 206)
        self.assertEqual(len(b), 100)
        self.assertEqual(h["Content-Range"], f"bytes 0-99/{size}")
        self.assertEqual(h["Accept-Ranges"], "bytes")
        self.assertEqual(h["Content-Type"], "video/mp4")

    def test_range_open_ended(self):
        size = (self.root / "my-project/_review/03-x/r1.mp4").stat().st_size
        s, h, b = self.get(f"/media/{VID}/r1.mp4", {"Range": "bytes=100-"})
        self.assertEqual((s, len(b)), (206, size - 100))
        s, h, b = self.get(f"/media/{VID}/r1.mp4", {"Range": "bytes=-50"})
        self.assertEqual((s, len(b)), (206, 50))

    def test_range_past_end_416(self):
        size = (self.root / "my-project/_review/03-x/r1.mp4").stat().st_size
        s, h, _ = self.get(f"/media/{VID}/r1.mp4", {"Range": f"bytes={size + 10}-"})
        self.assertEqual(s, 416)
        self.assertEqual(h["Content-Range"], f"bytes */{size}")

    def test_media_traversal_404(self):
        for p in [f"/media/{VID}/../../video.json", f"/media/{VID}/video.json", "/media/x/y/r1.mp4",
                  f"/media/{VID}/r1/../video.json"]:
            self.assertEqual(self.get(p)[0], 404, p)

    def test_send_sets_status_and_writes_stills(self):
        note = {"id": "a", "round": 1, "start": 10, "end": 20, "tag": "picture", "text": "flash"}
        s, b = self.post(f"/api/videos/{VID}/send", {"round": 1, "notes": [note], "verdicts": {}})
        self.assertEqual((s, b["status"]), (200, "sent"))
        stills = self.root / "my-project/_review/03-x/r1/stills"
        self.assertEqual(sorted(p.name for p in stills.glob("*.jpg")),
                         ["frame-10.jpg", "frame-15.jpg", "frame-20.jpg"])
        idx = json.loads((self.root / "_review-index.json").read_text())
        self.assertEqual(idx["videos"][0]["status"], "sent")

    def test_send_round1_empty_approves(self):
        s, b = self.post(f"/api/videos/{VID}/send", {"round": 1, "notes": [], "verdicts": {}})
        self.assertEqual(b["status"], "approved")

    def test_send_rejects_malformed_note(self):
        bad = [{"start": 5, "end": 2, "tag": "picture", "text": "x"}]
        req = urllib.request.Request(self.base + f"/api/videos/{VID}/send", method="POST",
                                     data=json.dumps({"round": 1, "notes": [{"id": "../x", "start": 1, "end": 2,
                                                                             "tag": "picture", "text": "x"}],
                                                      "verdicts": {}}).encode())
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 400)
        s, b = self.post(f"/api/videos/{VID}/send", {"round": 1, "notes": bad, "verdicts": {}})
        notes = json.loads((self.root / "my-project/_review/03-x/notes-r1.json").read_text())["notes"]
        self.assertRegex(notes[0]["id"], r"^[A-Za-z0-9_-]+$")
        self.assertEqual((notes[0]["start"], notes[0]["end"]), (2, 5))

    def test_foreign_host_rejected(self):
        s, _, _ = self.get("/api/videos", {"Host": "evil.example:47615"})
        self.assertEqual(s, 403)
        req = urllib.request.Request(self.base + f"/api/videos/{VID}/send", method="POST",
                                     data=b'{"round":1,"notes":[],"verdicts":{}}',
                                     headers={"Origin": "https://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 403)

    def test_multi_range_gets_full_body(self):
        size = (self.root / "my-project/_review/03-x/r1.mp4").stat().st_size
        s, h, b = self.get(f"/media/{VID}/r1.mp4", {"Range": "bytes=0-1,5-6"})
        self.assertEqual((s, len(b)), (200, size))

    def test_missing_verdict_rejected(self):
        note = {"id": "a", "start": 10, "end": 12, "tag": "picture", "text": "flash"}
        self.post(f"/api/videos/{VID}/send", {"round": 1, "notes": [note], "verdicts": {}})
        fx = self.root / "fixes.json"
        fx.write_text(json.dumps({"answers": [{"note_id": "a", "explanation": "fixed"}]}))
        env = dict(os.environ, REVIEW_ROOT=str(self.root))
        subprocess.run([sys.executable, str(HERE.parent / "review.py"), "register", "--project", "my-project",
                        "--title", "03 X", "--render", str(self.root / "c.mp4"), "--fixes", str(fx)],
                       env=env, check=True, capture_output=True)
        req = urllib.request.Request(self.base + f"/api/videos/{VID}/send", method="POST",
                                     data=json.dumps({"round": 2, "notes": [], "verdicts": {}}).encode())
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 400)
        s, b = self.post(f"/api/videos/{VID}/send", {"round": 2, "notes": [], "verdicts": {"a": "fixed"}})
        self.assertEqual(b["status"], "approved")

    def test_author_from_env(self):
        note = {"id": "a", "start": 1, "end": 2, "tag": "sound", "text": "pop"}
        self.post(f"/api/videos/{VID}/send", {"round": 1, "notes": [note], "verdicts": {}})
        n = json.loads((self.root / "my-project/_review/03-x/notes-r1.json").read_text())["notes"][0]
        self.assertEqual(n["author"], os.environ.get("REVIEW_AUTHOR", "reviewer"))

    def test_installable_app_assets(self):
        s, h, b = self.get("/ui/manifest.webmanifest")
        self.assertEqual(s, 200)
        m = json.loads(b)
        self.assertEqual((m["name"], m["display"], m["start_url"]), ("Video Review", "standalone", "/"))
        for icon in m["icons"]:
            self.assertEqual(self.get(icon["src"])[0], 200, icon["src"])
        self.assertEqual(self.get("/sw.js")[0], 200)

    def test_ui_served(self):
        s, h, b = self.get("/")
        self.assertEqual(s, 200)
        self.assertIn("text/html", h["Content-Type"])


if __name__ == "__main__":
    unittest.main()
