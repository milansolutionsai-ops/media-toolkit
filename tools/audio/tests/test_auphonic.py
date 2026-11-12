import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auphonic  # noqa: E402


def tone(path: Path, secs: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={secs}", str(path)], check=True)


def dur(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout)


class Defaults(unittest.TestCase):
    def test_default_chain_is_round9_winner(self):
        f = auphonic.fields("x")   # dynamic denoise 12 dB, full reverb removal, leveler 80 (Milan, round 9)
        self.assertEqual((f["denoisemethod"], f["denoiseamount"], f["deverbamount"], f["levelerstrength"]),
                         ("dynamic", "12", "0", "80"))


class Trim(unittest.TestCase):
    def test_trims_free_plan_jingle_to_source_length(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "src.wav"), Path(d, "out.wav")
            tone(src, 2.0)
            tone(out, 5.0)          # processed file with a jingle appended
            auphonic.trim_to(src, out)
            self.assertAlmostEqual(dur(out), 2.0, delta=0.05)

    def test_leaves_same_length_output_alone(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "src.wav"), Path(d, "out.wav")
            tone(src, 2.0)
            tone(out, 2.0)
            auphonic.trim_to(src, out)
            self.assertAlmostEqual(dur(out), 2.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
