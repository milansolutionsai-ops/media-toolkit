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


def mean_db(path: Path, start: float, length: float) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(start), "-t", str(length), "-i", str(path),
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    return float(r.stderr.split("mean_volume:")[1].split("dB")[0])


class Defaults(unittest.TestCase):
    def test_default_chain_is_round9_winner(self):
        f = auphonic.fields("x")   # dynamic denoise 12 dB, full reverb removal, leveler 80 (Milan, round 9)
        self.assertEqual((f["denoisemethod"], f["denoiseamount"], f["deverbamount"], f["levelerstrength"]),
                         ("dynamic", "12", "0", "80"))


class Trim(unittest.TestCase):
    def test_trims_free_plan_jingle_from_the_start(self):
        # The free plan PREPENDS a spoken tag (2026-11-21: 6.4s before the speech). Cutting the end instead
        # shifts the voice late against the picture and loses the last line.
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "src.wav"), Path(d, "out.wav")
            tone(src, 2.0)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=3",
                            "-f", "lavfi", "-i", "sine=f=440:d=2", "-filter_complex", "[0][1]concat=n=2:v=0:a=1",
                            str(out)], check=True)          # 3s "jingle" (silence here), then the content
            auphonic.trim_to(src, out)
            self.assertAlmostEqual(dur(out), 2.0, delta=0.05)
            self.assertGreater(mean_db(out, 0.0, 0.5), -40)   # starts on the content, not on the jingle

    def test_leaves_same_length_output_alone(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "src.wav"), Path(d, "out.wav")
            tone(src, 2.0)
            tone(out, 2.0)
            auphonic.trim_to(src, out)
            self.assertAlmostEqual(dur(out), 2.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
