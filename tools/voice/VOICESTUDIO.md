# VoiceStudio (debpalash/VoiceStudio)

Local voice cloning, voice design, TTS, dubbing, transcription. AGPL-3.0 (fine for own and internal use;
hosting it as a service for clients triggers AGPL source obligations). Model licences are separate per engine.

- Installed 2026-10-23: `tools/voice/VoiceStudio`, v0.5.7-beta.1 (commit 4646713), CPU PyTorch
  (no NVIDIA on this laptop). Installed from source, NOT the `irm | iex` one-liner.
  Re-install / upgrade: `git pull` then `OMNIVOICE_TORCH_VARIANT=cpu node scripts/setup-api.mjs` (uv sync, ~5 GB).
- Start the backend (no desktop app needed):
  ```
  cd tools/voice/VoiceStudio
  OMNIVOICE_DEVICE=cpu OMNIVOICE_MCP_OUTPUT_MODE=files OMNIVOICE_MCP_BASE_PATH="<toolkit>/tools/voice/test" \
    uv run --no-sync uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900
  ```
  Ready when `curl http://127.0.0.1:3900/health` returns `"status":"ok"` (~1-2 min on first start).
- Clone + speak in one call (REST):
  `curl -F "text=..." -F "language=English" -F "ref_audio=@ref.wav" -F "ref_text=<what the ref says>" http://127.0.0.1:3900/generate -o out.wav`
  Saved voices: `POST /profiles` (name, ref_audio, ref_text), then `/generate` with `profile_id`.
  Other engines: `GET /engines/tts`; pass `engine=` to `/generate`.
- MCP for agents: `http://127.0.0.1:3900/mcp/` (trailing slash), tools `generate_speech`, `clone_voice`,
  `design_voice`, `transcribe`, `list_voices`. Files mode writes only inside `OMNIVOICE_MCP_BASE_PATH`.
- Reference audio: 10-15s of clean speech + its exact transcript. Best source: a JBL-mic take, cleaned
  (`projects/.../_work/edits/<batch>/clean/*.mkv`).

## Licences: which engine is allowed (checked 2026-10-23, `docs/licensing/model-license-data.json`)

| Engine | Licence | Use |
|---|---|---|
| OmniVoice (default) | CC-BY-NC + Higgs Audio 2 + Llama 3: **non-commercial** | not for brand or client work; needs an in-app licence acceptance (Milan's call) |
| VoxCPM2 (openbmb) | Apache-2.0 | allowed; reviews say it clones better than OmniVoice |
| CosyVoice3 0.5B | Apache-2.0 | allowed |
| GPT-SoVITS | MIT | allowed |
| Kokoro | Apache-2.0 | allowed (no cloning) |

## Test 2026-10-23

- Install: venv 4.3 GB, backend healthy on CPU (`torch 2.8.0+cpu`), startup ~1 min.
- First `/generate` (OmniVoice, default) refused: `model_licence_required`. Nothing accepted.
- VoxCPM2 (Apache-2.0) installed: `uv pip install --python .venv/Scripts/python.exe "voxcpm>=2.0.3"`, model 4.96 GB
  from Hugging Face on the first call (first call 732s incl. download). Call `/generate` with `engine=voxcpm2`.
- Speed on this CPU: 14.9s English line in 156s, 9.7s Spanish line in 99s, so ~10x slower than real time
  (a 60s voiceover ≈ 10 min). Output 48 kHz mono WAV.
- Intelligibility: Whisper read both clones back word for word (only "Claude" → "cloud", a Whisper habit).
- Listening files: `tools/voice/test/listen/` (real voice, English clone, Spanish clone). Verdict: Milan's ear.
- ElevenLabs account is the FREE tier (checked via API 2026-10-23): 10k chars/month, no voice cloning,
  no commercial licence. Fine for drafts with stock voices, not for published work.
  Reference clip ready: `tools/voice/test/milan_ref.wav` (11s, video 1, phone mic, cleaned).

## Status 2026-10-30: cloning parked
Milan: "discard the AI cloned voices for now" (clone had his features but sounded robotic on an 11s phone sample).
Backend stopped. Install (~9.3 GB incl. VoxCPM2 model in the HF cache) kept until Milan decides to delete.
