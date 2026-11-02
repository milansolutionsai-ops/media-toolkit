# media-toolkit

**A full AI video studio for €0 a month.** Talking-head editing, motion graphics, voiceover, music and sound
design, driven by Claude Code, running locally on a laptop CPU. No subscriptions.

Built by [Milan Veljkovikj](https://www.linkedin.com/in/milan-veljkovikj/) for his own LinkedIn and YouTube Shorts,
then turned into a reusable engine for any project. Updated with every change.

## What it does

| Step | How | Cost |
|---|---|---|
| **Record** | OBS profile + 9:16 framing guide, phone camera, teleprompter | free |
| **Transcribe** | Groq Whisper (free tier) or local faster-whisper, words snapped to real speech | free |
| **Find mistakes** | stutters, retakes, false starts, phrases said twice; the newer take always wins | free |
| **Cut** | on pauses, never inside a word, 30 ms fades, speed-up with pitch kept | free |
| **Captions** | sentence pills or active-word highlight, brand fonts, burned in | free |
| **Punch-ins & reframes** | alternating wide/tight framing, hook title behind the speaker (person cutout) | free |
| **Motion graphics** | HyperFrames (HTML + GSAP → MP4), spring motion, templates, storyboard stills before any render | free |
| **Transitions** | full-screen graphic cutaways with a whip-pan exit back to the face | free |
| **Voice** | Kokoro (local), Gemini 3.8 Flash TTS (free tier); ElevenLabs if you pay | free |
| **Music** | beat grid, build-up and drop detection, beat-accurate splicing to any length | free |
| **SFX** | code-generated sounds, real CC0 recordings from Openverse | free |
| **Listen** | [earshot](https://github.com/Leonxlnx/earshot): the agent hears the mix, ranks sounds, checks sync to the cuts | free |
| **Review** | contact sheets, phone-size previews, scored self-critique to 8/10 before a human sees it | free |

## How it works

```
script ─► record ─► transcribe ─► find mistakes ─► cut list (EDL) ─► render
                                                       ▲
             motion graphic ─► storyboard stills ─► approve ─► overlay
             music ─► beat grid ─► splice ─► SFX on hits ─► listen (earshot) ─► mix
```

Claude Code is the operator. `TOOLKIT.md` is the map it reads first; each tool has a README with its options, version
and how to swap it. Brand rules (fonts, colours, pace) live in each project's `STYLE_GUIDE.md`, never in the tools.

## Free by design, upgrade paths documented

Every paid or GPU route we evaluated is recorded in [`docs/UPGRADES.md`](docs/UPGRADES.md): ElevenLabs, Higgsfield,
Kling/Kie, Veo, Suno, Remotion, Blender on an RTX GPU, stock libraries. What each adds, what it costs, and the
trigger that would make it worth paying for.

## Craft notes

[`docs/knowledge/ad-craft.md`](docs/knowledge/ad-craft.md): ad and promo techniques by pipeline stage. Research,
script structure, music (one track per emotional section, build-ups under the call to action, bridging tracks),
sound design, pacing, AI b-roll prompting.

## Get started

See [`SETUP.md`](SETUP.md). Then open Claude Code in a project folder next to this repo and say:
"Read `../media-toolkit/TOOLKIT.md` and edit `RECORDINGS/take1.mp4` per my style guide."

## Credits

- Editor: fork of [browser-use/video-use](https://github.com/browser-use/video-use) (MIT).
- Mistake finder, music splicer and kick-band beat phase adapted from
  [nateherkai/herk-edit-kit](https://github.com/nateherkai/herk-edit-kit) (MIT).
- Motion: [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0). Listening:
  [earshot](https://github.com/Leonxlnx/earshot) (MIT, installed separately). Voice:
  [Kokoro](https://github.com/thewh1teagle/kokoro-onnx). SFX: [Openverse](https://openverse.org).

MIT licence. Want this set up for your team, or videos made with it? Reach out on LinkedIn.
