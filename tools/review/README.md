# Video review

A local Frame.io-style review app. The reviewer marks exact frames or sound in a render and leaves notes;
Claude is told automatically, fixes, and the reviewer checks each fix before/after.

- Runs on `127.0.0.1:47615` only. Python stdlib + ffmpeg + Node (hook). No paid APIs.
- The reviewer sees only titles, video, notes and statuses. No file names, paths or logs.
- Workspace root = env `REVIEW_ROOT`, default: the folder that contains `media-toolkit/`.
- Standalone version with a quickstart for anyone: https://github.com/milansolutionsai-ops/claude-review-inbox

## For Claude

```bash
python media-toolkit/tools/review/review.py register --project my-project --title "My video" --render path/to/final.mp4
python media-toolkit/tools/review/review.py list
python media-toolkit/tools/review/review.py claim my-project/my-video
python media-toolkit/tools/review/review.py show my-project/my-video
python media-toolkit/tools/review/review.py register --project my-project --title "My video" --render path/to/v2.mp4 --fixes fixes.json
```

`fixes.json` answers every open note (new notes + anything marked Not fixed):
`{"answers": [{"note_id": "ab12cd", "explanation": "One line, plain words.", "after": [start, end]}]}`.
Frame ranges are optional; they default to the note's own frames. Give `after` when the cut moved the spot.

Loop: register → reviewer sends notes → the hook prints "Feedback ready" on the next prompt → `claim` →
`show` (notes, frames, seconds, stills of the exact frames) → fix → `register --fixes` → reviewer checks.

## Edit plan (before the first cut)

For videos with motion moments: post the plan first, build only after the reviewer sends it back.

```bash
python media-toolkit/tools/review/review.py plan --project my-project --title "My video" --plan plan.json
```

`plan.json`: `{"rows": [{"start": 0.0, "end": 2.8, "text": "Hook, face, HONEST appears", "still": "s1.jpg"}]}`
(seconds on the output timeline; `still` optional, any image). The reviewer marks every line OK or Change (with a
reason) and sends; the hook prints "Edit plan back"; `claim` + `show` print the lines. Revise with `plan` again
(old version kept as `plan-vN.json`), or `register` the first cut. Statuses: `plan_waiting` → `plan_sent` → `waiting`.

## Style rounds

One-variable candidates the reviewer sorts into Keep / Maybe / Drop (see `docs/STYLE_ONBOARDING.md`):

```bash
python media-toolkit/tools/review/style.py new --project my-project --title "Captions and transitions"
python media-toolkit/tools/review/style.py add --project my-project --round 1 --render c1.mp4 --label "Bold caps" --dimension captions --origin library --technique bold-caps
python media-toolkit/tools/review/style.py claim my-project 1
python media-toolkit/tools/review/style.py summary my-project
```

Data: `<project>/_style/round-<n>/` (`round.json`, `reactions.json`, `c1.mp4`, `c2.mp4`...). Every player has a safe-zone
overlay (Instagram, TikTok, Shorts, LinkedIn).

## Folder contract

```
<project>/_review/<slug>/
  video.json        title, status, rounds, fps, context windows
  rN.mp4            review copy: exact CFR, all-intra, visually lossless (write-once; master untouched)
  rN/               sprite.jpg, sprite.json, peaks.json, stills/, claim.json
  notes-rN.json     notes + verdicts sent for round N
  fixes-rN.json     Claude's answers that came with round N
  fixcheck-rN/      before/after frame pairs or clips per note
<root>/_review-index.json   one-file summary the hook reads
```

Statuses: `waiting` → `sent` → `fixes_ready` → `sent` or `approved`.

## Setup (once, Windows)

```bash
python media-toolkit/tools/review/install.py
```

- Starts the server with Windows (hidden Startup entry) and starts it now.
- Opens the app in Edge: menu (...) > Apps > Install this site as an app, tick "Pin to taskbar". The installed
  app gets its own window, taskbar button and icon. (Pinning a plain browser window pins Edge itself.)
- Prints the hook block for `~/.claude/settings.json`.
- Reviewer name on notes: env `REVIEW_AUTHOR` (default `reviewer`).
- `launch.pyw` starts the server if needed and opens an app-mode window, for when you don't want to install.

## Tests

```bash
python -m unittest discover -s tools/review/tests -t tools/review
node --test "tools/review/**/*.test.mjs"
```
