# Editor (video-use fork): toolkit notes

Upstream `browser-use/video-use`, branch `milan/groq-transcription`, never pushed upstream. Full usage: `SKILL.md`.

- Run: `cd tools/editor && uv run python helpers/<name>.py ...` (Python 3.12 via uv). Tests: `uv run python -m unittest discover -s tests`.
- Transcribe: `helpers/transcribe.py <video> --edit-dir <project>/_work/edits/<batch>` (Groq Whisper, free tier, key in env; local faster-whisper fallback). Words are snapped to real speech (`align_words.py`).
- Mistakes: `helpers/find_mistakes.py <edit>/transcripts/<name>.json --out-dir <edit>` → `<name>.cut-candidates.md` (stutters, retakes, false starts, phrases said twice; `suspect` = re-transcribe that stretch). Read each in context, then leave the approved cuts out of the EDL ranges. Adapted from herk-edit-kit (MIT).
- Render: `helpers/render.py <edl.json> -o <out.mp4> --build-subtitles`. EDL fields beyond upstream: `keywords` (teal word), `hook_title`, range `zoom`, `overlays[].fade_out`, top-level `speed` (pitch-kept), `audio_clean` (RNNoise + 25% dry, default on), `watermark` (faint text mid-frame), `captions: "sentence"` (one sentence per pill, top third), `reframe: 1.15` (alternate wide/tight per range), `captions: "active"` (spoken word on a teal box), overlay `"exit": "whip"` (whip-pan out of a graphic, the face settles in), `hook_behind: {"lines": [...], "seconds": 3, "color": "0x0E1214", "top": 0.17}` (title behind the head: person cutout via `hyperframes remove-background`, CPU, ~1 min for 3s; cached as `hook_cutout.webm`).
- Caption style (font, colours, sizes) lives in `helpers/ass_captions.py`: currently Milan's brand. A second brand = make it read from the project (open item).
- Known open items: true peak lands at -0.7 dBTP when `speed` is set; root cause of the old setpts overlay drift never isolated (tpad fix holds). Vault backlog has the rest.
- Worked example of a full edit script: `projects/milan-content/_work/edits/batch-1/build_edl_01.py`.
