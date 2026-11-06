# Media Toolkit

A local, near-zero-cost media production stack: edit talking-head video, build motion graphics,
generate voice, clean and mix audio, and let the agent listen to the result. Built by Milan Veljkovikj for his own
content first, usable by any project.

**Agent entry point.** Point a session here: "Read `<toolkit>/TOOLKIT.md`." Read this file, then only the tool
README you need, then the project's style guide. Setup on a new machine: `SETUP.md`.

**Projects live OUTSIDE this repo**, one folder up: `<workspace>/<project>/` next to `<workspace>/media-toolkit/`.
The repo is the engine only; nothing project-specific is ever committed here.

## Layout

| Path | What |
|---|---|
| `tools/editor/` | **Video editor** (fork of [browser-use/video-use](https://github.com/browser-use/video-use), MIT). Transcribe, find mistakes, cut, captions, punch-ins, speed, overlays, render. Notes in `tools/editor/TOOLKIT_NOTES.md`; also usable as the `video-use` Claude skill (link `~/.claude/skills/video-use` to it). |
| `tools/motion/` | **Motion graphics** (HyperFrames: HTML + GSAP → MP4). Templates, `snap.mjs` storyboard stills, reference library (`REFERENCES.md`: 703 Claude-made videos with prompts, 15 + 43 film styles). |
| `tools/audio/` | **Sound**: beat grid + build-ups, music splicer, SFX generator, real SFX fetch (Openverse), **earshot** (the agent hears: rank, timeline, critique), licensed music, mixing recipes. Voice cleanup lives in the editor. |
| `tools/voice/` | **Voice generation**: Kokoro (free, local), Gemini 3.8 Flash TTS (free tier), VoiceStudio (local cloning, parked), ElevenLabs (paid). |
| `tools/paid/` | **Paid routes, ready to run**: Kie (Kling, Seedream, Suno), Higgsfield API, Gemini Omni video, ElevenLabs SFX, Blender GPU render. Dry run until `--go`. Only when `docs/UPGRADES.md` says the trigger is met. |
| `tools/review/` | **Review app** (local Frame.io): mark exact frames/sound in a render, notes reach Claude through a hook, before/after fix check. `review.py register/claim/show/list`. Setup: `install.py`. |
| `tools/library/` | **Technique library**: references and techniques (what, recipe, status, brand verdicts); data in the private workspace `library/`. |
| `tools/gate/` | **Quality gate**: flash frames, loudness, true peak, clicks at cuts, pacing vs references. Run before anyone watches a render. |
| `tools/recording/` | **Recording**: OBS profile backup, 9:16 framing guide. |
| `../<project>/` | One folder per project, outside the repo. Brand rules live there (`STYLE_GUIDE.md`), never in `tools/`. |
| `docs/STYLE_ONBOARDING.md` | **Style onboarding**: references → technique library → style rounds (Keep / Maybe / Drop) → locked `STYLE_GUIDE.md`, with the quality gate. |
| `docs/` | `knowledge/ad-craft.md` (ad research, script, music, SFX and edit techniques by pipeline stage), `UPGRADES.md` (every paid / GPU route we found, for the day the free one isn't enough), `windows-setup.md`. |

A project folder usually holds `STYLE_GUIDE.md`, `SCRIPTS/`, `RECORDINGS/`, `READY TO POST/` and `_work/` (edit
dirs, EDLs, renders).

## The pipeline (talking head)

1. Script (project `SCRIPTS/`) → record (`RECORDINGS/`, see `tools/recording/`).
2. `tools/editor`: `transcribe.py` → `pack_transcripts.py` → cut list (EDL) → `render.py`.
   Restarts: run `find_mistakes.py` for cut candidates; the newer take always wins; re-transcribe `suspect` stretches (Whisper hides duplicates).
3. Motion moments: `tools/motion` template → storyboard gate → render → EDL `overlays`.
4. Deliver to the project's ready folder with caption text.

## The pipeline (motion-only video)

Beat sheet → storyboard stills (`tools/motion/snap.mjs`) → Milan's marks → voice (`tools/voice`)
→ word timings (`npx hyperframes transcribe vo.wav --engine parakeet`) → cue times → music + SFX mix
(`tools/audio`) → listen (earshot) → render.

## Universal rules (every project)

- **Storyboard gate** for every motion piece: beat sheet → stills, one per beat → approval → full render.
- **Voice is the master clock.** Every on-screen element lands on its spoken word; music sections change on
  scene changes. Change voice, visuals or music → re-sync the other two before rendering.
- **Music-led pieces (ads, promos) pick the music EARLY** (Milan, 2026-10-30): script → pick track (mood, BPM, drop)
  → beat grid (`tools/audio/beats.py`) → scene cuts on beats → voice fitted to the grid → graphics on words.
  Narration-led explainers keep "voice is the master clock". Ads: map the energy curve per section first (`docs/knowledge/ad-craft.md`).
- **Banned looks** (they read as "AI video"): centered title on a gradient, everything fading in, corner labels,
  frame borders, generic particle bursts. Something new on screen every 2-4s. Motion uses springs (`tools/motion/lib/motion.js`), not plain ease curves.
- **Self-critique before Milan sees it** (every motion piece, stills and renders): score 1-10 on hook in the first
  2s, readability at phone size, motion quality, variety, brand accuracy, sound sync. Fix the 3 worst, repeat until
  all are 8+, then show. Renders: `tools/motion/review_sheets.py` (contact, phone-size, strips around fast moments).
- **Reference first** when Milan likes a look (or search `tools/motion/REFERENCES.md` for candidates): `review_sheets.py <ref.mp4> --frames` → write the reference's
  palette, type, shot lengths, transitions, how text enters/exits into the project's style notes; take the grammar,
  never the content. Then the shot list, then his OK, then code.
- New motion pieces run at high effort (xhigh); medium is fine for fixes and re-renders.
- **Never bare `hyperframes snapshot`**: it bills the Gemini API key and wipes the stills folder. Use `snap.mjs`.
- **Measure, don't assume**: loudness (`ebur128`), true peak, frame checks at every cut before showing anything. Listen with earshot (`timeline` / `critique`) before Milan hears a mix.
- **Zero subscriptions.** Local or free first; a paid API only when the quality gap is real and the cost is cents.
- **Secrets**: keys live in `.env.local` at the toolkit root (gitignored). Never print a value.
- Brand values (fonts, colours, caption size, pace) come from the PROJECT's style guide, never hardcoded in tools.

## Upgrading a tool

Every tool is replaceable. To upgrade or swap one:
1. Read its README: it lists the version, how it's installed, and what depends on it.
2. Change it in place; for the editor, add a test first (`cd tools/editor && uv run python -m unittest discover -s tests`).
3. Re-run one real project end to end and compare against the previous output before calling it done.
4. Update the tool README (version, date, why) and commit. Big swaps get a note in `docs/`.
5. Considering a paid route instead? Check `docs/UPGRADES.md` first: it records what was evaluated and why.

## Machine

Windows 11, AMD Radeon 780M (no NVIDIA: GPU AI tools run on CPU), Node 22, Python via uv (3.12),
ffmpeg 8 (with rubberband), bun 1.3. Everything runs on CPU.
