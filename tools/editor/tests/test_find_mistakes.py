import importlib.util
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"
SPEC = importlib.util.spec_from_file_location("video_use_find_mistakes", HELPERS / "find_mistakes.py")
fm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fm)


def words(*items):
    """items: (text, start, end)"""
    return [{"text": t, "start": s, "end": e, "type": "word"} for t, s, e in items]


class FindMistakesTests(unittest.TestCase):
    def test_stutter_cuts_first_copy(self):
        c = fm.find_candidates(words(("the", 0.0, 0.2), ("the", 0.3, 0.5), ("editor", 0.5, 0.9)))
        st = [x for x in c if x["type"] == "stutter"]
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["cut"], [0.0, 0.3])

    def test_restart_keeps_newer_take(self):
        w = words(("Then", 0.0, 0.2), ("I", 0.2, 0.3), ("watch", 0.3, 0.6), ("it", 0.6, 0.7), ("once", 0.7, 1.0),
                  ("Then", 2.5, 2.7), ("I", 2.7, 2.8), ("watch", 2.8, 3.1), ("it", 3.1, 3.2), ("once,", 3.2, 3.5),
                  ("start", 3.5, 3.8), ("to", 3.8, 3.9), ("finish.", 3.9, 4.4))
        c = [x for x in fm.find_candidates(w) if x["type"] in ("retake", "false_start")]
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["cut"], [0.0, 2.5])
        self.assertIn("finish", c[0]["keeps"])

    def test_different_sentences_are_not_retakes(self):
        w = words(("Editing", 0.0, 0.4), ("takes", 0.4, 0.7), ("hours", 0.7, 1.1),
                  ("Captions", 2.5, 3.0), ("render", 3.0, 3.4), ("automatically", 3.4, 4.2))
        self.assertFalse([x for x in fm.find_candidates(w) if x["type"] in ("retake", "false_start")])

    def test_phrase_said_twice_keeps_second(self):
        w = words(("what", 0.0, 0.2), ("goes", 0.2, 0.4), ("in,", 0.4, 0.6), ("what", 0.6, 0.8), ("happens", 0.8, 1.2),
                  ("what", 1.6, 1.8), ("goes", 1.8, 2.0), ("in,", 2.0, 2.2), ("what", 2.2, 2.4), ("happens", 2.4, 2.8),
                  ("next", 2.8, 3.1))
        c = [x for x in fm.find_candidates(w) if x["type"] == "phrase_repeat"]
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["cut"], [0.0, 1.6])

    def test_two_word_emphasis_not_flagged(self):
        w = words(("never,", 0.0, 0.3), ("never", 0.4, 0.7), ("hands", 0.7, 1.0), ("off", 1.0, 1.3))
        self.assertFalse([x for x in fm.find_candidates(w) if x["type"] == "phrase_repeat"])

    def test_stretched_word_flagged_for_retranscription(self):
        c = fm.find_candidates(words(("what", 0.0, 0.2), ("goes", 0.2, 1.8), ("in", 1.8, 2.0)))
        sus = [x for x in c if x["type"] == "suspect"]
        self.assertEqual(len(sus), 1)
        self.assertEqual(sus[0]["recommend"], "re-transcribe")


if __name__ == "__main__":
    unittest.main()
