# Upgrade paths (paid and GPU routes)

This toolkit is free by design: every step runs locally or on a free tier, on a Windows laptop with an AMD iGPU and no NVIDIA card. This page lists what money or a real GPU would buy at each step, what was already evaluated, and why it was or wasn't taken. Prices were checked on 2026-11-02 from third-party summaries unless noted; confirm on the vendor's page before buying.

Status key: **skipped** (evaluated, not worth it now), **parked** (worth it once a trigger hits), **candidate** (first in line if money is spent).

## Transcription

| Option | Adds over Groq / faster-whisper | Cost | Status | Why |
|---|---|---|---|---|
| ElevenLabs Scribe v2 | Keeps "um"/"uh" in the transcript, multi-speaker diarization. It is video-use's default and Nate Herk's choice. | ~$0.22 per audio hour (batch), ~$0.39 realtime | skipped | Groq Whisper is free and gives word timestamps. Its filler loss is covered by silence-based cut snapping. |
| Groq Whisper paid tier | Removes the 25 MB free-tier file cap | ~$0.04 per audio hour (2026-10-08) | parked | The free tier already handles ~100 min per file via audio-only upload. |
| VibeVoice-ASR on a rented GPU | Real speaker diarization | GPU rental, price not verified | parked | CUDA-only. Only matters for interviews or podcasts. |

## Editing and caption apps

| Option | Adds | Cost | Status | Why |
|---|---|---|---|---|
| Descript | Text-based editing UI, manual trim handles | ~$24/month (2026-10-08, not verified) | skipped | Four models consulted all said to adopt video-use instead. A SaaS editor adds a recurring cost and produces no reusable style rules. |
| OpusClip | Auto-clipping long videos into shorts | price not verified | skipped | Mentioned only in passing. The pipeline records native short-form. |
| Submagic, Captions-style apps | Template captions | not evaluated | not evaluated | Branded captions are already built in. |

## Voice

| Option | Adds | Cost | Status | Why |
|---|---|---|---|---|
| ElevenLabs Starter / Creator | Best-in-class TTS, a commercial licence, voice cloning (Creator adds professional cloning) | Starter ~$5-6/month, Creator ~$22/month | **candidate** | The free tier has no cloning and no commercial licence (10k characters/month, attribution required). This is the upgrade if the local clone sounds off. |
| Gemini 3.8 Flash TTS paid | Removes free-tier rate limits | ~$0.013 per minute (per the toolkit's voice README) | parked | The free tier works if scenes are run one at a time. |
| VoiceStudio with OmniVoice | Free local cloning, 646 languages | free | skipped | OmniVoice is CC-BY-NC (non-commercial). VoxCPM2 (Apache-2.0) inside VoiceStudio is the allowed engine instead. Cloned voices are on hold for now. |
| VoxCPM2 LoRA fine-tune | A clone that learns the speaker's rhythm from 5-10 minutes of audio | rent a 24 GB GPU for about an hour, roughly $1 one-off (estimate, not verified) | parked | It needs ~20 GB of VRAM. Free Colab/Kaggle GPUs (16 GB) might work but are tight. |

## Music

| Option | Adds | Cost | Status | Why |
|---|---|---|---|---|
| Suno via Kie.ai | Generated instrumental cut to the brief | Kie credits, price not verified | parked | Herk's kit uses it for showreels. Pixabay tracks plus the beat splicer cover the need today. |
| Google Lyria | Generated music | access and price not verified | parked | Noted, never tested. |
| Epidemic Sound | Large licensed library plus SFX | ~$10-18/month personal, ~$17-40/month Pro (sources conflict) | parked | Worth it for client ads, where licence clarity matters. |
| Artlist | Music and SFX, and footage on higher tiers | ~$10-15/month Social, ~$40/month Max (sources conflict) | parked | Its Max tier would also cover stock footage. |

## SFX

| Option | Adds | Cost | Status | Why |
|---|---|---|---|---|
| Sonilo | Watches the video and generates frame-accurate SFX through one API call | free tier with limits; paid price not verified | parked | earshot plus Openverse CC0 recordings cover placement and sourcing for free. |
| Mirelo SFX 2.0 | Video-to-sound: synced foley and ambience | price not verified | parked | Same reason. Not clearly open source. |
| ElevenLabs sound effects | Prompt-to-SFX (used in Herk's kit) | uses ElevenLabs plan credits | parked | Comes bundled if the ElevenLabs plan is bought for voice. |

## Motion graphics and 3D

| Option | Adds | Cost | Status | Why |
|---|---|---|---|---|
| Higgsfield Katana | A claude.ai connector (`/katana`) that recreates a reference edit's style with your product. Also AI footage. | Higgsfield credits: ~$15-19/month Starter, ~$39-59/month Plus (sources conflict) | skipped | It runs in chat by hand, outside the pipeline. It copies someone else's look instead of the brand. The storyboard step plus a reference video gets most of the value for free. Revisit only if free credits allow a 15-minute A/B test. |
| Higgsfield 3D characters (the animated-sitcom reel style) | Consistent generative 3D characters | Higgsfield credits | skipped | Character consistency is the hard part, and the look is now crowded. The writing patterns were kept instead. |
| Claude Motion | `/motion` in claude.ai chat, editable animation to MP4 | included in the Claude plan | parked | It doesn't run in Claude Code and can't sync graphics to spoken words. HyperFrames does both. |
| Remotion (React to video) | A mature alternative renderer | free for individuals and companies of up to 3 people; $25 per seat per month above that, or $0.01 per render with a $100/month minimum | skipped | HyperFrames (Apache-2.0) has no company licence trigger. |
| Blender on an NVIDIA GPU | Real 3D scenes, product shots, rendered camera moves | needs an NVIDIA RTX card. 12-16 GB VRAM is workable; a 32 GB RTX 5090 is the high end. Card price not verified. | parked | Nothing in this pipeline needs 3D yet. Blender's Cycles renderer is far slower on CPU or an AMD iGPU. |

## AI video and b-roll generation

| Option | Adds | Cost | Status | Why |
|---|---|---|---|---|
| Kling through Kie.ai | Camera moves and moving b-roll from stills | Kie credits, price not verified | **candidate** | It's the fallback when footage can't be shot. Herk's kit has a small client for it. |
| Seedream through Kie.ai | Stills from a logo or reference | Kie credits, price not verified | parked | Pairs with Kling. |
| Google Veo | Text-to-video b-roll | price not verified | parked | The toolkit holds a Veo prompting guide as the documented fallback. |

## Stock footage

There is no stock pipeline today. The free order is: your own screen recordings first, then the Pexels and Pixabay free APIs, then AI generation. Paid tiers (Artlist Max, Epidemic) come in only for client ads that need a lot of b-roll.

## Hardware

| Option | Adds | Status |
|---|---|---|
| NVIDIA RTX GPU (local desktop, or a used card) | CUDA: fast Whisper, VoxCPM2 at real-time speed instead of ~10x slower, local fine-tunes, Blender Cycles, faster HyperFrames frame capture | parked |
| Rented GPU (RunPod, Modal and similar) | The same capabilities pay-as-you-go, with no subscription | **candidate** for one-off jobs |

## When an upgrade is worth it

1. **Client work needs commercial voice in a cloned voice** and VoxCPM2 doesn't pass a listening test. Buy ElevenLabs Starter or Creator.
2. **Voiceover or dubbing becomes weekly.** A local clone takes ~10 minutes per 60s line on CPU, so rent a GPU or buy a plan.
3. **A brief needs footage that can't be shot** (product in use, locations). Buy Kie credits per project, priced before generating.
4. **Client ads need licence-clean music at volume.** Buy an Epidemic or Artlist plan and bill it to the project.
5. **Multi-speaker content** (interviews, podcasts). Use Scribe at cents per hour.
6. **3D or product-render work shows up in paid briefs.** Then an RTX desktop (or rented render time) for Blender pays for itself. Until then, no.
