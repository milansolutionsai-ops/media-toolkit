# Motion reference library

Local, searchable references for the "reference first" step (TOOLKIT.md). Take the grammar of a reference
(pace, type, transitions, palette logic), never its content. All cloned 2026-10-30 into `references/`
(gitignored, each is its own git repo: `git -C references/<name> pull` to update).

| Folder | What | Licence | Use it for |
|---|---|---|---|
| `awesome-opus5-5-videos/` | **703 Claude-made videos with the creator's prompt**: 369 motion, 117 3D, 116 explainer, 101 interactive. `data/videos.json` (slug, author, post_url, category, tech_tags, prompt), `prompts/<slug>.md`. Previews: `https://skillry.dev/ai-videos/opus-5-5/<slug>` | MIT | Finding a look Milan likes and the prompt that made it |
| `awesome-claude-5-5-videos/` | A second curated list with notes on how each was made (`data/cases.csv`: label, path, creator disclosure, duration) | CC-BY-4.0 | Cross-checking how a viral piece was actually built |
| `mg-styles-15/` | **15 motion-design styles**, each a 10s film with prompt + code + MP4 (`prompts/NN-style.md`, `videos/NN-style.mp4`): flat vector, line art, isometric, 3D render, cel boil, collage, liquid, morph, bauhaus, synthwave, aurora glass, hanazi, paperclip, pixel, HUD. Has a scoring `rubric.md` | MIT | A style vocabulary for motion pieces in any project; the videos double as references for `review_sheets.py --frames` |
| `lemo-opuscar/` | **43+ film styles** as a Claude Code skill/plugin (`styles/<name>/`, `DIRECTOR.md`, `TECHNIQUE.md`): art deco, blueprint, chalkboard, dark keynote, dataviz, hologram HUD, ink wash, newsreel, papercut, risograph, pixel RPG... | MIT | Stylised pure-motion films for other projects. Not installed as a plugin; read a style folder or install from its README when a project needs it. Tuned for Opus-class models |
| `ClaudeAnimationBase/` | Hand-painted cartoon kit (p5.brush, a character with 31 emotions, `ANIMATION_GUIDE.md`) | MIT | Cartoon pieces only. Slow without a GPU (seconds per frame) |

## How to search

```bash
# by words in the prompt (e.g. a dashboard, a product launch, kinetic type)
python -I -c "import json,sys;q=sys.argv[1].lower();[print(v['slug'],v['category'],v['tech_tags']) for v in json.load(open('tools/motion/references/awesome-opus5-5-videos/data/videos.json',encoding='utf-8')) if q in v['prompt'].lower()]" "kinetic"
# by category / tech: category in motion|3d|explainer|interactive; tags like gsap, svg, canvas, threejs, shader
rg -l "gsap" tools/motion/references/awesome-opus5-5-videos/prompts | head
# a style family
ls tools/motion/references/lemo-opuscar/styles   ·   ls tools/motion/references/mg-styles-15/videos
```

Then: show Milan 3-5 candidates (preview link or local MP4), let him pick, run
`review_sheets.py <video> --frames` on the pick, write its grammar into the project's style notes.
Brand rules of the project always win over the reference (fonts, colours).
