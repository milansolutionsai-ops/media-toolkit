import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HELPERS = Path(__file__).parents[1] / "helpers"
SPEC = importlib.util.spec_from_file_location("video_use_clean_audio", HELPERS / "clean_audio.py")
clean = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clean)


class SettingsTests(unittest.TestCase):
    def test_on_by_default(self):
        self.assertEqual(clean.settings_for({}), {"method": "rnnoise", "dry": 0.25})

    def test_switched_off(self):
        self.assertIsNone(clean.settings_for({"audio_clean": False}))
        self.assertIsNone(clean.settings_for({"audio_clean": {"method": "none"}}))

    def test_overrides_merge_over_default(self):
        self.assertEqual(clean.settings_for({"audio_clean": {"dry": 0.1}}),
                         {"method": "rnnoise", "dry": 0.1})

    def test_unknown_method_rejected(self):
        with self.assertRaises(ValueError):
            clean.settings_for({"audio_clean": {"method": "magic"}})


class FilterTests(unittest.TestCase):
    def test_rnnoise_blended_with_original(self):
        self.assertEqual(
            clean.clean_filter("rnnoise", 0.25),
            "[0:a]highpass=f=80,aresample=48000,asplit=2[dry][wet];"
            "[wet]arnndn=m=sh.rnnn[den];[dry]volume=0.25[keep];"
            "[den][keep]amix=inputs=2:weights=1 1:normalize=0[a]",
        )

    def test_no_dry_means_no_blend(self):
        self.assertEqual(clean.clean_filter("rnnoise", 0.0),
                         "[0:a]highpass=f=80,aresample=48000,arnndn=m=sh.rnnn[a]")

    def test_anlmdn_method(self):
        self.assertIn("anlmdn=s=7:p=0.002:r=0.006", clean.clean_filter("anlmdn", 0.25))

    def test_cache_name_carries_the_settings(self):
        p = clean.clean_path(Path("E"), Path("raw/VID_1.mp4"), {"method": "rnnoise", "dry": 0.25})
        self.assertEqual(p, Path("E") / "clean" / "VID_1.rnnoise-d25.mkv")


class CleanSourceTests(unittest.TestCase):
    def make_clip(self, d: Path) -> Path:
        src = d / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
             "-f", "lavfi", "-i", "anoisesrc=d=1:a=0.05:r=48000", "-shortest",
             "-c:v", "libx264", "-c:a", "aac", str(src)],
            check=True,
        )
        return src

    def streams(self, path: Path) -> list[str]:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout
        return sorted(s["codec_type"] for s in json.loads(out)["streams"])

    def test_cleans_audio_keeps_video_and_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = self.make_clip(d)
            out = clean.clean_source(src, d / "edit", {"method": "rnnoise", "dry": 0.25})
            self.assertEqual(self.streams(out), ["audio", "video"])
            mtime = out.stat().st_mtime_ns
            again = clean.clean_source(src, d / "edit", {"method": "rnnoise", "dry": 0.25})
            self.assertEqual((again, again.stat().st_mtime_ns), (out, mtime))

    def test_missing_model_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(clean, "MODEL", Path(tmp) / "nope.rnnn"):
                with self.assertRaisesRegex(RuntimeError, "sh.rnnn"):
                    clean.clean_source(Path(tmp) / "x.mp4", Path(tmp), {"method": "rnnoise", "dry": 0.25})


class EdlTests(unittest.TestCase):
    def test_sources_swapped_for_cleaned_copies(self):
        edl = {"sources": {"A": "raw/a.mp4"}, "ranges": []}
        with patch.object(clean, "clean_source", return_value=Path("E/clean/a.rnnoise-d25.mkv")) as cs:
            out = clean.with_clean_sources(edl, Path("E"))
        self.assertEqual(out["sources"], {"A": str(Path("E/clean/a.rnnoise-d25.mkv"))})
        self.assertEqual(edl["sources"], {"A": "raw/a.mp4"})  # input untouched
        self.assertEqual(cs.call_args.args[0], Path("E") / "raw/a.mp4")

    def test_off_returns_edl_unchanged(self):
        edl = {"sources": {"A": "raw/a.mp4"}, "audio_clean": False}
        with patch.object(clean, "clean_source") as cs:
            self.assertIs(clean.with_clean_sources(edl, Path("E")), edl)
        cs.assert_not_called()


class RenderWiringTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("video_use_render_wiring", HELPERS / "render.py")
        self.render = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.render)

    def test_render_cleans_sources_by_default(self):
        edl = {"sources": {"A": "a.mp4"}}
        with patch.object(self.render.clean_audio, "with_clean_sources", return_value={"x": 1}) as w:
            self.assertEqual(self.render.prepare_sources(edl, Path("E"), clean=True), {"x": 1})
        w.assert_called_once_with(edl, Path("E"))

    def test_no_clean_audio_flag_skips_it(self):
        edl = {"sources": {"A": "a.mp4"}}
        with patch.object(self.render.clean_audio, "with_clean_sources") as w:
            self.assertIs(self.render.prepare_sources(edl, Path("E"), clean=False), edl)
        w.assert_not_called()


if __name__ == "__main__":
    unittest.main()
