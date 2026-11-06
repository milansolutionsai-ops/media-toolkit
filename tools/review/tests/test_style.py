"""Style rounds: candidates, reactions, summary, index."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import store  # noqa: E402
import style  # noqa: E402
from _fx import make_clip  # noqa: E402

P = "my-project"


class StyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = tempfile.TemporaryDirectory()
        d = Path(cls.fx.name)
        cls.clip = make_clip(d / "v.mp4", seconds=1)
        cls.wide = make_clip(d / "w.mp4", seconds=1, w=96, h=64, audio=False)

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / P).mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def two(self):
        n = style.new_round(self.root, P, "Round one")
        a = style.add_candidate(self.root, P, n, self.clip, "Bold captions", "captions", "library", technique="bold-caps")
        b = style.add_candidate(self.root, P, n, self.clip, "Whip pan", "transition", "claude", explain="new idea")
        return n, a, b

    def test_new_round_and_add_candidates(self):
        n, a, b = self.two()
        d = style.style_dir(self.root, P, n)
        self.assertEqual((a["id"], b["id"]), ("c1", "c2"))
        self.assertTrue((d / "c-c1.mp4").exists() and (d / "c-c2.mp4").exists())
        r = json.loads((d / "round.json").read_text())
        self.assertEqual((r["status"], r["candidates"][1]["origin"]), ("waiting", "claude"))

    def test_new_round_refused_while_open(self):
        self.two()
        with self.assertRaises(style.RoundOpen):
            style.new_round(self.root, P, "Round two")

    def test_reactions_require_all_verdicts(self):
        n, a, b = self.two()
        with self.assertRaises(ValueError):
            style.apply_reactions(self.root, P, n, {"c1": {"verdict": "keep", "note": ""}}, "")

    def test_all_drop_round_is_sent(self):
        n, a, b = self.two()
        style.apply_reactions(self.root, P, n, {"c1": {"verdict": "drop"}, "c2": {"verdict": "drop"}}, "none of these")
        r = json.loads((style.style_dir(self.root, P, n) / "round.json").read_text())
        self.assertEqual(r["status"], "sent")
        self.assertEqual(style.new_round(self.root, P, "Round two"), 2)

    def test_summary_groups_by_dimension(self):
        n, a, b = self.two()
        style.apply_reactions(self.root, P, n, {"c1": {"verdict": "keep", "note": "love it"},
                                                "c2": {"verdict": "maybe", "note": "slower"}}, "")
        s = style.summary(self.root, P)
        self.assertIn("captions", s)
        self.assertIn("KEEP Bold captions", s)
        self.assertIn("love it", s)
        self.assertIn("MAYBE Whip pan", s)
        self.assertIn("Claude's idea", s)

    def test_index_lists_style_round_with_kind(self):
        n, a, b = self.two()
        style.apply_reactions(self.root, P, n, {"c1": {"verdict": "keep"}, "c2": {"verdict": "drop"}}, "")
        store.rebuild_index(self.root)
        idx = json.loads((self.root / "_review-index.json").read_text())
        e = next(v for v in idx["videos"] if v["kind"] == "style")
        self.assertEqual((e["id"], e["status"], e["round_label"], e["notes_count"]),
                         (f"{P}/style-1", "sent", "Style round 1", 2))

    def test_cli_claim_twice_exit3(self):
        n, a, b = self.two()
        style.apply_reactions(self.root, P, n, {"c1": {"verdict": "keep"}, "c2": {"verdict": "drop"}}, "")
        env = dict(os.environ, REVIEW_ROOT=str(self.root))
        run = lambda: subprocess.run([sys.executable, str(HERE.parent / "style.py"), "claim", P, "1"],
                                     env=env, capture_output=True, text=True)
        self.assertEqual(run().returncode, 0)
        self.assertEqual(run().returncode, 3)

    def test_no_audio_horizontal_candidate(self):
        n = style.new_round(self.root, P, "Wide")
        c = style.add_candidate(self.root, P, n, self.wide, "Wide grade", "grade", "claude")
        self.assertGreater(c["width"], c["height"])


if __name__ == "__main__":
    unittest.main()
