# Video review

A local Frame.io-style review app. The reviewer marks exact frames or sound in a render and leaves notes;
Claude is told automatically, fixes, and the reviewer checks each fix before/after.

- Runs on `127.0.0.1:47615` only. Python stdlib + ffmpeg + Node (hook). No paid APIs.
- The reviewer sees only titles, video, notes and statuses. No file names, paths or logs.
- Workspace root = env `REVIEW_ROOT`, default: the folder that contains `media-toolkit/`.

## For Claude

```bash
python media-toolkit/tools/review/review.py register --project milan-content --title "03 Context first" --render path/to/final.mp4
python media-toolkit/tools/review/review.py list
python media-toolkit/tools/review/review.py claim milan-content/03-context-first
python media-toolkit/tools/review/review.py show milan-content/03-context-first
python media-toolkit/tools/review/review.py register --project milan-content --title "03 Context first" --render path/to/v2.mp4 --fixes fixes.json
```

`fixes.json` answers every open note (new notes + anything marked Not fixed):
`{"answers": [{"note_id": "ab12cd", "explanation": "One line, plain words.", "after": [start, end]}]}`.
Frame ranges are optional; they default to the note's own frames. Give `after` when the cut moved the spot.

Loop: register → reviewer sends notes → the hook prints "Feedback ready" on the next prompt → `claim` →
`show` (notes, frames, seconds, stills of the exact frames) → fix → `register --fixes` → reviewer checks.

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

## Setup (once)

```bash
python media-toolkit/tools/review/install.py
```

Creates a "Video Review" Start-menu shortcut (pin it to the taskbar by hand) and prints the hook block for
`~/.claude/settings.json`. The shortcut starts the server silently if needed and opens an app window.

## Tests

```bash
python -m unittest discover -s tools/review/tests -t tools/review
node --test "tools/review/**/*.test.mjs"
```
