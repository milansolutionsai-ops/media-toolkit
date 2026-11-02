import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HELPERS = Path(__file__).parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))


def load(name):
    spec = importlib.util.spec_from_file_location(f"video_use_{name}", HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


transcribe = load("transcribe")
pack = load("pack_transcripts")


class WhisperToScribeTests(unittest.TestCase):
    def test_words_get_scribe_shape_and_gaps_become_spacing(self):
        out = transcribe.whisper_to_scribe(
            {"language": "en", "text": " Hi there. Next ",
             "words": [{"word": " Hi", "start": 0.0, "end": 0.3},
                       {"word": "there.", "start": 0.3, "end": 0.7},
                       {"word": " Next", "start": 1.6, "end": 1.9}]},
            source="groq/whisper-large-v3-turbo",
        )
        types = [w["type"] for w in out["words"]]
        self.assertEqual(types, ["word", "word", "spacing", "word"])
        self.assertEqual(out["words"][0]["text"], "Hi")
        self.assertEqual(out["words"][2]["start"], 0.7)
        self.assertEqual(out["words"][2]["end"], 1.6)
        self.assertTrue(all(w["speaker_id"] == "speaker_0" for w in out["words"]))
        self.assertEqual(out["language_code"], "en")
        self.assertEqual(out["source"], "groq/whisper-large-v3-turbo")

    def test_contiguous_words_produce_no_zero_length_spacing(self):
        out = transcribe.whisper_to_scribe(
            {"words": [{"word": "a", "start": 0.0, "end": 0.2},
                       {"word": "b", "start": 0.2, "end": 0.4}]},
            source="x",
        )
        self.assertEqual([w["type"] for w in out["words"]], ["word", "word"])

    def test_converted_output_splits_into_phrases_on_long_gap(self):
        out = transcribe.whisper_to_scribe(
            {"words": [{"word": "one", "start": 0.0, "end": 0.3},
                       {"word": "two", "start": 0.3, "end": 0.6},
                       {"word": "three", "start": 2.0, "end": 2.4}]},
            source="x",
        )
        phrases = pack.group_into_phrases(out["words"], silence_threshold=0.5)
        self.assertEqual([p["text"] for p in phrases], ["one two", "three"])


class PickBackendTests(unittest.TestCase):
    def env(self, values):
        return patch.object(transcribe, "load_env_value", side_effect=lambda n: values.get(n, ""))

    def test_prefers_groq_when_key_present(self):
        with self.env({"GROQ_API_KEY": "g", "ELEVENLABS_API_KEY": "e"}):
            self.assertEqual(transcribe.pick_backend(), ("groq", "g"))

    def test_falls_back_to_elevenlabs_then_local(self):
        with self.env({"ELEVENLABS_API_KEY": "e"}):
            self.assertEqual(transcribe.pick_backend(), ("elevenlabs", "e"))
        with self.env({}):
            self.assertEqual(transcribe.pick_backend(), ("local", ""))

    def test_explicit_local_ignores_keys(self):
        with self.env({"GROQ_API_KEY": "g"}):
            self.assertEqual(transcribe.pick_backend("local"), ("local", ""))

    def test_explicit_groq_without_key_exits_with_message(self):
        with self.env({}):
            with self.assertRaises(SystemExit) as ctx:
                transcribe.pick_backend("groq")
            self.assertIn("GROQ_API_KEY", str(ctx.exception))


class CallGroqTests(unittest.TestCase):
    def test_oversized_audio_fails_before_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.flac"
            with open(big, "wb") as f:
                f.truncate(26 * 1024 * 1024)
            with patch.object(transcribe.requests, "post") as post:
                with self.assertRaises(RuntimeError) as ctx:
                    transcribe.call_groq(big, "key")
                post.assert_not_called()
            self.assertIn("--backend local", str(ctx.exception))

    def test_posts_word_timestamps_and_returns_scribe_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "a.flac"
            audio.write_bytes(b"x")
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"language": "en", "text": "hi",
                                      "words": [{"word": "hi", "start": 0.0, "end": 0.2}]}
            with patch.object(transcribe.requests, "post", return_value=resp) as post:
                out = transcribe.call_groq(audio, "key", language="en")
            data = dict(post.call_args.kwargs["data"])
            fields = [k for k, _ in post.call_args.kwargs["data"]]
            self.assertEqual(data["model"], "whisper-large-v3-turbo")
            self.assertEqual(data["response_format"], "verbose_json")
            self.assertIn("timestamp_granularities[]", fields)
            self.assertEqual(data["language"], "en")
            self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer key")
            self.assertEqual(out["words"][0]["text"], "hi")


class LocalWhisperTests(unittest.TestCase):
    def test_passes_decoded_samples_not_a_path(self):
        # faster-whisper's own decoder (PyAV) breaks on av>=19, so the wav is
        # decoded here and handed over as float32 samples.
        import array
        import wave
        import numpy as np

        seen = {}

        class FakeModel:
            def __init__(self, *a, **k):
                pass

            def transcribe(self, audio, **kwargs):
                seen["audio"] = audio
                word = MagicMock(word=" hi", start=0.0, end=0.2)
                seg = MagicMock(words=[word])
                return iter([seg]), MagicMock(language="en")

        fake = MagicMock(WhisperModel=FakeModel)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(array.array("h", [0, 16384, -16384, 0]).tobytes())
            with patch.dict(sys.modules, {"faster_whisper": fake}):
                out = transcribe.call_local_whisper(wav)
        self.assertIsInstance(seen["audio"], np.ndarray)
        self.assertEqual(seen["audio"].dtype, np.float32)
        self.assertAlmostEqual(float(seen["audio"][1]), 0.5, places=3)
        self.assertEqual(out["words"][0]["text"], "hi")

    def test_missing_faster_whisper_gives_install_hint(self):
        with patch.dict(sys.modules, {"faster_whisper": None}):
            with self.assertRaises(RuntimeError) as ctx:
                transcribe.call_local_whisper(Path("x.wav"))
        self.assertIn("uv sync --python 3.12 --extra local", str(ctx.exception))


class MainErrorTests(unittest.TestCase):
    def test_runtime_error_exits_with_one_line_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"x")
            argv = ["transcribe.py", str(video), "--backend", "local"]
            boom = RuntimeError("local backend needs faster-whisper: run `uv sync`")
            with patch.object(sys, "argv", argv), \
                 patch.object(transcribe, "transcribe_one", side_effect=boom):
                with self.assertRaises(SystemExit) as ctx:
                    transcribe.main()
        self.assertIn("needs faster-whisper", str(ctx.exception.code))


class UploadAudioTests(unittest.TestCase):
    def test_groq_upload_is_compressed_opus(self):
        # Lossless FLAC is ~1 MB/min, so a 30-min session would blow Groq's 25 MB
        # free limit. Opus at 32 kbps speech is ~0.24 MB/min (~100 min).
        with patch.object(transcribe.subprocess, "run") as run:
            transcribe.to_upload_audio(Path("in.wav"), Path("out.ogg"))
        cmd = run.call_args.args[0]
        self.assertIn("libopus", cmd)
        self.assertIn("32k", cmd)
        self.assertEqual(cmd[-1], "out.ogg")

    def test_groq_sends_ogg_mime_for_ogg_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "a.ogg"
            audio.write_bytes(b"x")
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"words": []}
            with patch.object(transcribe.requests, "post", return_value=resp) as post:
                transcribe.call_groq(audio, "key")
        self.assertEqual(post.call_args.kwargs["files"]["file"][2], "audio/ogg")


class FinalizePayloadTests(unittest.TestCase):
    PAYLOAD = {"words": [{"type": "word", "text": "video", "start": 13.96, "end": 15.72,
                          "speaker_id": "speaker_0"}]}

    def test_whisper_backends_are_aligned(self):
        for backend in ("groq", "local"):
            with patch.object(transcribe.align_words, "detect_silences",
                              return_value=([(14.44, 15.33)], 20.0)):
                out = transcribe.finalize_payload(self.PAYLOAD, backend, Path("a.wav"))
            self.assertEqual(out["alignment"]["method"], "silence-snap")
            self.assertEqual(out["words"][0]["start"], 15.33)

    def test_failed_silence_detection_keeps_the_transcript(self):
        import subprocess
        err = subprocess.CalledProcessError(1, ["ffprobe"])
        with patch.object(transcribe.align_words, "detect_silences", side_effect=err):
            out = transcribe.finalize_payload(self.PAYLOAD, "groq", Path("a.wav"))
        self.assertIs(out, self.PAYLOAD)

    def test_scribe_payload_untouched(self):
        with patch.object(transcribe.align_words, "detect_silences") as det:
            out = transcribe.finalize_payload(self.PAYLOAD, "elevenlabs", Path("a.wav"))
        det.assert_not_called()
        self.assertIs(out, self.PAYLOAD)


if __name__ == "__main__":
    unittest.main()
