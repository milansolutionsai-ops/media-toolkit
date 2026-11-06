# Style onboarding

How a brand gets a locked editing style without anyone writing prompts. The owner points at videos they like and
reacts to what the agent makes; the agent turns that into edits, rules and reusable techniques.

Tools: `tools/library/library.py` (technique library), `tools/review/style.py` + the review app (style rounds),
`tools/gate/gate.py` (quality gate). Brand rules live in `<project>/STYLE_GUIDE.md`, nowhere else.

## The two inputs from the owner

1. **References:** links to videos they like, pasted into a session whenever they find one. No description needed.
2. **Reactions:** Keep / Maybe / Drop on each candidate in the review app, a few words when it's close. Ideas of
   their own are welcome, never required.

Never ask the owner to describe or prompt an edit. Every question is a reaction or an A/B.

## Flow

1. **Project folder.** `<root>/<project>/` with its raw footage. A new client sends one short test clip of them
   talking before round 1.
2. **References in.** For each link: read it (keyframes, transcript, caption), then
   `library.py add-ref URL --platform P --creator C`, and for every distinct technique
   `library.py add-tech NAME --what ... --recipe ... --status have|partial|missing --ref REF_ID`
   (recipe = how to make it with our tools; for missing ones, what it would take and its cost).
   A technique seen again just gains a link.
3. **Research pass (optional).** For a new niche, search for creators doing the edits the owner likes and add their
   techniques the same way.
4. **Style round.** `style.py new --project P --title T`, then one `style.py add ... --dimension D` per candidate:
   - 6-10 candidates, **one variable each** (captions, transition, sound, grade, pacing, effect, layout) on the same
     base cut, so a reaction means one thing.
   - Mix library techniques (`--origin library --technique ID`) with **your own ideas** (`--origin claude`,
     shown as "Claude's idea"). At least two per round are your own: rounds that only remix the references fail.
   - One-line `--explain` per candidate, plain words.
   - Every candidate passes the quality gate below first.
5. **Reactions.** The review hook announces "Style reactions ready". `style.py claim P N`, then `show` and
   `summary P` (all rounds by dimension).
   - Keep → becomes a rule. Maybe → an allowed option. Drop → `library.py verdict TECH BRAND drop`.
   - Notes on Maybe items shape the next round's variants.
6. **Next round or lock.** Build the next round from the reactions. When a round brings no new Drops, show one
   "combined" candidate with every kept choice together; if it's kept, lock.
7. **Lock.** Write the kept choices into `<project>/STYLE_GUIDE.md` as short rules (Keep = rule, Maybe = option),
   bump its version, and render `library.py render`. From here every video is produced against that guide.

## Quality gate (before the owner sees anything)

1. `gate.py RENDER [--ref-shots MIN MAX]`: flash frames, loudness (-14 LUFS ±1), true peak (≤ -1 dBTP), clicks
   at cuts, pacing against the references' shot lengths.
2. **Frame by frame, start to finish:** `gate.py RENDER --sheets DIR --events T1,T2,...` and read every sheet it
   writes: the whole video at 3 fps, plus every single frame around each event. Pass as events every cut (jump
   cuts on one angle are invisible to scene detection, so take them from the EDL, divided by the EDL speed) and
   every title or graphic start and end. Look for: text over a head or face, captions blinking off at a cut,
   flashes, wrong frames in overlays, anything in a platform safe zone. Costs session time only (about 1-2k
   tokens per sheet, ~25 sheets for a 60s video), no API spend.
3. Sound: earshot `timeline` + `critique` on the mix (voice level, music under voice, SFX timing).
4. Safe zones: check captions and graphics with the review app's safe-zone overlay for the target platform.
5. **Fresh critic.** A separate agent gets the render, the references and the brand guide, and is told to roast,
   not praise: a verdict, ranked problems with timecodes and evidence (frames, levels), and the five fixes to do
   first.
6. Fix and re-check, at most 3 passes. Anything still open is flagged to the owner, never hidden.

## Licences of borrowed kits

- MIT/Apache kits: code may be ported into the toolkit with their licence notice.
- Kits without a licence: all rights reserved. Read them for ideas, rebuild in our own code, copy nothing.
- Never commit another creator's posts, frames or captions to this public repo. The library data stays in the
  private workspace.
