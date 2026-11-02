import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "video_use_render_loudnorm", Path(__file__).parents[1] / "helpers" / "render.py")
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)

M = {"input_i": "-29.7", "input_tp": "-11.6", "input_lra": "2.9",
     "input_thresh": "-40.1", "target_offset": "0.2"}


class LoudnormFilterTests(unittest.TestCase):
    def test_aims_under_the_peak_target_to_leave_room_for_aac(self):
        # AAC encoding overshoots true peak by ~0.3 dB (measured: -1.0 target -> -0.7 delivered).
        self.assertIn("TP=-1.5", render.loudnorm_filter())
        self.assertIn("TP=-1.5", render.loudnorm_filter(M))

    def test_second_pass_uses_measurement_linearly(self):
        f = render.loudnorm_filter(M)
        self.assertIn("measured_I=-29.7", f)
        self.assertIn("offset=0.2", f)
        self.assertTrue(f.endswith(":linear=true"))


if __name__ == "__main__":
    unittest.main()
