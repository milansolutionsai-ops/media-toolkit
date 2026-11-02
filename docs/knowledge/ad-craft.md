# Ad craft reference (by pipeline stage)

Permanent techniques for ads, promos and any music-led piece, sorted by the pipeline step where they apply.
Suggestions, not rules: the project's style guide decides. Rewritten 2026-11-02 from a first-hand read of the sources.

Sources (raw files stay in the client folder, nothing client-specific here):
- **[T1]** TRW "Be Creative" mastermind, call 1 (Dec 2023): the CTA section of a 3.5-min hype ad, 19 video + 14 audio layers.
- **[T2]** Same, call 2: music selection and bridging, across that ad and a calm, smooth "awareness" ad.
- **[N]** Milan's course notes (research steps + "winning ad formula").
- **[P]** Milan's old pitch-research doc (the prompting method only; the copy itself is dropped).
- **[V]** "Veo guider v2" (AI video prompting).
- **[B]** A benchmark of 12 long-running Meta coaching ads (2026-11-01). One niche, one offer type: treat as a strong
  hint for talking-head direct response, not as law.

## The one idea that ties it together: energy is a curve, set by the narrative

Every piece has an energy curve: each section carries one emotion, and the sound and pace follow it [T2]. Two rules
fall out of that, and they hold for calm pieces as much as loud ones:
1. **Match the vibe.** A smooth, calm speaker under aggressive music loses; so does a hype montage under a soft bed.
   "Music will make or break a video" [T2]. Pick the energy level per section from what is being said.
2. **Never wind down before the ask.** Don't resolve the energy before the CTA or the last line: the ending should
   feel like the start of something, not a wrap-up [T1]. For a loud ad that means keep the music rising. For a calm
   talking head it means the ask is the sharpest point of the piece, not a soft recap. (Same as our "end on the point".)

The previous version split everything into HYPE vs TRUST modes. That split doesn't come from the course: the calm
"awareness" ad in [T2] still used three tracks, a disruptive hook and a bridge. The split came from one client's offer
(calm talking head for a high-ticket coaching sale). Energy level is a dial per section, not a mode per ad.

## 1. Research (before the script)

- Three passes: **customer**, **competitor**, **trend** [N]. Competitor + trend = Meta Ad Library (hooks, styles, fonts):
  our `ad-read` skill pulls it.
- Walk the buyer's whole journey, then answer: what pain does it solve? does it really solve it? what else does it give? [N]
- Avatar: goals and desired outcomes, problems and pain points, roadblocks and objections [N].
- **Daily-situation prompt** [P]: describe the buyer precisely (age, role, business, what they've already tried), then ask
  an LLM for *real-life moments in their day that remind them of the problem and frustrate them*. Then fears, then
  internal effects (stress, sleep). Those moments become hooks and story beats. Concrete beats generic every time.

## 2. Script

- **Hook in 2-6s** that drives curiosity; on-screen text from the first frame; no intro, logo or greeting [N].
- **Pitch** = the problem (ideally one they hadn't named yet, which needs research), the solution, why you're the
  authority [N]. Then **social proof** (people using or liking it) [N], then the **CTA: exactly what to do and exactly
  what happens next** [N].
- One core message, stripped down, plain enough for a kid [N].
- Talking-head direct response, from [B]:
  - Hook names the buyer (role, status) or states a contradiction.
  - "It's not you, it's the method" reframe.
  - One specific proof case over a volume claim.
  - The problem told as a story (a client's or the founder's), never "you have X". This also keeps Meta ads within policy.
  - In ads over 60s, ask for the action by about 0:30 and again at the end.
  - A buyer filter for high prices.

## 3. Music (pick early, see TOOLKIT "music-led pieces")

- **One track per emotional section.** Under ~30s, one track usually holds. At 60s+, expect 2-3, because the
  narrative shifts emotion (hook → proof → CTA) [T2].
- **The hook can break the theme.** The hook's music can fit the hook's visuals rather than the whole ad, layered
  with the main theme, which then takes over [T2].
- **Intro under the CTA, not the outro.** Song endings resolve and intros build. For the closing section, take a
  build-up passage from the start of a track, not its last bars [T1]. `beats.py` lists them under `builds`
  (`ramp` = getting louder, `pre-drop` = getting brighter into a drop; end the bed just before the drop).
  `splice_music.py` cuts the bed to the exact length on the beat.
- **Bridge track changes** instead of leaving a gap or a hard jump [T2]:
  - Cut a short slice from the *next* track (a high note, a riser) and place it just before the switch, over the end
    of the outgoing track.
  - Add a heartbeat or pulse hit on the switch itself. A visual transition on the same frame sells it.
  - A secondary bridge layer can stack on the primary one.

## 4. Sound design

- **Every SFX sits on its visual frame**: whooshes on movement, pings on notifications, impacts on reveals [T1].
- **Density rises toward the end.** Layer more SFX as the piece builds, so the close is the fullest moment [T1].
  `make_sfx.py` places SFX on cue times.
- Talking heads: none, or very sparse (Milan's style guide: no SFX).

## 5. Edit

- **Pace follows the curve.** Montage and b-roll ads change shot every 1-2s [N]. Talking heads cut on pauses and use
  punch-ins and cutaways (style guide), because a 1-2s cadence on a face reads as a pitch.
- Vertical, captions burned in, real setting; simple production wins in direct response [B].
- Splice a new close onto a proven ad: cut at the old CTA, record a 15-20s close, keep the captions consistent [B].
  The editor does this already (two ranges from two sources in one EDL).

## 6. AI b-roll (Veo-style), only when it can't be shot [V]

- Write it like a one-shot film script of what the camera sees.
- **Opening:** mood + shot type first ("a raw, handheld medium shot...").
- **Subject:** concrete visual anchors and a precise verb ("strides", not "walks").
- **Setting:** textures.
- **Lighting:** named exactly, plus a 3-5 colour palette with intent.
- **Camera motion:** stated separately from subject motion.
- **Composition:** use the terms (thirds, leading lines, shallow depth of field).
- **Length:** 120-180 words per shot.
- **No memory between prompts:** each one stands alone (no "still", "now", "the first"), so re-state every detail per shot.
- Real footage first.

## Dropped, and why

- **Pricing PDF** (a four-question price test): pricing research, not production.
- **The pitch copy and "Conversion Kingdom" style names** in [P]: generic and overwrought. Only the research method survives.
- **The HYPE/TRUST split as a frame**: explained above.
- **Anything about the course's own product or presenters**: content, not craft.
