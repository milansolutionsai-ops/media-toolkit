"""Review data on disk: one folder per video under <project>/_review/<slug>/.

video.json holds the video and its rounds; notes-rN.json holds what Milan sent for round N;
fixes-rN.json holds Claude's answers that came with round N; rN/claim.json marks a picked-up round.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

CLAIM_STALE_HOURS = 4
SAFE_NAME = r"[A-Za-z0-9_.-]+"
INDEX_NAME = "_review-index.json"
DEFAULT_WINDOWS = {"picture_frames": 4, "sound_seconds": 2, "cut_seconds": 1}
STATUS_LABELS = {
    "waiting": "Waiting for you",
    "sent": "Notes sent",
    "fixes_ready": "Fixes ready to check",
    "approved": "Approved",
}


class ClaimTaken(Exception):
    def __init__(self, at: str):
        super().__init__(at)
        self.at = at


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60].strip("-") or "video"


def round_label(n: int) -> str:
    return "First cut" if n == 1 else f"Fix round {n - 1}"


def video_dir(root: Path, project: str, slug: str) -> Path:
    return Path(root) / project / "_review" / slug


def save_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_video(vdir: Path) -> dict:
    v = read_json(Path(vdir) / "video.json")
    if v is None:
        raise FileNotFoundError(f"no video.json in {vdir}")
    return v


def _save_video(vdir: Path, v: dict) -> None:
    v["updated"] = _now()
    save_json_atomic(Path(vdir) / "video.json", v)


def new_video(root: Path, project: str, title: str, slug: str, fps: str, width: int, height: int) -> dict:
    vdir = video_dir(root, project, slug)
    v = {
        "id": f"{project}/{slug}",
        "title": title,
        "project": project,
        "slug": slug,
        "fps": fps,
        "width": width,
        "height": height,
        "orientation": "vertical" if height > width else "horizontal",
        "status": "waiting",
        "rounds": [],
        "windows": dict(DEFAULT_WINDOWS),
        "created": _now(),
    }
    _save_video(vdir, v)
    return v


def add_round(vdir: Path, fixes: dict | None) -> int:
    vdir = Path(vdir)
    v = load_video(vdir)
    n = len(v["rounds"]) + 1
    if (vdir / f"r{n}.mp4").exists() or (vdir / f"fixes-r{n}.json").exists():
        raise FileExistsError(f"round {n} slot already used")  # review files are write-once
    if fixes is not None:
        save_json_atomic(vdir / f"fixes-r{n}.json", fixes)
    v["rounds"].append({"n": n, "created": _now(), "sent_at": None, "has_fixes": fixes is not None})
    v["status"] = "fixes_ready" if fixes is not None else "waiting"
    _save_video(vdir, v)
    return n


def apply_send(vdir: Path, round_n: int, notes: list[dict], verdicts: dict[str, str]) -> str:
    vdir = Path(vdir)
    v = load_video(vdir)
    save_json_atomic(vdir / f"notes-r{round_n}.json",
                     {"round": round_n, "notes": notes, "verdicts": verdicts, "sent_at": _now()})
    all_fixed = all(val == "fixed" for val in verdicts.values())
    status = "approved" if (not notes and all_fixed) else "sent"
    for r in v["rounds"]:
        if r["n"] == round_n:
            r["sent_at"] = _now()
    v["status"] = status
    _save_video(vdir, v)
    return status


def claim(vdir: Path, round_n: int, now: datetime) -> dict:
    path = Path(vdir) / f"r{round_n}" / "claim.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"at": now.isoformat()}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        old = read_json(path, {}) or {}
        at = old.get("at")
        try:
            age_h = (now - datetime.fromisoformat(at)).total_seconds() / 3600
        except (TypeError, ValueError):
            age_h = CLAIM_STALE_HOURS + 1
        if age_h < CLAIM_STALE_HOURS:
            raise ClaimTaken(at)
        save_json_atomic(path, data)
        return data
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def latest_round(v: dict) -> int:
    return v["rounds"][-1]["n"] if v["rounds"] else 0


def round_notes(vdir: Path, n: int) -> dict:
    return read_json(Path(vdir) / f"notes-r{n}.json", {"round": n, "notes": [], "verdicts": {}})


def feedback_count(notes: dict) -> int:
    """What Claude has to act on in a sent round: new notes plus fixes marked not-fixed."""
    return len(notes.get("notes", [])) + sum(1 for s in notes.get("verdicts", {}).values() if s == "not-fixed")


def iter_videos(root: Path):
    for vj in sorted(Path(root).glob("*/_review/*/video.json")):
        v = read_json(vj)
        if v:
            yield vj.parent, v


def rebuild_index(root: Path) -> None:
    root = Path(root)
    out = []
    for vdir, v in iter_videos(root):
        n = latest_round(v)
        notes = round_notes(vdir, n) if n else {"notes": [], "verdicts": {}}
        c = read_json(vdir / f"r{n}" / "claim.json") if n else None
        out.append({
            "id": v["id"],
            "title": v["title"],
            "project": v["project"],
            "status": v["status"],
            "round": n,
            "round_label": round_label(n) if n else "",
            "notes_count": feedback_count(notes),
            "sent_at": v["rounds"][-1]["sent_at"] if n else None,
            "claimed_at": (c or {}).get("at"),
            "folder": vdir.relative_to(root).as_posix(),
        })
    save_json_atomic(root / INDEX_NAME, {"updated": _now(), "videos": out})
