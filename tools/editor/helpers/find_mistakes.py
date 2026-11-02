"""Propose cuts for spoken mistakes: stutters, retakes, false starts, and stretches where Whisper may hide a restart.

    uv run python helpers/find_mistakes.py <edit>/transcripts/<name>.json [--out-dir <edit>]
    → <name>.cut-candidates.json + .md

Mechanical detection only: every candidate needs a human/agent read in context before it goes into the EDL
(emphatic "never, never" looks exactly like a stutter). Default for a retake is Milan's rule: drop the earlier
take, keep the newer one. "suspect" candidates are not cuts: re-transcribe that stretch (Whisper often writes one
copy across both takes of a restart, leaving a long word or a long silence).

Adapted from herk-edit-kit `cut-mistakes/scripts/find-cut-candidates.mjs`:
Copyright (c) 2026 Nate Herk, MIT License (https://github.com/nateherkai/herk-edit-kit/blob/main/LICENSE).
"""
import argparse
import json
import re
from pathlib import Path

STOP = set("a an and are as at be but by for from i if in is it of on or so that this to was we with you your "
           "they their there what when where why how like um uh".split())


def _token(text):
    return re.sub(r"^[^a-z0-9$%]+|[^a-z0-9$%]+$", "", (text or "").lower())


def _join(ws):
    return re.sub(r"\s+([,.!?;:])", r"\1", " ".join(w["text"] for w in ws))


def segments(words, gap=0.85, sentence_len=7.5, max_len=16.0):
    """Split words into phrases on a long gap, a sentence end after sentence_len s, or max_len s."""
    out, s = [], 0
    for i in range(1, len(words) + 1):
        if i < len(words):
            prev, cur = words[i - 1], words[i]
            elapsed = cur["end"] - words[s]["start"]
            if not (cur["start"] - prev["end"] > gap or (re.search(r"[.!?]$", prev["text"]) and elapsed >= sentence_len)
                    or elapsed >= max_len):
                continue
        out.append({"w0": s, "w1": i - 1, "start": words[s]["start"], "end": words[i - 1]["end"],
                    "text": _join(words[s:i])})
        s = i
    return out


def _sig(text):
    toks = re.sub(r"[^a-z0-9\s$%]", " ", text.lower()).split()
    return [t for t in toks if len(t) > 2 and t not in STOP][:18]


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / max(1, len(a | b))


def find_candidates(words, long_word=1.0, long_gap=1.5):
    words = [w for w in words if w.get("type", "word") == "word"]
    cands = []

    for i in range(1, len(words)):
        a, b = words[i - 1], words[i]
        if _token(a["text"]) and _token(a["text"]) == _token(b["text"]) and b["start"] - a["end"] < 0.5:
            cands.append({"type": "stutter", "confidence": "high", "recommend": "cut",
                          "cut": [round(a["start"], 3), round(b["start"], 3)], "removes": a["text"], "keeps": b["text"],
                          "context": _join(words[max(0, i - 6):i + 6])})

    segs = segments(words)
    sigs = [_sig(s["text"]) for s in segs]
    for i in range(len(segs)):
        for j in range(i + 1, min(len(segs), i + 9)):
            if segs[j]["start"] - segs[i]["end"] > 75:
                break
            score = _jaccard(sigs[i], sigs[j])
            same_open = sum(1 for x, y in zip(sigs[i][:4], sigs[j][:4]) if x == y) >= 2
            if score >= 0.34 or (score >= 0.24 and same_open):
                false_start = same_open and segs[i]["end"] - segs[i]["start"] < 6 and segs[j]["start"] - segs[i]["end"] < 12
                cands.append({"type": "false_start" if false_start else "retake",
                              "confidence": "high" if score >= 0.45 else "medium" if score >= 0.34 else "low",
                              "recommend": "cut" if score >= 0.34 else "review", "score": round(score, 3),
                              "cut": [round(segs[i]["start"], 3), round(segs[j]["start"], 3)],
                              "removes": segs[i]["text"], "keeps": segs[j]["text"]})

    # A phrase said twice in a row inside one segment ("what goes in, what happens, what goes in, what happens")
    toks = [_token(w["text"]) for w in words]
    i = 0
    while i < len(words):
        hit = None
        for n in range(8, 2, -1):
            for j in range(i + n, min(len(words) - n + 1, i + 3 * n)):
                if toks[i:i + n] == toks[j:j + n] and words[j]["start"] - words[i + n - 1]["end"] < 3.0:
                    hit = (n, j)
                    break
            if hit:
                break
        if hit:
            n, j = hit
            cands.append({"type": "phrase_repeat", "confidence": "medium", "recommend": "cut",
                          "cut": [round(words[i]["start"], 3), round(words[j]["start"], 3)],
                          "removes": _join(words[i:j]), "keeps": _join(words[j:j + n]),
                          "context": _join(words[max(0, i - 4):j + n + 4])})
            i = j
        i += 1

    for i, w in enumerate(words):
        stretched = w["end"] - w["start"] > long_word
        gap = i + 1 < len(words) and words[i + 1]["start"] - w["end"] > long_gap
        if stretched or gap:
            end = words[i + 1]["start"] if gap else w["end"]
            cands.append({"type": "suspect", "confidence": "low", "recommend": "re-transcribe",
                          "cut": [round(w["start"], 3), round(end, 3)],
                          "removes": "", "keeps": "",
                          "context": _join(words[max(0, i - 6):i + 6]),
                          "note": f"word '{w['text']}' lasts {w['end'] - w['start']:.2f}s" if stretched
                                  else f"{end - w['end']:.2f}s silence after '{w['text']}'"})

    cands.sort(key=lambda c: c["cut"][0])
    for n, c in enumerate(cands, 1):
        c["id"] = f"c{n:03d}"
    return cands


def to_markdown(name, cands):
    fmt = lambda s: f"{int(s // 60):02d}:{s % 60:05.2f}"
    lines = [f"# Cut candidates: {name}", "", f"{len(cands)} candidates. Read each in context before it goes in the EDL.", ""]
    for c in cands:
        lines += [f"## {c['id']} {c['type']} · {c['confidence']} · {c['recommend']}",
                  f"{fmt(c['cut'][0])}-{fmt(c['cut'][1])} ({c['cut'][1] - c['cut'][0]:.2f}s) {c.get('note', '')}".rstrip()]
        lines += [f"- {k}: {c[k]}" for k in ("removes", "keeps", "context") if c.get(k)]
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    src = Path(a.transcript)
    cands = find_candidates(json.loads(src.read_text(encoding="utf-8"))["words"])
    out = Path(a.out_dir or src.parent)
    out.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    (out / f"{stem}.cut-candidates.json").write_text(json.dumps(cands, indent=1), encoding="utf-8")
    (out / f"{stem}.cut-candidates.md").write_text(to_markdown(stem, cands), encoding="utf-8")
    counts = {}
    for c in cands:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    print(json.dumps({"candidates": len(cands), "counts": counts, "md": str(out / f"{stem}.cut-candidates.md")}))


if __name__ == "__main__":
    main()
