import importlib.util
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"
SPEC = importlib.util.spec_from_file_location("video_use_align_words", HELPERS / "align_words.py")
align = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(align)


def w(text, start, end):
    return {"type": "word", "text": text, "start": start, "end": end, "speaker_id": "speaker_0"}


def words_only(entries):
    return [(e["text"], e["start"], e["end"]) for e in entries if e["type"] == "word"]


STDERR = """
[silencedetect @ 0x1] silence_start: 0.27775
[silencedetect @ 0x1] silence_end: 0.712021 | silence_duration: 0.434
[silencedetect @ 0x1] silence_start: 14.441042
[silencedetect @ 0x1] silence_end: 15.329792 | silence_duration: 0.888
"""


class ParseTests(unittest.TestCase):
    def test_pairs(self):
        self.assertEqual(
            align.parse_silencedetect(STDERR, 20.0),
            [(0.27775, 0.712021), (14.441042, 15.329792)],
        )

    def test_unterminated_trailing_silence(self):
        out = align.parse_silencedetect(STDERR + "silence_start: 18.5\n", 20.0)
        self.assertEqual(out[-1], (18.5, 20.0))

    def test_speech_spans_are_the_complement(self):
        self.assertEqual(
            align.speech_spans([(0.0, 0.7), (14.4, 15.3)], 20.0),
            [(0.7, 14.4), (15.3, 20.0)],
        )


class SnapTests(unittest.TestCase):
    SPANS = [(0.7, 14.44), (15.33, 20.0)]

    def test_word_stretched_into_pause_is_clamped(self):
        out = align.snap_words([w("Code.", 5.04, 6.46), w("Um,", 6.91, 7.67)], [(0.7, 6.27), (6.91, 7.67)])
        self.assertEqual(words_only(out), [("Code.", 5.04, 6.27), ("Um,", 6.91, 7.67)])

    def test_stretched_word_anchors_on_its_end(self):
        # Verified on a real take: "video" listed 13.96-15.72 is spoken at 15.33-15.72.
        out = align.snap_words([w("video", 13.96, 15.72), w("content", 15.72, 16.26)], self.SPANS)
        self.assertEqual(words_only(out), [("video", 15.33, 15.72), ("content", 15.72, 16.26)])

    def test_raw_times_kept(self):
        out = align.snap_words([w("video", 13.96, 15.72)], self.SPANS)
        self.assertEqual((out[0]["raw_start"], out[0]["raw_end"]), (13.96, 15.72))

    def test_start_stretched_word_goes_to_later_span(self):
        # "I" 8.50-11.40 over a silence 8.51-10.75: the speech is the 10.75+ blip.
        spans = [(5.0, 8.508), (10.75, 10.87), (11.42, 12.21)]
        out = align.snap_words([w("um,", 7.96, 8.50), w("I", 8.50, 11.40)], spans)
        self.assertEqual(words_only(out)[1], ("I", 10.75, 10.87))

    def test_end_span_wins_over_bigger_overlap(self):
        # "test" 11.92-12.88: 0.29s in span A, 0.25s in span B. Spoken in B.
        spans = [(11.42, 12.21), (12.63, 13.09)]
        out = align.snap_words([w("test", 11.92, 12.88)], spans)
        self.assertEqual(words_only(out), [("test", 12.63, 12.88)])

    def test_grazing_overlap_does_not_pull_word(self):
        # The end pokes 0.03s into the next span: not enough to move the word there.
        out = align.snap_words([w("start", 31.06, 32.57)], [(29.96, 31.75), (32.54, 35.99)])
        self.assertEqual(words_only(out), [("start", 31.06, 31.75)])

    def test_overlapping_words_become_monotonic(self):
        out = align.snap_words([w("everything", 18.22, 18.58), w("looks,", 18.16, 18.80)], [(15.0, 18.9)])
        (_, _, e1), (_, s2, e2) = words_only(out)
        self.assertGreaterEqual(s2, e1)
        self.assertGreater(e2, s2)

    def test_word_fully_in_silence_is_flagged(self):
        out = align.snap_words([w("fine.", 56.34, 57.42), w("Thank", 57.44, 57.54)],
                               [(55.0, 56.47)])
        thank = [e for e in out if e.get("text") == "Thank"][0]
        self.assertTrue(thank["in_silence"])
        self.assertEqual((thank["start"], thank["end"]), (57.44, 57.54))

    def test_spacing_rebuilt_between_snapped_words(self):
        out = align.snap_words([w("Code.", 5.04, 6.46), w("Um,", 6.91, 7.67)], [(0.7, 6.27), (6.91, 7.67)])
        spacing = [e for e in out if e["type"] == "spacing"]
        self.assertEqual([(s["start"], s["end"]) for s in spacing], [(6.27, 6.91)])


class AlignTranscriptTests(unittest.TestCase):
    def test_metadata_and_silences_recorded(self):
        tr = {"words": [w("video", 13.96, 15.72)]}
        out = align.align_transcript(tr, [(14.44, 15.33)], 20.0, -35.0, 0.15)
        self.assertEqual(out["alignment"], {"method": "silence-snap", "noise_db": -35.0, "min_silence": 0.15})
        self.assertEqual(out["silences"], [[14.44, 15.33]])
        self.assertNotIn("alignment", tr)  # input untouched

    def test_realign_uses_raw_times(self):
        tr = {"words": [w("video", 13.96, 15.72)]}
        once = align.align_transcript(tr, [(14.44, 15.33)], 20.0, -35.0, 0.15)
        twice = align.align_transcript(once, [(15.5, 16.0)], 20.0, -30.0, 0.15)
        self.assertEqual(words_only(twice["words"]), [("video", 13.96, 15.5)])


if __name__ == "__main__":
    unittest.main()
