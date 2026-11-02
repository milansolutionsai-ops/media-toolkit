# Windows notes (editor)

- The editor lives in `tools/editor`, forked from browser-use/video-use (local changes: Groq transcription, Windows fixes, the features in `TOOLKIT_NOTES.md`).
- Python: 3.12 via uv (`.venv` in `tools/editor`). Run helpers with `uv run python helpers/<name>.py` from there.
- Skill: junction `~/.claude/skills/video-use` → `tools/editor` (`mklink /J`). Claude Code picks up SKILL.md from there.
- Transcription: `--backend groq` (default when `GROQ_API_KEY` is in `tools/editor/.env`, free tier, 25 MB per file; audio is uploaded as 32 kbps opus, so takes up to ~100 min fit), `--backend local` (faster-whisper on CPU, free, slower), `--backend elevenlabs` (paid, unused).
- Keys never go in git: `tools/editor/.env` and the root `.env.local` are ignored.
- Pulling upstream improvements: compare with browser-use/video-use, port by hand, then `uv run python -m unittest discover -s tests`.
- Windows fixes carried on the branch: subtitles filter path escaping (`render.subtitles_filter_path`) and UTF-8 stdout in the helpers that print arrows (cp1252 consoles crashed on them).
