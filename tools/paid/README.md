# Paid routes

Ready-to-run scripts for the upgrades in [`docs/UPGRADES.md`](../../docs/UPGRADES.md). Plug in a key (or a GPU) and
they work. The free pipeline never calls them.

**Every script is a dry run until you add `--go`.** Without it, it prints what it would buy and stops. A file that
already exists is never generated twice. Keys go in `.env.local` at the toolkit root (gitignored) and are never
printed.

| Route | Script | Key in `.env.local` | What it buys | Tested |
|---|---|---|---|---|
| Kling video, Seedream stills, Suno music (Kie.ai) | `kie.py` | `KIE_API_KEY` | b-roll from a still, product stills, a custom instrumental bed | dry run only (no key) |
| Higgsfield API (50+ models: Kling, Seedance, Wan, MiniMax, Soul) | `higgsfield.py` | `HF_KEY` (`id:secret`) | any model on one balance | dry run only (no key) |
| Gemini Omni Flash video (replaced Veo, shut down 2026-10-22) | `omni_video.py` | `GEMINI_VIDEO_API_KEY` (billing on) | text or image to video with sound, 9:16 | request accepted; free tier is capped at 0, so billing is required |
| ElevenLabs sound effects | `eleven_sfx.py` | `ELEVENLABS_API_KEY` | prompt-to-SFX kits | dry run only (no key) |
| ElevenLabs voice | `../voice/eleven_vo.py` | `ELEVENLABS_API_KEY` | final VO, word alignment | earlier session |
| ElevenLabs Scribe transcription | `../editor` `transcribe.py --backend elevenlabs` | `ELEVENLABS_API_KEY` in `tools/editor/.env` | keeps fillers, speaker labels | upstream video-use default |
| Blender on a GPU (own RTX or rented) | `blender_render.py` | none: needs Blender + a GPU | real 3D scenes and product renders | not run (no Blender on this machine) |

No script, by design: Epidemic Sound and Artlist (no public API; download by hand, keep the licence), Remotion
(a framework, not a service), Higgsfield Katana (a claude.ai connector, used in chat), Sonilo and Mirelo (no
verified API docs yet).

## Recipes

**Product shot b-roll (Nate Herk's recipe).** Two stills of the same object in two states, then a video between them:
```bash
python tools/paid/kie.py image --prompt "studio shot of <product>, plain black background, no shadows" --aspect 9:16 --out a.png --go
python tools/paid/kie.py image --ref a.png --prompt "same shot, <changed state>" --aspect 9:16 --out b.png --go
python tools/paid/kie.py video --image a.png --prompt "<how it moves from A to B>, camera locked" --out clip.mp4 --go
```
Omni does the same in one call with both frames: `omni_video.py "<FIRST_FRAME> <LAST_FRAME> ..." --image a.png --image b.png`.

**Rented GPU for Blender.** Start a pod with an NVIDIA card and Blender installed, copy `blender_render.py` and the
`.blend`, run `python blender_render.py --probe` (should list OPTIX or CUDA), then render and copy the frames back.
Stop the pod when it finishes: it bills by the minute.

## Before spending

1. Check `docs/UPGRADES.md`: the trigger for that route should be true.
2. Price the job on the vendor's site first (`kie.py credit` shows the Kie balance).
3. Generate one, look at it (`tools/motion/review_sheets.py`), then batch.
