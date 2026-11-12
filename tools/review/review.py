"""Review app CLI, for Claude.

  register --project P --title T --render PATH [--slug S] [--fixes FIXES.json]
      First time: round 1 ("First cut"). Again: a fix round; --fixes must answer every open note:
      {"answers": [{"note_id": "...", "explanation": "...", "before": [s, e]?, "after": [s, e]?}]}
      (frame ranges; missing ranges default to the note's own frames)
  plan --project P --title T --plan PLAN.json [--slug S]
      Post (or revise) the edit plan before building: {"fps"?: "30", "width"?: 1080, "height"?: 1920,
      "rows": [{"start": s, "end": s, "text": "what happens", "still"?: "path.jpg"}]}. The reviewer OKs or
      marks each row; register the first cut only after the plan was sent back.
  claim ID      pick up sent feedback (ID = project/slug)
  show ID       print the latest sent round: notes, frames, seconds, verdicts, still paths
  list          every video with status and round
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import media  # noqa: E402
import store  # noqa: E402


def review_root() -> Path:
    env = os.environ.get("REVIEW_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[3]


def die(msg: str, code: int = 2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def vdir_for(root: Path, vid: str) -> Path:
    project, _, slug = vid.partition("/")
    d = store.video_dir(root, project, slug)
    if not (d / "video.json").exists():
        die(f"unknown video {vid}")
    return d


def build_round(vdir: Path, n: int, render: Path, fps: str) -> None:
    rev = vdir / f"r{n}.mp4"
    media.make_review_copy(render, rev, fps)
    meta = media.make_sprite(rev, vdir / f"r{n}" / "sprite.jpg", fps)
    meta["frames"] = media.probe(rev)["frames"]
    store.save_json_atomic(vdir / f"r{n}" / "sprite.json", meta)
    media.make_peaks(rev, vdir / f"r{n}" / "peaks.json")


def open_notes(vdir: Path, n: int) -> dict[str, dict]:
    """Notes that need an answer in round n+1: round n's new notes plus anything marked not-fixed in round n."""
    all_notes = {}
    for k in range(1, n + 1):
        for nt in store.round_notes(vdir, k)["notes"]:
            all_notes[nt["id"]] = nt
    cur = store.round_notes(vdir, n)
    need = {nt["id"]: nt for nt in cur["notes"]}
    for nid, verdict in cur.get("verdicts", {}).items():
        if verdict == "not-fixed" and nid in all_notes:
            need[nid] = all_notes[nid]
    return need


def _rollback(vdir: Path, n: int, status: str) -> None:
    v = store.load_video(vdir)
    v["rounds"] = [r for r in v["rounds"] if r["n"] != n]
    v["status"] = status
    store.save_json_atomic(vdir / "video.json", v)
    for p in [vdir / f"r{n}.mp4", vdir / f"fixes-r{n}.json"]:
        p.unlink(missing_ok=True)
    for p in [vdir / f"r{n}", vdir / f"fixcheck-r{n}"]:
        shutil.rmtree(p, ignore_errors=True)


def cmd_register(a, root: Path) -> None:
    render = Path(a.render)
    if not render.exists():
        die(f"render not found: {render}")
    if not re.fullmatch(store.SAFE_NAME, a.project) or ".." in a.project:
        die(f"project folder name '{a.project}' must use only letters, digits, '-', '_' or '.'")
    slug = a.slug or store.unique_slug(root, a.project, store.slugify(a.title), a.title)
    if not re.fullmatch(store.SAFE_NAME, slug):
        die(f"slug '{slug}' must use only letters, digits, '-', '_' or '.'")
    vdir = store.video_dir(root, a.project, slug)

    if not (vdir / "video.json").exists():
        p = media.probe(render)
        fps = media.snap_fps(p["fps"])
        store.new_video(root, a.project, a.title, slug, fps, p["width"], p["height"])
        n = store.add_round(vdir, None)
        try:
            build_round(vdir, n, render, fps)
        except Exception:
            shutil.rmtree(vdir, ignore_errors=True)
            raise
        store.rebuild_index(root)
        print(f"registered {a.project}/{slug} round {n} (waiting for review)")
        return

    v = store.load_video(vdir)
    prev = store.latest_round(v)
    if v["status"] == "plan_waiting":
        die(f"{v['id']}: the edit plan hasn't been reviewed yet")
    if v["status"] == "plan_sent":  # first cut after the plan: take the real render's size and rate
        p = media.probe(render)
        v.update({"fps": media.snap_fps(p["fps"]), "width": p["width"], "height": p["height"],
                  "orientation": "vertical" if p["height"] > p["width"] else "horizontal"})
        store.save_json_atomic(vdir / "video.json", v)
    if v["status"] in ("waiting", "approved", "plan_sent"):  # a new cut with nothing to answer: back to the reviewer
        n = store.add_round(vdir, None)
        try:
            build_round(vdir, n, render, v["fps"])
        except Exception:
            _rollback(vdir, n, v["status"])
            raise
        store.rebuild_index(root)
        print(f"registered {v['id']} round {n} (waiting for review)")
        return
    if v["status"] != "sent":
        die(f"{v['id']} is '{v['status']}': wait for the reviewer to check the fixes first")
    if not a.fixes:
        die("fix rounds need --fixes FIXES.json answering every open note")
    fixes = json.loads(Path(a.fixes).read_text(encoding="utf-8"))
    need = open_notes(vdir, prev)
    answered = {x["note_id"] for x in fixes.get("answers", [])}
    missing = sorted(set(need) - answered)
    if missing:
        die("missing answers for notes: " + ", ".join(missing))

    n = store.add_round(vdir, fixes)
    fps = v["fps"]
    try:
        build_round(vdir, n, render, fps)
        fc = vdir / f"fixcheck-r{n}"
        index = {}
        for ans in fixes["answers"]:
            nt = need.get(ans["note_id"])
            if not nt:
                continue
            rng = (nt["start"], nt["end"])
            before = tuple(ans.get("before") or rng)
            after = tuple(ans.get("after") or rng)
            index[nt["id"]] = media.make_fixcheck(vdir / f"r{prev}.mp4", vdir / f"r{n}.mp4", fc, nt["id"], nt["tag"],
                                                  before, after, fps, v["orientation"], v.get("windows"))
        store.save_json_atomic(fc / "index.json", index)
    except Exception as e:
        _rollback(vdir, n, "sent")
        if isinstance(e, (ValueError, media.MediaError)):
            die(f"round not registered: {e}")
        raise
    store.rebuild_index(root)
    print(f"registered {v['id']} round {n} (fixes ready to check)")


def cmd_plan(a, root: Path) -> None:
    if not re.fullmatch(store.SAFE_NAME, a.project) or ".." in a.project:
        die(f"project folder name '{a.project}' must use only letters, digits, '-', '_' or '.'")
    spec = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    rows = []
    for i, r in enumerate(spec.get("rows") or []):
        start, end, text = float(r["start"]), float(r["end"]), str(r.get("text", "")).strip()
        if end <= start or not text:
            die(f"plan row {i + 1} needs start < end and text")
        still = Path(r["still"]) if r.get("still") else None
        if still and not still.is_file():
            die(f"plan row {i + 1}: still not found: {still}")
        rows.append({"id": f"p{i + 1}", "start": start, "end": end, "text": text, "_still": still})
    if not rows:
        die("the plan has no rows")
    slug = a.slug or store.unique_slug(root, a.project, store.slugify(a.title), a.title)
    if not re.fullmatch(store.SAFE_NAME, slug):
        die(f"slug '{slug}' must use only letters, digits, '-', '_' or '.'")
    vdir = store.video_dir(root, a.project, slug)
    if (vdir / "video.json").exists():
        v = store.load_video(vdir)
        if v["rounds"] or not v["status"].startswith("plan_"):
            die(f"{v['id']} already has a cut: plans come before the first cut")
    else:
        store.new_video(root, a.project, a.title, slug, str(spec.get("fps", "30")),
                        int(spec.get("width", 1080)), int(spec.get("height", 1920)))
    shutil.rmtree(vdir / "plan", ignore_errors=True)
    for r in rows:
        still = r.pop("_still")
        r["still"] = bool(still)
        if still:
            media.plan_still(still, vdir / "plan" / f"{r['id']}.jpg")
    store.set_plan(vdir, rows)
    store.rebuild_index(root)
    print(f"plan posted for {a.project}/{slug} ({len(rows)} rows, waiting for review)")


def cmd_claim(a, root: Path) -> None:
    vdir = vdir_for(root, a.id)
    v = store.load_video(vdir)
    if v["status"] == "plan_sent":
        try:
            store.claim_file(vdir / "plan" / "claim.json", datetime.now(timezone.utc))
        except store.ClaimTaken as e:
            print(f"already picked up at {datetime.fromisoformat(e.at).astimezone().strftime('%H:%M')}")
            sys.exit(3)
        store.rebuild_index(root)
        print(f"claimed {a.id} edit plan")
        return
    if v["status"] != "sent":
        die(f"nothing to claim: {a.id} is '{v['status']}'", 4)
    n = store.latest_round(v)
    try:
        store.claim(vdir, n, datetime.now(timezone.utc))
    except store.ClaimTaken as e:
        at = datetime.fromisoformat(e.at).astimezone().strftime("%H:%M")
        print(f"already picked up at {at}")
        sys.exit(3)
    store.rebuild_index(root)
    print(f"claimed {a.id} round {n}")


def cmd_show(a, root: Path) -> None:
    vdir = vdir_for(root, a.id)
    v = store.load_video(vdir)
    if v["status"] == "plan_sent":
        plan = store.read_json(vdir / "plan.json")
        print(f"{v['title']} ({v['id']}), edit plan v{plan['version']}")
        for r in plan["rows"]:
            verdict = plan["verdicts"].get(r["id"], "?")
            note = plan["notes"].get(r["id"], "")
            print(f"- {r['id']} {r['start']:.2f}-{r['end']:.2f}s [{verdict}] {r['text']}" + (f" -> {note}" if note else ""))
        if plan.get("note"):
            print(f"  overall: {plan['note']}")
        return
    sent = [r for r in v["rounds"] if r["sent_at"]]
    if not sent:
        die(f"{a.id} has no sent notes yet", 4)
    n = sent[-1]["n"]
    fps = float(Fraction(v["fps"]))
    data = store.round_notes(vdir, n)
    print(f"{v['title']} ({v['id']}), {store.round_label(n)}, review copy: {vdir / f'r{n}.mp4'} @ {v['fps']} fps")
    for nid, verdict in data.get("verdicts", {}).items():
        print(f"  verdict {nid}: {verdict}")
    for nt in data["notes"]:
        s, e = nt["start"], nt["end"]
        print(f"- [{nt['tag']}] {nt['id']}: frames {s}-{e} ({s / fps:.3f}s-{(e + 1) / fps:.3f}s): {nt['text']}")
        for fr in sorted({s, (s + e) // 2, e}):
            still = vdir / f"r{n}" / "stills" / f"frame-{fr}.jpg"
            if still.exists():
                print(f"    still: {still}")


def cmd_list(a, root: Path) -> None:
    for _, v in store.iter_videos(root):
        print(f"{v['id']}\t{v['status']}\t{store.round_label(store.latest_round(v))}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--project", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--render", required=True)
    r.add_argument("--slug")
    r.add_argument("--fixes")
    pl = sub.add_parser("plan")
    pl.add_argument("--project", required=True)
    pl.add_argument("--title", required=True)
    pl.add_argument("--plan", required=True)
    pl.add_argument("--slug")
    for name in ("claim", "show"):
        sub.add_parser(name).add_argument("id")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    root = review_root()
    {"register": cmd_register, "plan": cmd_plan, "claim": cmd_claim, "show": cmd_show, "list": cmd_list}[a.cmd](a, root)


if __name__ == "__main__":
    main()
