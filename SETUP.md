# Setup

Tested on Windows 11 (CPU only, no NVIDIA). macOS/Linux work with the obvious path changes (`.venv/bin/` instead of
`.venv/Scripts/`).

## 1. Workspace layout

```
<workspace>/
  media-toolkit/        this repo (the engine)
  my-channel/           a project: STYLE_GUIDE.md, SCRIPTS/, RECORDINGS/, READY TO POST/, _work/
  client-promo/         another project
```

Projects never go inside the repo. Point Claude Code at `media-toolkit/TOOLKIT.md` from any of them.

## 2. Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is fetched by uv), Node 22+, git.
- ffmpeg 8 with rubberband on PATH (Windows: `winget install Gyan.FFmpeg`).

## 3. Editor (`tools/editor`)

```bash
cd tools/editor && uv sync
uv run python -m unittest discover -s tests
```

- Voice cleanup model: download `sh.rnnn` from
  [GregorR/rnnoise-models](https://github.com/GregorR/rnnoise-models/tree/master/somnolent-hogwash-2018-09-01)
  into `tools/editor/models/` (not redistributed here).
- Transcription key (free): put `GROQ_API_KEY=...` in `tools/editor/.env`. No key → `--backend local` (faster-whisper, CPU).
- Use it as a Claude Code skill: link `~/.claude/skills/video-use` to `tools/editor`
  (Windows: `mklink /J "%USERPROFILE%\.claude\skills\video-use" "<path>\media-toolkit\tools\editor"`).

## 4. Motion graphics (`tools/motion`)

HyperFrames runs through npx, nothing to install: `npx hyperframes@0.8.157 --help`.
Optional reference library (gitignored, ~1-2 GB with videos):

```bash
cd tools/motion/references
git clone https://github.com/yihui-dev/awesome-opus5-5-videos
git clone https://github.com/athemeroy/awesome-claude-5-5-videos
git clone https://github.com/Vincentwei1021/mg-styles-15
git clone https://github.com/lemomo-ai/lemo-opuscar
git clone https://github.com/JohnHeibel/ClaudeAnimationBase
```

## 5. Voice (`tools/voice`)

- Kokoro (local): `uv venv --python 3.12 tools/voice/kokoro/.venv` then
  `uv pip install --python tools/voice/kokoro/.venv/Scripts/python.exe kokoro-onnx soundfile`.
- Gemini 3.8 Flash TTS (free tier): create a key in Google AI Studio on a project WITHOUT billing, add
  `GEMINI_TTS_API_KEY=...` to `.env.local` at the repo root.
- ElevenLabs (paid, optional): `ELEVENLABS_API_KEY=...` in the same `.env.local`.

## 6. Audio (`tools/audio`)

- Music: tracks are not redistributed. The example track is "Club No Copyright" by MiroMaxMusic on Pixabay
  (free licence); download it into `tools/audio/music/` or use your own.
- earshot (lets the agent hear; ~2.1 GB with models):

```bash
cd tools/audio && git clone --depth 1 https://github.com/Leonxlnx/earshot && cd earshot
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/Scripts/python.exe -e ".[mcp]"
.venv/Scripts/python.exe -m earshot doctor --fetch
```

- `.mcp.json` at the repo root registers earshot as an MCP server for sessions started in this folder.
- Openverse SFX need no key.

## 7. Recording (`tools/recording`)

OBS profile + scene collection backup and a 9:16 framing guide. Copy `obs/` into
`%APPDATA%/obs-studio/basic/profiles/` and `.../scenes/` with OBS closed, then set the recording path to your
project's `RECORDINGS/` folder.

## 8. Paid routes (optional)

Scripts in `tools/paid/` (see its README). Blender renders need Blender installed and ideally an NVIDIA GPU.

## Keys, summarised

| Key | File | Needed for |
|---|---|---|
| `GROQ_API_KEY` | `tools/editor/.env` | free cloud transcription (optional) |
| `GEMINI_TTS_API_KEY` | `.env.local` | Gemini voice (optional) |
| `ELEVENLABS_API_KEY` | `.env.local` | ElevenLabs voice and SFX (optional, paid) |
| `KIE_API_KEY` | `.env.local` | Kling, Seedream, Suno (optional, paid) |
| `HF_KEY` | `.env.local` | Higgsfield API, `id:secret` (optional, paid) |
| `GEMINI_VIDEO_API_KEY` | `.env.local` | Gemini Omni video, billing on (optional, paid) |

Both files are gitignored. Never commit a key.
