"""Cut transitions (whip, zoom-through, flash), x-ray reveal, picture-in-picture bubble, background swap."""
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HELPERS = Path(__file__).parents[1] / "helpers"


def load(name):
    spec = importlib.util.spec_from_file_location(f"video_use_{name}_fx", HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


render = load("render")


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def vdur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def mean_luma(p, t):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1", "-vf",
                          "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"],
                         capture_output=True, text=True)
    return float(out.stderr.split("YAVG=")[1].split()[0])


class FilterTextTests(unittest.TestCase):
    def test_flash_peaks_at_the_cut(self):
        f = ";".join(render.transition_filters("[v]", "[o]", "flash", 2.5, 0, 1080, 1920))
        self.assertIn("eq=brightness=", f)
        self.assertIn("t-2.500", f)

    def test_whip_is_a_horizontal_blur_slide_around_the_cut(self):
        f = ";".join(render.transition_filters("[v]", "[o]", "whip", 2.5, 0, 1080, 1920))
        self.assertIn("avgblur=sizeX=", f)
        self.assertIn("trim=start=2.350:end=2.650", f)
        self.assertIn("between(t,2.350,2.650)", f)

    def test_zoom_through_uses_zoompan_on_the_cut_window(self):
        f = ";".join(render.transition_filters("[v]", "[o]", "zoom", 2.5, 0, 1080, 1920))
        self.assertIn("zoompan=", f)
        self.assertIn("s=1080x1920", f)

    def test_unknown_transition_is_an_error(self):
        with self.assertRaises(ValueError):
            render.transition_filters("[v]", "[o]", "spin", 2.5, 0, 1080, 1920)

    def test_leak_and_wipe_sit_on_the_cut(self):
        leak = ";".join(render.transition_filters("[v]", "[o]", "leak", 2.5, 0, 1080, 1920))
        wipe = ";".join(render.transition_filters("[v]", "[o]", "wipe", 2.5, 0, 1080, 1920))
        self.assertIn("between(t,2.280,2.720)", leak)
        self.assertIn("overlay=x=", wipe)          # drawbox can't move over time; an overlay can
        self.assertIn("2.500", wipe)

    def test_box_is_a_rounded_rectangle(self):
        f = ";".join(render.bubble_layer("[v]", "[m]", "[b]", {"start": 1, "duration": 2, "x": 0, "y": 0,
                                                              "w": 600, "h": 400, "radius": 40,
                                                              "crop": [100, 100, 600, 400]}, 0))
        self.assertIn("crop=600:400:100:100", f)
        self.assertIn("40", f)

    def test_background_zoom_follows_punch_ins(self):
        z = render.bg_zoom_expr([(1.0, 2.0, 1.18)])
        self.assertIn("between(it,1.000,2.000)", z)
        self.assertIn("1.18", z)
        self.assertEqual(render.bg_zoom_expr([]), "1")

    def test_xray_scans_down_from_its_start(self):
        f = ";".join(render.xray_filters("[v]", "[o]", start=3.0, duration=1.2, n=0))
        self.assertIn("negate", f)
        self.assertIn("geq=", f)
        self.assertIn("between(t,3.000,4.200)", f)

    def test_mask_cache_key_follows_the_cut_not_the_grade(self):
        a = render.mask_key([{"source": "A", "start": 1, "end": 2}], None, 3.0)
        b = render.mask_key([{"source": "A", "start": 1, "end": 2, "beat": "x"}], None, 3.0)
        c = render.mask_key([{"source": "A", "start": 1, "end": 2.5}], None, 3.0)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(render.mask_key([{"source": "A", "start": 1, "end": 2}], None, 3.0, "rvm"), a + "_rvm")


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.d = Path(cls.tmp.name)
        cls.base = d / "base.mp4"
        ff("-f", "lavfi", "-i", "color=c=0x404040:s=160x288:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.base))
        cls.mask = d / "mask.webm"   # opaque left half = "the person"
        ff("-f", "lavfi", "-i", "color=c=white:s=160x288:r=30:d=4.3,format=yuva420p,"
           "geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='255*lt(X,W/2)'",
           "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", str(cls.mask))
        cls.bg = d / "bg.png"
        ff("-f", "lavfi", "-i", "color=c=0x00B4B4:s=320x320", "-frames:v", "1", str(cls.bg))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_transitions_and_effects_keep_the_length(self):
        out = self.d / "fx.mp4"
        render.build_final_composite(
            self.base, [], None, out, self.d,
            transitions=[{"type": "whip", "t": 1.0}, {"type": "zoom", "t": 2.0}, {"type": "flash", "t": 3.0}],
            effects=[{"type": "xray", "start": 0.5, "duration": 0.8},
                     {"type": "bubble", "start": 2.2, "duration": 1.0, "x": 10, "y": 150, "size": 80,
                      "crop": [40, 60, 80]}])
        self.assertAlmostEqual(vdur(out), 4.0, delta=0.1)
        self.assertGreater(mean_luma(out, 3.0), mean_luma(out, 3.6) + 40)   # the flash is bright at its cut

    def test_sfx_are_mixed_at_their_times(self):
        click = self.d / "click.wav"
        ff("-f", "lavfi", "-i", "sine=f=2000:d=0.1", "-af", "volume=10dB", str(click))
        out = self.d / "sfx.mp4"
        render.build_final_composite(self.base, [], None, out, self.d, sfx=[{"file": str(click), "t": 2.0}])
        self.assertAlmostEqual(vdur(out), 4.0, delta=0.1)
        fast = self.d / "sfx_fast.mp4"   # with a speed-up the mix is retimed inside the graph
        render.build_final_composite(self.base, [], None, fast, self.d, speed=1.25, sfx=[{"file": str(click), "t": 2.0}])
        self.assertAlmostEqual(vdur(fast), 3.2, delta=0.1)

    def test_behind_overlay_goes_under_the_person(self):
        card = self.d / "card.mp4"
        ff("-f", "lavfi", "-i", "color=c=red:s=160x288:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(card))
        out = self.d / "behind.mp4"
        render.build_final_composite(self.base, [{"file": str(card), "start_in_output": 1.0, "duration": 2.0,
                                                  "layer": "behind"}], None, out, self.d,
                                     background={"file": str(self.bg), "mask": str(self.mask)})
        px = subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-vf",
                             "format=rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
        left, right = px[(144 * 160 + 20) * 3:(144 * 160 + 20) * 3 + 3], px[(144 * 160 + 140) * 3:(144 * 160 + 140) * 3 + 3]
        self.assertLess(left[0], 150)        # the person (grey) stays in front on the left
        self.assertGreater(right[0], 150)    # the red card shows behind, on the right

    def test_background_swap_puts_the_person_over_the_backdrop(self):
        out = self.d / "bg.mp4"
        render.build_final_composite(self.base, [], None, out, self.d,
                                     background={"file": str(self.bg), "mask": str(self.mask)})
        self.assertAlmostEqual(vdur(out), 4.0, delta=0.1)
        right = subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-vf",
                                "crop=40:40:110:120,format=rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
        self.assertGreater(right[1], right[0] + 80)    # backdrop teal on the right: green well above red


if __name__ == "__main__":
    unittest.main()
