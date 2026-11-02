# Voice generation

| Engine | Cost | Quality | Use for |
|---|---|---|---|
| **Kokoro-82M** (`kokoro/.venv`, via `npx hyperframes tts`) | free, local, fast on CPU | good, clearly synthetic | drafts, timing passes, internal pieces |
| **VoiceStudio** (`VoiceStudio/`, OmniVoice + other engines) | free, local, slow on this CPU | mixed per reviews; cloning + voice design | cloning Milan's voice, Spanish dubs (on test) |
| **Gemini 3.8 Flash TTS** (`gemini_vo.py`, key `GEMINI_TTS_API_KEY` in root `.env.local`, free-tier project) | free tier (rate-limited: run scenes one by one); paid ~$0.013/min | on test (2026-11-02) | 30 voices, style by plain-English direction, Spanish, inline `<short pause>`/`<laugh>` tags |
| **ElevenLabs** (`eleven_vo.py`, key `ELEVENLABS_API_KEY` in root `.env.local`) | paid per character | best | final voiceover when it matters |

- Kokoro: `HYPERFRAMES_PYTHON="<toolkit>/tools/voice/kokoro/.venv/Scripts/python.exe" npx hyperframes tts script.txt -v am_fenrir -s 1.08 -o vo.wav`.
  Rebuild: `uv venv --python 3.12 tools/voice/kokoro/.venv` then `uv pip install --python tools/voice/kokoro/.venv/Scripts/python.exe kokoro-onnx soundfile`.
- ElevenLabs: `python tools/voice/eleven_vo.py <project_dir> <voice_name> <voice_id> [model]` (reads `VO_SCRIPT.md`, one request per scene, word alignment saved).
- Gemini: `python tools/voice/gemini_vo.py <project_dir> <voice> "style"` (reads `VO_SCRIPT.md`) or `--text "line" --out x.wav <voice> "style"`. Samples: `tools/voice/test/gemini/`. No alignment from the API: transcribe for timings.
- Word timings for any voice file: `npx hyperframes transcribe vo.wav --engine parakeet`.
- VoiceStudio: see `VOICESTUDIO.md`.
