"""Style rounds: one-variable candidates the reviewer sorts into Keep / Maybe / Drop.

  style.py new --project P --title T
  style.py add --project P --round N --render F --label L --dimension D --origin library|claude
               [--technique ID] [--explain TEXT]
  style.py claim P N        pick up sent reactions
  style.py show P N         reactions for one round
  style.py cancel P N       close a waiting round that shouldn't be reviewed (unblocks the next round)
  style.py summary P        every round's reactions grouped by dimension, for writing STYLE_GUIDE.md rules

Data: <root>/<project>/_style/round-<n>/ with round.json, reactions.json, <id>.mp4 (review copies, c1.mp4...).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import media  # noqa: E402
import store  # noqa: E402

DIMENSIONS = ("captions", "transition", "sound", "grade", "pacing", "effect", "layout", "combined")
ORIGINS = ("library", "claude")
VERDICTS = ("keep", "maybe", "drop")


class RoundOpen(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def style_dir(root: Path, project: str, n: int) -> Path:
    return Path(root) / project / "_style" / f"round-{n}"


def rounds_of(root: Path, project: str) -> list[dict]:
    out = []
    for f in (Path(root) / project / "_style").glob("round-*/round.json"):
        r = store.read_json(f)
        if r:
            out.append(r)
    return sorted(out, key=lambda r: r["n"])


def iter_rounds(root: Path):
    for f in sorted(Path(root).glob("*/_style/round-*/round.json")):
        r = store.read_json(f)
        if r:
            yield f.parent, r


def new_round(root: Path, project: str, title: str) -> int:
    if not re.fullmatch(store.SAFE_NAME, project) or ".." in project:
        raise ValueError(f"project folder name '{project}' must use only letters, digits, '-', '_' or '.'")
    existing = rounds_of(root, project)
    if existing and existing[-1]["status"] == "waiting":
        raise RoundOpen(f"style round {existing[-1]['n']} is still waiting for reactions")
    n = existing[-1]["n"] + 1 if existing else 1
    store.save_json_atomic(style_dir(root, project, n) / "round.json",
                           {"project": project, "n": n, "title": title, "status": "waiting", "created": _now(),
                            "sent_at": None, "candidates": []})
    store.rebuild_index(root)
    return n


def _load_round(root: Path, project: str, n: int) -> dict:
    r = store.read_json(style_dir(root, project, n) / "round.json")
    if not r:
        raise FileNotFoundError(f"no style round {project} {n}")
    return r


def add_candidate(root: Path, project: str, n: int, render: Path, label: str, dimension: str, origin: str,
                  technique: str | None = None, explain: str = "") -> dict:
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension must be one of {DIMENSIONS}")
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}")
    d = style_dir(root, project, n)
    r = _load_round(root, project, n)
    if r["status"] != "waiting":
        raise ValueError(f"style round {n} was already sent")
    cid = f"c{len(r['candidates']) + 1}"
    p = media.probe(render)
    fps = media.snap_fps(p["fps"])
    media.make_review_copy(render, d / f"{cid}.mp4", fps)
    c = {"id": cid, "label": label, "dimension": dimension, "origin": origin, "technique": technique,
         "explain": explain, "file": f"{cid}.mp4", "width": p["width"], "height": p["height"], "fps": fps}
    r["candidates"].append(c)
    store.save_json_atomic(d / "round.json", r)
    store.rebuild_index(root)
    return c


def cancel_round(root: Path, project: str, n: int) -> None:
    d = style_dir(root, project, n)
    r = _load_round(root, project, n)
    if r["status"] != "waiting":
        raise ValueError(f"style round {n} is '{r['status']}', only a waiting round can be cancelled")
    r["status"] = "cancelled"
    store.save_json_atomic(d / "round.json", r)
    store.rebuild_index(root)


def apply_reactions(root: Path, project: str, n: int, reactions: dict, note: str) -> None:
    d = style_dir(root, project, n)
    r = _load_round(root, project, n)
    if r["status"] != "waiting":
        raise ValueError(f"style round {n} was already sent")
    clean = {}
    for c in r["candidates"]:
        rx = reactions.get(c["id"]) or {}
        if rx.get("verdict") not in VERDICTS:
            raise ValueError("every candidate needs Keep, Maybe or Drop")
        clean[c["id"]] = {"verdict": rx["verdict"], "note": str(rx.get("note") or "").strip()}
    store.save_json_atomic(d / "reactions.json", {"reactions": clean, "note": note.strip(), "sent_at": _now()})
    r["status"], r["sent_at"] = "sent", _now()
    store.save_json_atomic(d / "round.json", r)
    store.rebuild_index(root)


def summary(root: Path, project: str) -> str:
    by_dim: dict[str, list[str]] = {}
    notes = []
    for r in rounds_of(root, project):
        rx = store.read_json(style_dir(root, project, r["n"]) / "reactions.json")
        if not rx:
            continue
        if rx.get("note"):
            notes.append(f"Round {r['n']} note: {rx['note']}")
        for c in r["candidates"]:
            v = rx.get("reactions", {}).get(c["id"], {})
            tag = " (Claude's idea)" if c["origin"] == "claude" else f" (library: {c['technique']})" if c.get("technique") else ""
            line = f"  {v.get('verdict', '?').upper()} {c['label']}{tag}, round {r['n']}"
            if v.get("note"):
                line += f": {v['note']}"
            by_dim.setdefault(c["dimension"], []).append(line)
    out = [f"Style reactions for {project}"]
    for dim in DIMENSIONS:
        if dim in by_dim:
            out += [f"{dim}:"] + by_dim[dim]
    return "\n".join(out + notes)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    nw = sub.add_parser("new"); nw.add_argument("--project", required=True); nw.add_argument("--title", required=True)
    ad = sub.add_parser("add")
    for f in ("project", "render", "label"):
        ad.add_argument(f"--{f}", required=True)
    ad.add_argument("--round", type=int, required=True)
    ad.add_argument("--dimension", required=True, choices=DIMENSIONS)
    ad.add_argument("--origin", required=True, choices=ORIGINS)
    ad.add_argument("--technique"); ad.add_argument("--explain", default="")
    for name in ("claim", "show", "cancel"):
        s = sub.add_parser(name); s.add_argument("project"); s.add_argument("n", type=int)
    sm = sub.add_parser("summary"); sm.add_argument("project")
    a = ap.parse_args(argv)
    from review import review_root
    root = review_root()
    try:
        if a.cmd == "new":
            print(f"style round {new_round(root, a.project, a.title)} created")
        elif a.cmd == "add":
            c = add_candidate(root, a.project, a.round, Path(a.render), a.label, a.dimension, a.origin,
                              a.technique, a.explain)
            print(f"added {c['id']} to style round {a.round}")
        elif a.cmd == "claim":
            r = _load_round(root, a.project, a.n)
            if r["status"] != "sent":
                print(f"nothing to claim: style round {a.n} is '{r['status']}'", file=sys.stderr)
                sys.exit(4)
            try:
                store.claim_file(style_dir(root, a.project, a.n) / "claim.json", datetime.now(timezone.utc))
            except store.ClaimTaken as e:
                print(f"already picked up at {datetime.fromisoformat(e.at).astimezone():%H:%M}")
                sys.exit(3)
            store.rebuild_index(root)
            print(f"claimed {a.project}/style-{a.n}")
        elif a.cmd == "cancel":
            cancel_round(root, a.project, a.n)
            print(f"style round {a.n} cancelled")
        elif a.cmd == "show":
            r = _load_round(root, a.project, a.n)
            rx = store.read_json(style_dir(root, a.project, a.n) / "reactions.json", {}) or {}
            print(f"{r['title']} ({a.project}, style round {a.n}, {r['status']})")
            for c in r["candidates"]:
                v = rx.get("reactions", {}).get(c["id"], {})
                print(f"- {c['id']} [{c['dimension']}] {c['label']} ({c['origin']}): {v.get('verdict', '-')}"
                      + (f", note: {v['note']}" if v.get("note") else ""))
            if rx.get("note"):
                print(f"Round note: {rx['note']}")
        else:
            print(summary(root, a.project))
    except (ValueError, RoundOpen, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
