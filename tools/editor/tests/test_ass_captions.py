import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"


def load(name):
    spec = importlib.util.spec_from_file_location(f"video_use_{name}_asst", HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ass = load("ass_captions")
render = load("render")


class AssBasicsTests(unittest.TestCase):
    def test_time_format(self):
        self.assertEqual(ass.ass_time(3723.456), "1:02:03.46")
        self.assertEqual(ass.ass_time(0.0), "0:00:00.00")

    def test_header_sizes_follow_the_frame(self):
        h = ass.header(1080, 1920)
        self.assertIn("PlayResX: 1080", h)
        self.assertIn("PlayResY: 1920", h)
        self.assertIn("Style: Caption,IBM Plex Sans,120,", h)  # same size as the proven SRT style
        self.assertIn("Style: Hook,IBM Plex Sans,", h)

    def test_caption_text_upper_with_teal_keyword(self):
        self.assertEqual(ass.caption_text([("linkedin", False), ("video", True)]),
                         r"LINKEDIN {\1c&H00B4B400&}VIDEO{\r}")

    def test_override_characters_are_stripped(self):
        self.assertEqual(ass.caption_text([("a{b}\\c", False)]), "ABC")

    def test_hook_event_on_top_style_for_its_seconds(self):
        self.assertEqual(ass.hook_event("My AI agent {does} my work", 3),
                         "Dialogue: 1,0:00:00.00,0:00:03.00,Hook,,0,0,0,,My AI agent does my work")


class BrandTests(unittest.TestCase):
    def test_brand_font_and_colours_in_header(self):
        h = ass.header(1080, 1920, {"font": "Franklin Gothic Demi Cond", "text": "#FFFFFF", "dark": "#000000"})
        self.assertIn("Style: Caption,Franklin Gothic Demi Cond,120,&H00FFFFFF,&H00FFFFFF,&H00000000,", h)

    def test_brand_box_and_height(self):
        h = ass.header(1080, 1920, {"box": True, "margin_v": 0.3})
        cap = next(l for l in h.splitlines() if l.startswith("Style: Caption,"))
        f = cap.split(",")
        self.assertEqual(f[15], "3")            # BorderStyle 3 = opaque box
        self.assertEqual(f[-2], "576")          # MarginV = 30% of 1920

    def test_hex_to_ass(self):
        self.assertEqual(ass.ass_colour("#00B4B4"), "&H00B4B400")

    def test_active_fill_colours_the_word_not_the_outline(self):
        t = ass.active_text(["the", "waiter"], 1, mode="fill")
        self.assertIn(r"{\1c&H00B4B400&}WAITER{\r}", t)
        self.assertNotIn(r"\3c", t)

    def test_active_box_is_default(self):
        self.assertIn(r"\3c", ass.active_text(["a", "b"], 0))


class RenderAssTests(unittest.TestCase):
    def build(self, edl_extra):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "transcripts").mkdir()
            words = [{"type": "word", "text": t, "start": s, "end": e}
                     for t, s, e in [("LinkedIn", 1.0, 1.4), ("video", 1.4, 1.8), ("content.", 1.8, 2.4)]]
            (d / "transcripts" / "A.json").write_text(json.dumps({"words": words}), encoding="utf-8")
            edl = {"sources": {"A": "a.mp4"}, "ranges": [{"source": "A", "start": 0.9, "end": 2.5}], **edl_extra}
            out = d / "master.ass"
            render.build_master_srt(edl, d, out, frame_size=(1080, 1920))
            return out.read_text(encoding="utf-8")

    def test_keyword_marked_by_source_and_time(self):
        text = self.build({"keywords": [{"source": "A", "t": 1.4}]})
        self.assertIn(r"{\1c&H00B4B400&}VIDEO{\r}", text)
        self.assertEqual(text.count(r"\1c"), 1)

    def test_no_keywords_no_colour(self):
        self.assertNotIn(r"\1c", self.build({}))

    def test_brand_reaches_the_ass(self):
        text = self.build({"captions": "active", "brand": {"font": "Arial Black", "active": "fill"}})
        self.assertIn("Style: Caption,Arial Black,", text)
        self.assertIn(r"\1c&H00B4B400&", text)

    def test_hook_title_written(self):
        text = self.build({"hook_title": {"text": "Editing is not the bottleneck", "seconds": 3}})
        self.assertIn(",Hook,,0,0,0,,Editing is not the bottleneck", text)

    def test_subtitles_filter_uses_bundled_fonts_and_no_force_style_for_ass(self):
        f = render.subtitles_filter(Path("C:/x/master.ass"), Path("C:/v/fonts"))
        self.assertIn("fontsdir='C\\:/v/fonts'", f)
        self.assertNotIn("force_style", f)
        self.assertIn("force_style", render.subtitles_filter(Path("C:/x/master.srt"), Path("C:/v/fonts")))


class ZoomTests(unittest.TestCase):
    def test_punch_in_crops_then_rescales(self):
        vf = render.segment_vf(portrait=True, hdr=False, draft=False, grade_filter="", zoom=1.1)
        self.assertEqual(vf, "scale=-2:1920,crop=trunc(iw/1.1/2)*2:trunc(ih/1.1/2)*2,scale=-2:1920")

    def test_punch_in_scales_back_to_the_exact_frame_size(self):
        # crop rounding made zoomed segments 1078 wide next to 1080 ones (2026-11-06)
        vf = render.segment_vf(portrait=True, hdr=False, draft=False, grade_filter="", zoom=1.18, size=(1080, 1920))
        self.assertTrue(vf.endswith("scale=1080:1920"), vf)

    def test_frame_size_matches_the_unzoomed_scale(self):
        self.assertEqual(render.scaled_size((1080, 1920), portrait=True, draft=False), (1080, 1920))
        self.assertEqual(render.scaled_size((2160, 3840), portrait=True, draft=False), (1080, 1920))
        self.assertEqual(render.scaled_size((1080, 1920), portrait=True, draft=True), (720, 1280))
        self.assertEqual(render.scaled_size((1920, 1080), portrait=True, draft=False), (1080, 1920))  # rotated

    def test_no_zoom_unchanged(self):
        self.assertEqual(render.segment_vf(portrait=True, hdr=False, draft=False, grade_filter="eq=contrast=1.03"),
                         "scale=-2:1920,eq=contrast=1.03")


class PackDefaultTests(unittest.TestCase):
    def test_pauses_listed_from_015s(self):
        pack = load("pack_transcripts")
        md = pack.render_markdown([("T", 2.0, [{"start": 0, "end": 2, "text": "x", "speaker_id": None}],
                                    [[0.5, 0.67]])], 0.5)
        self.assertIn("pauses ≥0.15s", md)
        self.assertIn("[000.50-000.67 0.17]", md)


if __name__ == "__main__":
    unittest.main()
