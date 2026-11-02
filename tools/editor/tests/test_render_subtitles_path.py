import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "helpers" / "render.py"
SPEC = importlib.util.spec_from_file_location("video_use_render_subs", MODULE_PATH)
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


class SubtitlesFilterPathTests(unittest.TestCase):
    def test_windows_path_uses_forward_slashes_and_escaped_drive_colon(self):
        got = render.subtitles_filter_path(r"C:\Users\Milan\Desktop\Video Editing\edit\master.srt")
        self.assertEqual(got, r"C\:/Users/Milan/Desktop/Video Editing/edit/master.srt")

    def test_posix_path_unchanged_apart_from_quote_escape(self):
        self.assertEqual(render.subtitles_filter_path("/tmp/it's/master.srt"),
                         r"/tmp/it\'s/master.srt")


class WordsInRangeTests(unittest.TestCase):
    def test_word_cut_off_by_the_range_gets_no_caption(self):
        transcript = {"words": [
            {"type": "word", "text": "Um,", "start": 7.88, "end": 8.26},
            {"type": "spacing", "text": " ", "start": 8.26, "end": 8.26},
            {"type": "word", "text": "today", "start": 8.26, "end": 8.74},
            {"type": "word", "text": "me.", "start": 10.6, "end": 11.2},
        ]}
        got = [w["text"] for w in render._words_in_range(transcript, 8.21, 10.99)]
        # "Um," only grazes the range (0.05s of 0.38s); "me." is mostly inside.
        self.assertEqual(got, ["today", "me."])


if __name__ == "__main__":
    unittest.main()
