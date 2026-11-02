import importlib.util
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"
SPEC = importlib.util.spec_from_file_location("video_use_pack", HELPERS / "pack_transcripts.py")
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


class FormatPausesTests(unittest.TestCase):
    def test_lists_pauses_at_or_over_threshold(self):
        line = pack.format_pauses([[6.27, 6.91], [7.67, 7.85], [8.51, 10.75]], 0.3)
        self.assertEqual(line, "  pauses ≥0.3s: [006.27-006.91 0.64] [008.51-010.75 2.24]")

    def test_none_when_no_pauses(self):
        self.assertIsNone(pack.format_pauses([[7.67, 7.85]], 0.3))
        self.assertIsNone(pack.format_pauses([], 0.3))

    def test_rendered_under_take(self):
        md = pack.render_markdown(
            [("T1", 5.0, [{"start": 0.5, "end": 5.0, "text": "hi", "speaker_id": "speaker_0"}],
              [[1.0, 1.5]])], 0.5, 0.3)
        self.assertIn("  pauses ≥0.3s: [001.00-001.50 0.50]", md)


if __name__ == "__main__":
    unittest.main()
