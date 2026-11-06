"""ffmpeg side: review copies, sprite, peaks, stills, fix-check assets."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import media  # noqa: E402
from _fx import ffprobe_json, make_clip, mean_luma  # noqa: E402


class MediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.clip = make_clip(cls.d / "clip.mp4")
        cls.mute = make_clip(cls.d / "mute.mp4", audio=False)
        cls.odd = make_clip(cls.d / "odd.mp4", rate="30.003")
        cls.wide = make_clip(cls.d / "wide.mp4", w=96, h=64)
        cls.rev = cls.d / "r1.mp4"
        media.make_review_copy(cls.clip, cls.rev, "30/1")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_snap_fps(self):
        self.assertEqual(media.snap_fps("9211/307"), "30/1")
        self.assertEqual(media.snap_fps("30000/1001"), "30000/1001")
        self.assertEqual(media.snap_fps("25/1"), "25/1")

    def test_probe(self):
        p = media.probe(self.clip)
        self.assertEqual((p["width"], p["height"]), (64, 96))
        self.assertTrue(p["has_audio"])
        self.assertFalse(media.probe(self.mute)["has_audio"])
        self.assertAlmostEqual(p["duration"], 2.0, delta=0.1)

    def test_review_copy_is_all_intra_cfr(self):
        out = self.d / "odd-r1.mp4"
        media.make_review_copy(self.odd, out, media.snap_fps(media.probe(self.odd)["fps"]))
        info = ffprobe_json(out, "-select_streams", "v:0", "-show_entries",
                            "frame=pict_type:stream=r_frame_rate")
        types = {f["pict_type"] for f in info["frames"]}
        self.assertEqual(types, {"I"})
        self.assertEqual(len(info["frames"]), 60)
        self.assertEqual(info["streams"][0]["r_frame_rate"], "30/1")

    def test_review_copy_write_once(self):
        with self.assertRaises(FileExistsError):
            media.make_review_copy(self.clip, self.rev, "30/1")

    def test_extract_stills_exact_frame(self):
        files = media.extract_stills(self.rev, [10, 20], self.d / "stills")
        self.assertEqual([f.name for f in files], ["frame-10.jpg", "frame-20.jpg"])
        # frame N has limited-range Y = N*8; the JPEG decodes to full range
        full = lambda n: (n * 8 - 16) * 255 / 219
        self.assertAlmostEqual(mean_luma(files[0]), full(10), delta=4)
        self.assertAlmostEqual(mean_luma(files[1]), full(20), delta=4)

    def test_peaks_length_and_no_audio(self):
        n = media.make_peaks(self.rev, self.d / "peaks.json")
        vals = json.loads((self.d / "peaks.json").read_text())
        self.assertAlmostEqual(n, 200, delta=2)
        self.assertEqual(len(vals), n)
        self.assertTrue(all(0 <= x <= 1 for x in vals))
        self.assertGreater(max(vals), 0.1)
        mute_rev = self.d / "mute-r1.mp4"
        media.make_review_copy(self.mute, mute_rev, "30/1")
        self.assertEqual(media.make_peaks(mute_rev, self.d / "mpeaks.json"), 0)
        self.assertEqual(json.loads((self.d / "mpeaks.json").read_text()), [])

    def test_sprite_meta(self):
        meta = media.make_sprite(self.rev, self.d / "sprite.jpg", "30/1", every=10)
        self.assertEqual(meta["count"], 6)
        self.assertEqual(meta["every"], 10)
        self.assertTrue((self.d / "sprite.jpg").exists())

    def test_fixcheck_kinds(self):
        out = self.d / "fc"
        r = media.make_fixcheck(self.rev, self.rev, out, "a", "picture", (20, 24), (20, 24), "30/1", "vertical")
        self.assertEqual(r["kind"], "pairs")
        self.assertEqual(len(r["files"]), 13)
        r = media.make_fixcheck(self.rev, self.rev, out, "b", "picture", (5, 45), (5, 45), "30/1", "vertical")
        self.assertEqual(r["kind"], "clip")
        r = media.make_fixcheck(self.rev, self.rev, out, "c", "sound", (20, 25), (20, 25), "30/1", "vertical")
        self.assertEqual(r["kind"], "audio")
        wide_rev = self.d / "wide-r1.mp4"
        media.make_review_copy(self.wide, wide_rev, "30/1")
        r = media.make_fixcheck(wide_rev, wide_rev, out, "d", "cut", (10, 20), (10, 20), "30/1", "horizontal")
        s = ffprobe_json(out / r["files"][0], "-show_entries", "stream=width,height", "-select_streams", "v:0")
        self.assertEqual((s["streams"][0]["width"], s["streams"][0]["height"]), (96, 128))


if __name__ == "__main__":
    unittest.main()
