"""Output timeline = real segment lengths, not EDL arithmetic.

Each extracted segment is rounded up to whole frames, so after N cuts the
nominal sum (end - start per range) runs ahead of the real video by up to a
frame per cut. Captions and overlays must follow the real lengths.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "helpers" / "render.py"
SPEC = importlib.util.spec_from_file_location("video_use_render", MODULE_PATH)
assert SPEC and SPEC.loader
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)

WORDS = [
    {"text": "one", "start": 0.10, "end": 0.40, "type": "word"},
    {"text": "two.", "start": 5.10, "end": 5.40, "type": "word"},
]
EDL = {"sources": {"A": "A.mp4"},
       "ranges": [{"source": "A", "start": 0.0, "end": 1.0}, {"source": "A", "start": 5.0, "end": 6.5}]}


class CaptionOffsetTests(unittest.TestCase):
    def test_second_segment_cues_start_after_real_first_segment(self):
        with tempfile.TemporaryDirectory() as d:
            edit = Path(d)
            (edit / "transcripts").mkdir()
            (edit / "transcripts" / "A.json").write_text(json.dumps({"words": WORDS}))
            out = edit / "master.srt"
            render.build_master_srt(EDL, edit, out, seg_durations=[1.0333, 1.5333])
            cues = [b.splitlines() for b in out.read_text().strip().split("\n\n")]
            self.assertEqual(cues[1][1].split(" --> ")[0], "00:00:01,133")

    def test_nominal_offsets_without_real_durations(self):
        with tempfile.TemporaryDirectory() as d:
            edit = Path(d)
            (edit / "transcripts").mkdir()
            (edit / "transcripts" / "A.json").write_text(json.dumps({"words": WORDS}))
            out = edit / "master.srt"
            render.build_master_srt(EDL, edit, out)
            cues = [b.splitlines() for b in out.read_text().strip().split("\n\n")]
            self.assertEqual(cues[1][1].split(" --> ")[0], "00:00:01,100")


class OutputTimeMapTests(unittest.TestCase):
    REAL = [1.0333, 1.5333]

    def test_inside_first_segment_unchanged(self):
        self.assertAlmostEqual(render.real_output_time(0.5, EDL["ranges"], self.REAL), 0.5)

    def test_later_segment_shifted_by_rounding(self):
        # nominal 1.2 = 0.2s into segment 2, which really starts at 1.0333
        self.assertAlmostEqual(render.real_output_time(1.2, EDL["ranges"], self.REAL), 1.2333)

    def test_past_the_end_shifts_by_total_rounding(self):
        self.assertAlmostEqual(render.real_output_time(3.0, EDL["ranges"], self.REAL), 3.0666)

    def test_overlays_mapped_to_real_timeline(self):
        ovs = [{"file": "x.mp4", "start_in_output": 1.2, "duration": 1.0}]
        got = render.map_overlays(ovs, EDL["ranges"], self.REAL)
        self.assertAlmostEqual(got[0]["start_in_output"], 1.2333)
        self.assertAlmostEqual(got[0]["duration"], 1.0)
        self.assertEqual(ovs[0]["start_in_output"], 1.2)  # input untouched


if __name__ == "__main__":
    unittest.main()
