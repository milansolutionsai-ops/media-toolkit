"""Technique library: references, techniques, links, brand verdicts."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import library as lib  # noqa: E402


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_reference_dedupes_url_variants(self):
        a = lib.add_reference(self.root, "https://www.instagram.com/reel/X1/?igsh=abc", "instagram", "@someone", "")
        b = lib.add_reference(self.root, "https://WWW.instagram.com/reel/X1", "instagram", "@someone", "more")
        self.assertEqual(a["id"], b["id"])
        refs = json.loads((self.root / "library" / "references.json").read_text())
        self.assertEqual(len(refs), 1)

    def test_youtube_ids_are_separate_references(self):
        a = lib.add_reference(self.root, "https://www.youtube.com/watch?v=AAAA&utm_source=x", "youtube", "a", "")
        b = lib.add_reference(self.root, "https://youtube.com/watch?v=BBBB", "youtube", "b", "")
        c = lib.add_reference(self.root, "https://youtube.com/watch?si=zz&v=AAAA", "youtube", "a", "")
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(a["id"], c["id"])

    def test_unknown_ref_leaves_nothing_half_saved(self):
        with self.assertRaises(KeyError):
            lib.add_technique(self.root, "Orphan", "x", "y", "missing", ref_id="r-nope")
        self.assertEqual(lib.find(self.root, "orphan"), [])

    def test_cli_unknown_id_exits_cleanly(self):
        import os, subprocess
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "library.py"), "link", "r-x", "t-y"],
                           env=dict(os.environ, REVIEW_ROOT=str(self.root)), capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_update_technique(self):
        lib.add_technique(self.root, "Orbit", "text circles", "todo", "missing")
        t = lib.update_technique(self.root, "orbit", status="have", tool="tools/motion/orbit")
        self.assertEqual((t["status"], t["tool"], t["recipe"]), ("have", "tools/motion/orbit", "todo"))
        with self.assertRaises(ValueError):
            lib.update_technique(self.root, "orbit", status="done")

    def test_add_technique_merges_seen_in(self):
        r1 = lib.add_reference(self.root, "https://a.example/1", "web", "a", "")
        r2 = lib.add_reference(self.root, "https://b.example/2", "web", "b", "")
        t1 = lib.add_technique(self.root, "Text behind head", "Words sit behind the speaker", "cutout + title", "partial", ref_id=r1["id"])
        t2 = lib.add_technique(self.root, "Text Behind Head", "different", "different", "missing", ref_id=r2["id"])
        self.assertEqual(t1["id"], t2["id"])
        techs = json.loads((self.root / "library" / "techniques.json").read_text())
        self.assertEqual(len(techs), 1)
        self.assertEqual(sorted(techs[0]["seen_in"]), sorted([r1["id"], r2["id"]]))
        self.assertEqual(techs[0]["what"], "Words sit behind the speaker")

    def test_link_both_directions(self):
        r = lib.add_reference(self.root, "https://a.example/1", "web", "a", "")
        t = lib.add_technique(self.root, "Grain", "film grain", "noise filter", "have")
        lib.link(self.root, r["id"], t["id"])
        refs = json.loads((self.root / "library" / "references.json").read_text())
        techs = json.loads((self.root / "library" / "techniques.json").read_text())
        self.assertIn(t["id"], refs[0]["techniques"])
        self.assertIn(r["id"], techs[0]["seen_in"])

    def test_brand_verdict(self):
        t = lib.add_technique(self.root, "Grain", "film grain", "noise filter", "have")
        lib.set_brand_verdict(self.root, t["id"], "my-brand", "drop")
        techs = json.loads((self.root / "library" / "techniques.json").read_text())
        self.assertEqual(techs[0]["brands"], {"my-brand": "drop"})
        with self.assertRaises(ValueError):
            lib.set_brand_verdict(self.root, t["id"], "my-brand", "love")

    def test_find_case_insensitive(self):
        lib.add_technique(self.root, "Title orbit", "Text circles the head", "3D ring", "missing")
        lib.add_technique(self.root, "Grain", "film grain", "noise", "have")
        self.assertEqual([t["id"] for t in lib.find(self.root, "HEAD")], ["title-orbit"])

    def test_render_groups_by_status(self):
        lib.add_technique(self.root, "A", "a", "a", "have")
        lib.add_technique(self.root, "B", "b", "b", "partial")
        lib.add_technique(self.root, "C", "c", "c", "missing")
        lib.render(self.root)
        md = (self.root / "library" / "LIBRARY.md").read_text(encoding="utf-8")
        for h in ("## Have", "## Partial", "## Missing"):
            self.assertIn(h, md)


if __name__ == "__main__":
    unittest.main()
