"""Milan 2026-11-22, blind A/B on the same 10 s: rubberband at 1.1x 'okay', atempo 'good'. Speed-up uses atempo."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render  # noqa: E402


class SpeedAudioFilter(unittest.TestCase):
    def test_speed_up_uses_atempo_not_rubberband(self):
        self.assertEqual(render.speed_af(1.1), "atempo=1.1")


if __name__ == "__main__":
    unittest.main()
