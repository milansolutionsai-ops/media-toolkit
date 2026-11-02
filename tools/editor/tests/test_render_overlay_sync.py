"""An overlay's frame 0 must land exactly at start_in_output (Hard Rule 4).

Real ffmpeg run on generated clips: the overlay's brightness encodes its own
frame number, so the composite tells us which overlay frame is on screen.
"""
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "helpers" / "render.py"
SPEC = importlib.util.spec_from_file_location("video_use_render", MODULE_PATH)
assert SPEC and SPEC.loader
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def luma_at(video: Path, t: float) -> float:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
         "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip().splitlines()[-1].split("=")[1])


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class OverlaySyncTests(unittest.TestCase):
    def test_overlay_frame_zero_lands_at_window_start(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # a base built like render's: phone-rate segments (30.003 fps), concat -c copy
            segs = []
            for i in range(3):
                seg = d / f"seg{i}.mp4"
                ff("-f", "lavfi", "-i", "color=gray:s=160x288:r=30:d=2.01", "-f", "lavfi", "-i", "sine=d=2.01",
                   "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "9211/307",
                   "-c:a", "aac", "-ar", "48000", "-shortest", str(seg))
                segs.append(seg)
            base = d / "base.mp4"
            render.concat_segments(segs, base, d)
            ov = d / "ov.mp4"   # luma = 16 + 4 * frame number
            ff("-f", "lavfi", "-i", "color=black:s=160x288:r=30:d=2", "-vf", "geq=lum='16+4*N':cb=128:cr=128",
               "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(ov))
            out = d / "out.mp4"
            render.build_final_composite(base, [{"file": str(ov), "start_in_output": 3.0, "duration": 2.0}], None, out, d)
            # 1.0s into the window = overlay frame 30 → luma ~136
            self.assertAlmostEqual(luma_at(out, 4.0), 136, delta=12)


if __name__ == "__main__":
    unittest.main()


def duration_of(video: Path, stream: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", "stream=duration",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class FadeAndSpeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.base = self.d / "base.mp4"   # black, 4s, with sound
        ff("-f", "lavfi", "-i", "color=black:s=160x288:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(self.base))
        self.ov = self.d / "ov.mp4"       # white, 2s
        ff("-f", "lavfi", "-i", "color=white:s=160x288:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.ov))

    def tearDown(self):
        self.tmp.cleanup()

    def test_overlay_fade_out_dissolves_into_the_base(self):
        out = self.d / "out.mp4"
        ov = {"file": str(self.ov), "start_in_output": 1.0, "duration": 2.0, "fade_out": 1.0}
        render.build_final_composite(self.base, [ov], None, out, self.d)
        self.assertGreater(luma_at(out, 1.5), 200)              # before the fade: full overlay
        self.assertTrue(60 < luma_at(out, 2.5) < 180)           # halfway through: a dissolve

    def test_speed_shortens_picture_and_sound_together(self):
        out = self.d / "out.mp4"
        render.build_final_composite(self.base, [], None, out, self.d, speed=1.25)
        self.assertAlmostEqual(duration_of(out, "v:0"), 3.2, delta=0.1)
        self.assertAlmostEqual(duration_of(out, "a:0"), 3.2, delta=0.1)
