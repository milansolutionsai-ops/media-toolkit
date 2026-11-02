"""Opt-in caption/frame modes: sentence captions, handle watermark, alternating reframe."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"


def load(name):
    spec = importlib.util.spec_from_file_location(f"video_use_{name}_modes", HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ass = load("ass_captions")
render = load("render")


def w(text, start, end):
    return {"type": "word", "text": text, "start": start, "end": end}


WORDS = [w("The", 0.1, 0.3), w("waiter", 0.3, 0.6), w("is", 0.6, 0.7), w("the", 0.7, 0.8), w("API.", 0.8, 1.2),
         w("That's", 1.4, 1.6), w("actually", 1.6, 2.0), w("good.", 2.0, 2.3)]


def master(edl_extra):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "transcripts").mkdir()
        (d / "transcripts" / "A.json").write_text(json.dumps({"words": WORDS}))
        edl = {"sources": {"A": "A.mp4"}, "ranges": [{"source": "A", "start": 0.0, "end": 2.5}], **edl_extra}
        out = d / "master.ass"
        render.build_master_srt(edl, d, out, frame_size=(1080, 1920))
        return out.read_text(encoding="utf-8")


class SentenceCaptionTests(unittest.TestCase):
    def test_chunk_sentences_breaks_on_terminal_punctuation(self):
        got = [[x["text"] for x in c] for c in render.chunk_sentences(WORDS)]
        self.assertEqual(got, [["The", "waiter", "is", "the", "API."], ["That's", "actually", "good."]])

    def test_long_sentence_splits_at_max_words(self):
        long = [w(f"w{i}", i * 0.2, i * 0.2 + 0.15) for i in range(20)]
        self.assertTrue(all(len(c) <= render.SENTENCE_MAX_WORDS for c in render.chunk_sentences(long)))

    def test_sentence_mode_uses_sentence_style_and_natural_case(self):
        text = master({"captions": "sentence"})
        self.assertIn("Style: Sentence,", text)
        self.assertIn(",Sentence,,0,0,0,,The waiter is the API.", text)
        self.assertNotIn(",Caption,,", text)

    def test_default_mode_unchanged(self):
        text = master({})
        self.assertIn(",Caption,,0,0,0,,THE WAITER", text)


class WatermarkTests(unittest.TestCase):
    def test_watermark_runs_the_whole_video(self):
        text = master({"watermark": "milan veljkovikj"})
        line = next(l for l in text.splitlines() if ",Watermark," in l and l.startswith("Dialogue"))
        self.assertIn("0:00:00.00,0:00:02.50", line)
        self.assertTrue(line.endswith("milan veljkovikj"))

    def test_no_watermark_by_default(self):
        self.assertNotIn("Dialogue: 0,0:00:00.00,0:00:02.50,Watermark", master({}))


class ReframeTests(unittest.TestCase):
    def test_alternate_ranges_get_the_reframe_zoom(self):
        ranges = [{}, {}, {"zoom": 1.1}, {}, {}]
        self.assertEqual(render.effective_zooms(ranges, 1.15), [1.0, 1.15, 1.1, 1.0, 1.15])

    def test_explicit_zoom_counts_as_tight_so_the_next_is_wide(self):
        self.assertEqual(render.effective_zooms([{"zoom": 1.1}, {}, {}], 1.15), [1.1, 1.0, 1.15])

    def test_no_reframe_keeps_explicit_zooms_only(self):
        self.assertEqual(render.effective_zooms([{}, {"zoom": 1.1}], None), [1.0, 1.1])


if __name__ == "__main__":
    unittest.main()
