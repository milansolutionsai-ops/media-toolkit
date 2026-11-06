"""Whip-pan exit for overlays, text-behind-head hook, active-word captions."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"


def load(name):
    spec = importlib.util.spec_from_file_location(f"video_use_{name}_th", HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


render = load("render")


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def dur(p, s):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", s, "-show_entries", "stream=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


class FilterTextTests(unittest.TestCase):
    def test_whip_slides_left_and_base_settles_from_the_right(self):
        parts, x = render.whip_exit(1, start=2.0, duration=3.0, d=0.2)
        txt = ";".join(parts)
        self.assertIn("boxblur", txt)
        self.assertIn("fade=t=in:st=2.800", txt)       # blur ramps up over the last 0.2s of the overlay
        self.assertIn("4.800", x)                       # slide starts 0.2s before the window ends at 5.0
        settle = ";".join(render.whip_settle("[v1]", "[w1]", end=5.0, d=0.2))
        self.assertIn("between(t,5.000,5.200)", settle)

    def test_hook_behind_draws_each_line_with_its_own_delay(self):
        f = render.hook_behind_text("[0:v]", "[hb]", ["TEXT BEHIND", "YOUR HEAD"], seconds=3.0, height=1920)
        self.assertEqual(f.count("drawtext="), 2)
        self.assertIn("TEXT BEHIND", f)


    def test_hook_text_fades_out_before_the_cutout_ends(self):
        f = render.hook_behind_text("[0:v]", "[hb]", ["AI EDITS"], seconds=3.0, height=1920)
        self.assertNotIn("between(t,0,3.000)", f)      # never shown on the last frame, where the cutout may be gone
        self.assertIn("lt(t,2.950)", f)
        self.assertIn("(3.000-t)/0.250", f)             # fades out over the last 0.25s

    def test_hook_fill_sizes_each_line_to_the_width(self):
        f = render.hook_behind_text("[0:v]", "[hb]", ["AI", "EDITS MY VIDEOS"], 3.0, 1920, width=1080, fill=True)
        sizes = [int(x.split(":")[0]) for x in f.split("fontsize=")[1:]]
        self.assertGreater(sizes[0], sizes[1])          # the short line is set bigger
        self.assertLessEqual(max(sizes), round(1920 * 0.14))

    def test_hook_fill_respects_a_wider_font(self):
        f = render.hook_behind_text("[0:v]", "[hb]", ["MY VIDEOS"], 3.0, 1920, width=1080, fill=True, em=0.8)
        size = int(f.split("fontsize=")[1].split(":")[0])
        self.assertLessEqual(size * 0.8 * len("MY VIDEOS"), 1080 * 0.92 + 1)

    def test_hook_shadow_for_readability(self):
        f = render.hook_behind_text("[0:v]", "[hb]", ["AI EDITS"], 3.0, 1920, shadow=True)
        self.assertIn("shadowcolor=", f)


class ActiveWordTests(unittest.TestCase):
    def test_active_cues_never_stack(self):
        ev = [(0.0, 0.04, "A"), (0.04, 0.5, "B"), (0.4, 0.9, "C")]
        out = render.finalize_active(ev)
        self.assertEqual([t for _, _, t in out], ["B", "C"])   # a flash is dropped, never joined into two lines
        self.assertTrue(all(out[i][1] <= out[i + 1][0] for i in range(len(out) - 1)))

    def test_short_gaps_between_cues_are_closed(self):
        out = render.finalize_active([(0.0, 1.0, "A"), (1.1, 2.0, "B"), (3.0, 4.0, "C")])
        self.assertEqual(out[0][1], 1.1)    # a 0.1s blink at a cut is closed
        self.assertEqual(out[1][1], 2.0)    # a real pause (1s) keeps the screen clear

    def test_hook_title_shrinks_to_fit_long_lines(self):
        f = render.hook_behind_text("[0:v]", "[hb]", ["MY VIDEOS NOW EDIT THEMSELVES"], 3.0, 1920, width=1080)
        size = int(f.split("fontsize=")[1].split(":")[0])
        self.assertLessEqual(size * 0.62 * len("MY VIDEOS NOW EDIT THEMSELVES"), 1080 * 0.9)

    def test_one_event_per_word_with_the_spoken_word_marked(self):
        words = [{"text": "the", "start": 0.0, "end": 0.2}, {"text": "waiter", "start": 0.2, "end": 0.6}]
        ev = render.active_word_events(words, seg_start=0.0, seg_offset=10.0, seg_end=1.0)
        self.assertEqual(len(ev), 2)
        self.assertAlmostEqual(ev[1][0], 10.2)
        self.assertIn("WAITER", ev[1][2])
        self.assertIn(r"\3c", ev[1][2])                 # the active word carries the teal box
        self.assertEqual(ev[1][2].count(r"\3c"), 1)     # and only that one


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class WhipRenderTests(unittest.TestCase):
    def test_whip_composite_renders_full_length(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            base = d / "base.mp4"
            ff("-f", "lavfi", "-i", "testsrc2=s=160x288:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(base))
            ov = d / "ov.mp4"
            ff("-f", "lavfi", "-i", "color=white:s=160x288:r=30:d=1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(ov))
            out = d / "out.mp4"
            render.build_final_composite(base, [{"file": str(ov), "start_in_output": 1.0, "duration": 1.5, "exit": "whip"}],
                                         None, out, d)
            self.assertAlmostEqual(dur(out, "v:0"), 4.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
