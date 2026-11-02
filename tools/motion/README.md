# Motion graphics (HyperFrames)

HTML + GSAP compositions rendered to MP4 by HyperFrames (HeyGen, Apache-2.0) through headless Chrome + ffmpeg.
Claude plugin installed (user scope): load the `hyperframes` skill before writing compositions.

- New piece: copy a template into the project's `_work/`, `npm install`, edit `index.html`, then
  `npx hyperframes check` → stills → `npx hyperframes render . -o renders/x.mp4` (`--format mov` for alpha overlays).
- Always prefix HyperFrames commands with `GEMINI_API_KEY= GOOGLE_API_KEY=` (some commands call Gemini when a key is present).
- **Stills / storyboard:** `node tools/motion/snap.mjs <project> --at 3,12,21 [--first NN] [--describe "question"]`.
  Never bare `hyperframes snapshot` (bills the Gemini key, wipes the stills folder).

## Templates (`templates/`), all Milan's brand: IBM Plex, teal #00B4B4, slate #0E1214

| Template | What | Size |
|---|---|---|
| `step-flow-overlay` | 4 steps in a chip row on a panel, bottom of frame, over footage (alpha) | 1080x1920, 3.5s |
| `step-flow-cutaway` | Full-screen vertical step list, each step lands on a spoken word, dissolves out | 1080x1920, ~7.7s |
| `diagram-build` | Explainer diagram: title, boxes, wires and pill labels land one by one on their spoken words. Edit the NODES / WIRES / TAGS block at the top of the script | 1080x1920, 9s |
| `tool-label` | Tool logo pops in, the name slides out of it. Overlay (alpha, `--format mov`), on the word that names the tool | 1080x1920, 2.6s |
| `prompt-bar` | Dark rounded prompt bar, prompt types in, teal send button lights on send. Overlay | 1080x1920, 5s |
| `repo-card` | GitHub dark-theme repo card (owner/name, description, language, stars). Copy real numbers, never invent. Overlay | 1080x1920, 3.5s |
| `kinetic-steps-video` | Full motion video: word-slam hook, flash, numbered step cards, recap grid, payoff, name lockup. 120 BPM grid; timing constants at the top of the script | 1080x1920, 30s |

- **Springs:** `lib/motion.js` (copy into the project's `assets/`, load after GSAP). `ease: Motion.ease(0.45, "ui")`
  for boxes/icons, `"type"` for text (no overshoot), `"heavy"` for big type/logos. `Motion.track(t, keys)` for a value with several targets.
  `diagram-build` and `step-flow-cutaway` already use it; `kinetic-steps-video` (06, approved) still uses GSAP eases.
- **Review a render:** `python tools/motion/review_sheets.py out.mp4 --strips 3.0,9.5` → `review/contact.png`, `phone.png`, strips.
  Same script with `--frames` on a reference video for style study.

Lessons: ~2.5s per card to be readable at phone size; never parallel-reveal; hold the final frame 1s+.
