"""review.py CLI: register, claim, show, list."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _fx import make_clip  # noqa: E402

CLI = HERE.parent / "review.py"


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = tempfile.TemporaryDirectory()
        d = Path(cls.fx.name)
        cls.clip = make_clip(d / "c.mp4")
        cls.clip2 = make_clip(d / "c2.mp4")
        cls.mute = make_clip(d / "m.mp4", audio=False)

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "milan-content").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        env = dict(os.environ, REVIEW_ROOT=str(self.root))
        return subprocess.run([sys.executable, str(CLI), *args], env=env, capture_output=True, text=True)

    def register(self, render, title="03 X", *extra):
        return self.run_cli("register", "--project", "milan-content", "--title", title, "--render", str(render), *extra)

    def vdir(self, slug="03-x"):
        return self.root / "milan-content" / "_review" / slug

    def send(self, rnd, notes, verdicts=None):
        sys.path.insert(0, str(HERE.parent))
        import store
        store.apply_send(self.vdir(), rnd, notes, verdicts or {})
        store.rebuild_index(self.root)

    def test_register_first_round(self):
        r = self.register(self.clip)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.vdir()
        for f in ["video.json", "r1.mp4", "r1/sprite.jpg", "r1/sprite.json", "r1/peaks.json"]:
            self.assertTrue((v / f).exists(), f)
        self.assertEqual(json.loads((v / "video.json").read_text())["status"], "waiting")
        self.assertEqual(json.loads((v / "r1" / "sprite.json").read_text())["frames"], 60)
        self.assertTrue((self.root / "_review-index.json").exists())

    def test_register_second_round_requires_fixes(self):
        self.register(self.clip)
        self.send(1, [{"id": "a", "round": 1, "start": 20, "end": 22, "tag": "picture", "text": "x"}])
        r = self.register(self.clip2)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--fixes", r.stderr)

    def test_fixes_missing_answer_rejected(self):
        self.register(self.clip)
        self.send(1, [{"id": "a", "round": 1, "start": 20, "end": 22, "tag": "picture", "text": "x"},
                      {"id": "b", "round": 1, "start": 30, "end": 30, "tag": "sound", "text": "pop"}])
        fx = self.root / "fixes.json"
        fx.write_text(json.dumps({"answers": [{"note_id": "a", "explanation": "cut"}]}))
        r = self.register(self.clip2, "03 X", "--fixes", str(fx))
        self.assertEqual(r.returncode, 2)
        self.assertIn("b", r.stderr)

    def test_fixes_default_after_range(self):
        self.register(self.clip)
        self.send(1, [{"id": "a", "round": 1, "start": 20, "end": 22, "tag": "picture", "text": "x"}])
        fx = self.root / "fixes.json"
        fx.write_text(json.dumps({"answers": [{"note_id": "a", "explanation": "removed the flash"}]}))
        r = self.register(self.clip2, "03 X", "--fixes", str(fx))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(list((self.vdir() / "fixcheck-r2").glob("a-*.jpg")))
        self.assertEqual(json.loads((self.vdir() / "video.json").read_text())["status"], "fixes_ready")

    def test_claim_then_claim_again_exit3(self):
        self.register(self.clip)
        self.send(1, [{"id": "a", "round": 1, "start": 20, "end": 22, "tag": "picture", "text": "x"}])
        r = self.run_cli("claim", "milan-content/03-x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claimed milan-content/03-x round 1", r.stdout)
        r = self.run_cli("claim", "milan-content/03-x")
        self.assertEqual(r.returncode, 3)
        self.assertIn("already picked up", r.stdout + r.stderr)

    def test_show_lists_still_paths(self):
        self.register(self.clip)
        still_dir = self.vdir() / "r1" / "stills"
        still_dir.mkdir(parents=True)
        (still_dir / "frame-20.jpg").write_bytes(b"x")
        self.send(1, [{"id": "a", "round": 1, "start": 20, "end": 22, "tag": "picture", "text": "flash"}])
        r = self.run_cli("show", "milan-content/03-x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("flash", r.stdout)
        self.assertIn(str(still_dir / "frame-20.jpg"), r.stdout)

    def test_register_no_audio_render(self):
        r = self.register(self.mute, "Motion piece")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.vdir("motion-piece") / "r1" / "peaks.json").read_text()), [])

    def test_unsafe_title_registers(self):
        r = self.register(self.clip, "03 Context first / v2 é")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.vdir("03-context-first-v2-e").exists())

    def test_fixes_past_end_explains(self):
        self.register(self.clip)
        self.send(1, [{"id": "a", "round": 1, "start": 50, "end": 55, "tag": "picture", "text": "x"}])
        short = Path(self.fx.name) / "short.mp4"
        if not short.exists():
            make_clip(short, seconds=1)
        fx = self.root / "fixes.json"
        fx.write_text(json.dumps({"answers": [{"note_id": "a", "explanation": "cut"}]}))
        r = self.register(short, "03 X", "--fixes", str(fx))
        self.assertEqual(r.returncode, 2)
        self.assertIn("past the end", r.stderr)
        self.assertEqual(json.loads((self.vdir() / "video.json").read_text())["status"], "sent")

    def test_fixes_different_size_render(self):
        self.register(self.clip)
        self.send(1, [{"id": "a", "round": 1, "start": 20, "end": 22, "tag": "picture", "text": "x"}])
        big = Path(self.fx.name) / "big.mp4"
        if not big.exists():
            make_clip(big, w=128, h=192)
        fx = self.root / "fixes.json"
        fx.write_text(json.dumps({"answers": [{"note_id": "a", "explanation": "cut"}]}))
        r = self.register(big, "03 X", "--fixes", str(fx))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bad_project_name_rejected(self):
        r = self.run_cli("register", "--project", "My Project", "--title", "x", "--render", str(self.clip))
        self.assertEqual(r.returncode, 2)
        self.assertIn("project", r.stderr)

    def test_reregister_while_waiting_adds_round(self):
        self.register(self.clip)
        r = self.register(self.clip2)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = json.loads((self.vdir() / "video.json").read_text())
        self.assertEqual((len(v["rounds"]), v["status"]), (2, "waiting"))

    def test_list(self):
        self.register(self.clip)
        r = self.run_cli("list")
        self.assertIn("milan-content/03-x", r.stdout)
        self.assertIn("waiting", r.stdout)


if __name__ == "__main__":
    unittest.main()
