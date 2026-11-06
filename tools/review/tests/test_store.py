"""Store: folder contract, statuses, claims, index."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store  # noqa: E402

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def note(nid, rnd=1, start=10, end=12, tag="picture"):
    return {"id": nid, "round": rnd, "start": start, "end": end, "tag": tag, "text": "x", "author": "reviewer"}


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.v = store.new_video(self.root, "my-project", "03 X", "03-x", "30/1", 1080, 1920)
        self.vdir = store.video_dir(self.root, "my-project", "03-x")
        store.add_round(self.vdir, None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_slugify_unsafe_title(self):
        self.assertEqual(store.slugify("03 Context first / v2 é"), "03-context-first-v2-e")

    def test_new_video_creates_contract(self):
        v = store.load_video(self.vdir)
        self.assertTrue((self.vdir / "video.json").exists())
        self.assertEqual(v["status"], "waiting")
        self.assertEqual(v["id"], "my-project/03-x")
        self.assertEqual(v["orientation"], "vertical")
        self.assertEqual(v["windows"], {"picture_frames": 4, "sound_seconds": 2, "cut_seconds": 1})

    def test_send_with_notes_is_sent(self):
        self.assertEqual(store.apply_send(self.vdir, 1, [note("a")], {}), "sent")
        self.assertTrue((self.vdir / "notes-r1.json").exists())
        self.assertIsNotNone(store.load_video(self.vdir)["rounds"][0]["sent_at"])

    def test_send_round1_no_notes_is_approved(self):
        self.assertEqual(store.apply_send(self.vdir, 1, [], {}), "approved")
        self.assertEqual(store.load_video(self.vdir)["status"], "approved")

    def _to_round2(self):
        store.apply_send(self.vdir, 1, [note("a")], {})
        store.add_round(self.vdir, {"answers": [{"note_id": "a", "explanation": "fixed"}]})

    def test_round2_sets_fixes_ready(self):
        self._to_round2()
        v = store.load_video(self.vdir)
        self.assertEqual(v["status"], "fixes_ready")
        self.assertTrue(v["rounds"][1]["has_fixes"])
        self.assertTrue((self.vdir / "fixes-r2.json").exists())

    def test_send_all_fixed_no_new_notes_is_approved(self):
        self._to_round2()
        self.assertEqual(store.apply_send(self.vdir, 2, [], {"a": "fixed"}), "approved")

    def test_send_not_fixed_is_sent(self):
        self._to_round2()
        self.assertEqual(store.apply_send(self.vdir, 2, [], {"a": "not-fixed"}), "sent")

    def test_send_fixed_plus_new_note_is_sent(self):
        self._to_round2()
        self.assertEqual(store.apply_send(self.vdir, 2, [note("b", 2)], {"a": "fixed"}), "sent")

    def test_add_round_refuses_existing_slot(self):
        (self.vdir / "r2.mp4").write_bytes(b"x")
        with self.assertRaises(FileExistsError):
            store.add_round(self.vdir, {"answers": []})

    def test_claim_twice_raises(self):
        store.apply_send(self.vdir, 1, [note("a")], {})
        store.claim(self.vdir, 1, NOW)
        with self.assertRaises(store.ClaimTaken):
            store.claim(self.vdir, 1, NOW + timedelta(hours=1))

    def test_stale_claim_replaced(self):
        store.apply_send(self.vdir, 1, [note("a")], {})
        store.claim(self.vdir, 1, NOW)
        c = store.claim(self.vdir, 1, NOW + timedelta(hours=5))
        self.assertEqual(c["at"], (NOW + timedelta(hours=5)).isoformat())

    def test_index_lists_video_without_absolute_paths(self):
        store.apply_send(self.vdir, 1, [note("a"), note("b")], {})
        store.claim(self.vdir, 1, NOW)
        store.rebuild_index(self.root)
        idx = json.loads((self.root / "_review-index.json").read_text(encoding="utf-8"))
        e = idx["videos"][0]
        self.assertEqual(e["id"], "my-project/03-x")
        self.assertEqual(e["status"], "sent")
        self.assertEqual(e["notes_count"], 2)
        self.assertEqual(e["claimed_at"], NOW.isoformat())
        self.assertNotRegex(e["folder"], r"^([A-Za-z]:|/)")

    def test_feedback_count_includes_not_fixed(self):
        self.assertEqual(store.feedback_count({"notes": [note("b", 2)], "verdicts": {"a": "not-fixed", "c": "fixed"}}), 2)
        self.assertEqual(store.feedback_count({"notes": [], "verdicts": {"a": "not-fixed"}}), 1)

    def test_round_label(self):
        self.assertEqual(store.round_label(1), "First cut")
        self.assertEqual(store.round_label(3), "Fix round 2")


if __name__ == "__main__":
    unittest.main()
