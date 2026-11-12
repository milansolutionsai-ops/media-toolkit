"""Edit plan stage: Claude posts a plan (timed rows + optional stills), the reviewer OKs or marks rows, then the cut."""
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
import store  # noqa: E402
from _fx import make_clip  # noqa: E402

CLI = HERE.parent / "review.py"
VID = "my-project/03-x"


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "my-project").mkdir()
        self.still = self.root / "s.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=teal:s=54x96",
                        "-frames:v", "1", str(self.still)], check=True)
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({"rows": [
            {"start": 0, "end": 2.8, "text": "Hook, face, HONEST appears", "still": str(self.still)},
            {"start": 2.8, "end": 9.1, "text": "Punch-in on 'too honest'"},
        ]}), encoding="utf-8")
        self.srv = server.make_server(self.root, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def cli(self, *args):
        env = dict(os.environ, REVIEW_ROOT=str(self.root))
        return subprocess.run([sys.executable, str(CLI), *args], env=env, capture_output=True, text=True)

    def post_plan(self):
        r = self.cli("plan", "--project", "my-project", "--title", "03 X", "--plan", str(self.plan))
        self.assertEqual(r.returncode, 0, r.stderr)

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read()

    def send(self, body):
        req = urllib.request.Request(f"{self.base}/api/videos/{VID}/plan/send", data=json.dumps(body).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def vdir(self):
        return self.root / "my-project" / "_review" / "03-x"

    def test_plan_creates_waiting_video_with_rows_and_still(self):
        self.post_plan()
        v = json.loads((self.vdir() / "video.json").read_text())
        self.assertEqual((v["status"], v["rounds"]), ("plan_waiting", []))
        s, b = self.get(f"/api/videos/{VID}")
        d = json.loads(b)
        self.assertEqual(d["round_label"], "Edit plan")
        self.assertEqual([r["id"] for r in d["plan"]["rows"]], ["p1", "p2"])
        self.assertNotIn(str(self.root).replace("\\", "\\\\"), b.decode())
        s, img = self.get(d["plan"]["rows"][0]["still_url"])
        self.assertEqual(s, 200)
        self.assertIsNone(d["plan"]["rows"][1]["still_url"])

    def test_send_needs_every_row_and_a_reason_for_changes(self):
        self.post_plan()
        self.assertEqual(self.send({"verdicts": {"p1": "ok"}})[0], 400)
        self.assertEqual(self.send({"verdicts": {"p1": "ok", "p2": "change"}})[0], 400)
        s, out = self.send({"verdicts": {"p1": "ok", "p2": "change"}, "notes": {"p2": "zoom less"}})
        self.assertEqual((s, out["status"]), (200, "plan_sent"))
        self.assertEqual(self.send({"verdicts": {"p1": "ok", "p2": "ok"}})[0], 400)   # already sent

    def test_sent_plan_reaches_the_hook_index_then_claim_and_show(self):
        self.post_plan()
        self.send({"verdicts": {"p1": "ok", "p2": "change"}, "notes": {"p2": "zoom less"}, "note": "good"})
        idx = json.loads((self.root / store.INDEX_NAME).read_text())["videos"][0]
        self.assertEqual((idx["status"], idx["round_label"], idx["notes_count"]), ("plan_sent", "Edit plan", 1))
        self.assertEqual(self.cli("claim", VID).returncode, 0)
        out = self.cli("show", VID).stdout
        self.assertIn("p2", out)
        self.assertIn("zoom less", out)
        self.assertIn("change", out)
        self.assertIn("good", out)

    def test_render_after_sent_plan_becomes_first_cut(self):
        self.post_plan()
        self.send({"verdicts": {"p1": "ok", "p2": "ok"}})
        clip = make_clip(self.root / "c.mp4")
        r = self.cli("register", "--project", "my-project", "--title", "03 X", "--render", str(clip))
        self.assertEqual(r.returncode, 0, r.stderr)
        v = json.loads((self.vdir() / "video.json").read_text())
        self.assertEqual((v["status"], len(v["rounds"]), v["width"]), ("waiting", 1, 64))
        d = json.loads(self.get(f"/api/videos/{VID}")[1])
        self.assertEqual(d["plan"]["verdicts"], {"p1": "ok", "p2": "ok"})

    def test_render_before_plan_review_is_refused(self):
        self.post_plan()
        clip = make_clip(self.root / "c.mp4")
        r = self.cli("register", "--project", "my-project", "--title", "03 X", "--render", str(clip))
        self.assertNotEqual(r.returncode, 0)

    def test_revised_plan_keeps_the_old_one(self):
        self.post_plan()
        self.send({"verdicts": {"p1": "change", "p2": "ok"}, "notes": {"p1": "no word"}})
        self.post_plan()
        v = json.loads((self.vdir() / "video.json").read_text())
        self.assertEqual(v["status"], "plan_waiting")
        self.assertTrue((self.vdir() / "plan-v1.json").exists())
        self.assertEqual(json.loads((self.vdir() / "plan.json").read_text())["version"], 2)


if __name__ == "__main__":
    unittest.main()
