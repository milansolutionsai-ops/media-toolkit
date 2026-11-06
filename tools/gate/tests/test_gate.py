"""Quality gate: pacing, flash frames, loudness."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gate  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def shots_clip(out: Path, lengths, audio_gain_db=None, audio=True):
    """Solid-colour shots with hard cuts; optional sine audio, loudness-normalised to -14 or raised by gain."""
    colors = ["red", "blue", "green", "yellow", "white", "purple"]
    inputs, chain = [], ""
    for i, sec in enumerate(lengths):
        inputs += ["-f", "lavfi", "-i", f"color=c={colors[i % len(colors)]}:s=320x568:r=30:d={sec}"]
        chain += f"[{i}:v]"
    total = sum(lengths)
    graph = f"{chain}concat=n={len(lengths)}:v=1:a=0[v]"
    cmd = [*inputs]
    maps = ["-map", "[v]"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={total}"]
        a = len(lengths)
        af = f"loudnorm=I=-14:TP=-2:LRA=7" if audio_gain_db is None else f"volume={audio_gain_db}dB"
        graph += f";[{a}:a]{af},aresample=48000[a]"
        maps += ["-map", "[a]"]
    ff(*cmd, "-filter_complex", graph, *maps, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
       *(["-c:a", "aac", "-b:a", "192k"] if audio else []), "-t", str(total), str(out))
    return out


class GateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clean_clip_passes(self):
        r = gate.measure(shots_clip(self.d / "clean.mp4", [2, 2]))
        self.assertTrue(r["ok"], r["problems"])
        self.assertAlmostEqual(r["loudness_lufs"], -14, delta=1)

    def test_flash_frame_detected(self):
        out = self.d / "flash.mp4"
        ff("-f", "lavfi", "-i", "nullsrc=s=320x568:r=30,geq=lum='if(eq(N\,30)\,235\,90)':cb=128:cr=128",
           "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out))
        r = gate.measure(out)
        self.assertEqual(r["flash_frames"], [30])
        self.assertFalse(r["ok"])
        self.assertTrue(any("flash" in p.lower() for p in r["problems"]))

    def test_hot_audio_flagged(self):
        r = gate.measure(shots_clip(self.d / "hot.mp4", [2, 2], audio_gain_db=18))  # lavfi sine is -18 dBFS by default
        self.assertGreater(r["true_peak_dbtp"], -1)
        self.assertTrue(any("true peak" in p.lower() for p in r["problems"]))

    def test_no_audio_reports_not_crash(self):
        r = gate.measure(shots_clip(self.d / "mute.mp4", [2, 2], audio=False))
        self.assertFalse(r["has_audio"])
        self.assertIsNone(r["loudness_lufs"])
        self.assertTrue(any("no audio" in n.lower() for n in r["notes"]))

    def test_unmeasurable_audio_is_not_a_crash(self):
        import unittest.mock as um
        orig = gate._ff

        def fake(args):
            r = orig(args)
            if "ebur128=peak=true" in " ".join(args):
                r.stderr = b"no summary here"
            return r

        with um.patch.object(gate, "_ff", side_effect=fake):
            r = gate.measure(shots_clip(self.d / "odd.mp4", [2, 2]))
        self.assertIsNone(r["loudness_lufs"])
        self.assertTrue(any("loudness" in n.lower() for n in r["notes"]))

    def test_shot_lengths(self):
        r = gate.measure(shots_clip(self.d / "shots.mp4", [2, 1.5, 1.5]))
        self.assertEqual(len(r["shots"]), 3)
        for got, want in zip(r["shots"], [2.0, 1.5, 1.5]):
            self.assertAlmostEqual(got, want, delta=0.07)

    def test_sheets_sweep_and_edges(self):
        clip = shots_clip(self.d / "sheets.mp4", [2, 2, 2])
        out = self.d / "sheets"
        r = gate.sheets(clip, out, events=[1.0], sweep_fps=3)
        # 6s at 3 fps = 18 frames = one 6x3 sweep sheet; edges: 2 cuts + 1 event
        self.assertEqual(len(r["sweep"]), 1)
        self.assertEqual(len(r["edges"]), 3)
        for p in r["sweep"] + [e["sheet"] for e in r["edges"]]:
            self.assertTrue(Path(p).exists(), p)
        self.assertEqual(sorted(round(e["t"]) for e in r["edges"]), [1, 2, 4])

    def test_sheets_merge_close_edges(self):
        clip = shots_clip(self.d / "close.mp4", [2, 2])
        r = gate.sheets(clip, self.d / "close", events=[2.05], sweep_fps=1)
        self.assertEqual(len(r["edges"]), 1)  # an event 2 frames from a cut shares its sheet

    def test_ref_range_flags_too_fast(self):
        r = gate.measure(shots_clip(self.d / "fast.mp4", [0.5, 0.5, 0.5, 0.5]), ref_shot_range=(1.5, 3.0))
        self.assertTrue(any("faster" in p for p in r["problems"]))


if __name__ == "__main__":
    unittest.main()
