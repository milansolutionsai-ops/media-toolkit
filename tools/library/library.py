"""Technique library: what we've seen in reference videos and how to make it with our tools.

Data lives in <root>/library/ (private workspace, root = env REVIEW_ROOT or the folder containing media-toolkit):
  references.json   videos someone liked: url, platform, creator, notes, technique ids
  techniques.json   one entry per technique: what, recipe, when it works/fails, status (have|partial|missing),
                    tool, cost, seen_in (reference ids), brands ({brand: keep|maybe|drop})
  LIBRARY.md        rendered overview, grouped by status

  library.py add-ref URL --platform P --creator C [--notes N]
  library.py add-tech NAME --what W --recipe R --status have|partial|missing [--tool T] [--cost C]
                      [--works-when X] [--fails-when Y] [--ref REF_ID]
  library.py link REF_ID TECH_ID
  library.py verdict TECH_ID BRAND keep|maybe|drop
  library.py update TECH_ID [--status S] [--recipe R] [--tool T] ...
  library.py find TEXT
  library.py render
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

STATUSES = ("have", "partial", "missing")
VERDICTS = ("keep", "maybe", "drop")


def library_root() -> Path:
    env = os.environ.get("REVIEW_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[3]


def _dir(root: Path) -> Path:
    d = Path(root) / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(root: Path, name: str) -> list:
    try:
        return json.loads((_dir(root) / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def _save(root: Path, name: str, data: list) -> None:
    p = _dir(root) / name
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "item"


TRACKING = ("utm_", "igsh", "si", "fbclid", "gclid", "feature", "pp", "t", "ref", "s")


def normalise_url(url: str) -> str:
    """Same video = same key: lower-case host without www, no trailing slash, tracking params dropped,
    id-carrying params (YouTube's v=, etc.) kept and sorted."""
    u = urlsplit(url.strip())
    host = u.netloc.lower().removeprefix("www.").removeprefix("m.")
    keep = sorted((k, v) for k, v in parse_qsl(u.query) if not any(k == t or k.startswith(t) for t in TRACKING))
    return f"{host}{u.path.rstrip('/')}" + (f"?{urlencode(keep)}" if keep else "")


def add_reference(root: Path, url: str, platform: str, creator: str, notes: str = "") -> dict:
    refs = _load(root, "references.json")
    key = normalise_url(url)
    for r in refs:
        if normalise_url(r["url"]) == key:
            if notes and notes not in r["notes"]:
                r["notes"] = (r["notes"] + "\n" + notes).strip()
                _save(root, "references.json", refs)
            return r
    r = {"id": "r-" + hashlib.sha1(key.encode()).hexdigest()[:8], "url": url.strip(), "platform": platform,
         "creator": creator, "added": date.today().isoformat(), "notes": notes, "techniques": []}
    refs.append(r)
    _save(root, "references.json", refs)
    return r


def add_technique(root: Path, name: str, what: str, recipe: str, status: str, tool: str = "", cost: str = "",
                  works_when: str = "", fails_when: str = "", ref_id: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if ref_id and not any(r["id"] == ref_id for r in _load(root, "references.json")):
        raise KeyError(f"unknown reference {ref_id}")
    techs = _load(root, "techniques.json")
    tid = slug(name)
    t = next((x for x in techs if x["id"] == tid), None)
    if t is None:
        t = {"id": tid, "name": name, "what": what, "recipe": recipe, "works_when": works_when,
             "fails_when": fails_when, "status": status, "tool": tool, "cost": cost, "seen_in": [], "brands": {}}
        techs.append(t)
    _save(root, "techniques.json", techs)
    if ref_id:
        link(root, ref_id, tid)
        t = next(x for x in _load(root, "techniques.json") if x["id"] == tid)
    return t


UPDATABLE = ("name", "what", "recipe", "works_when", "fails_when", "status", "tool", "cost")


def update_technique(root: Path, technique_id: str, **fields) -> dict:
    """Change an entry's fields (e.g. status missing -> have once the tool exists). Empty values are ignored."""
    if fields.get("status") and fields["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    techs = _load(root, "techniques.json")
    t = next((x for x in techs if x["id"] == technique_id), None)
    if t is None:
        raise KeyError(f"unknown technique {technique_id}")
    t.update({k: v for k, v in fields.items() if k in UPDATABLE and v})
    _save(root, "techniques.json", techs)
    return t


def link(root: Path, ref_id: str, technique_id: str) -> None:
    refs, techs = _load(root, "references.json"), _load(root, "techniques.json")
    r = next((x for x in refs if x["id"] == ref_id), None)
    t = next((x for x in techs if x["id"] == technique_id), None)
    if r is None or t is None:
        raise KeyError(f"unknown {'reference ' + ref_id if r is None else 'technique ' + technique_id}")
    if technique_id not in r["techniques"]:
        r["techniques"].append(technique_id)
    if ref_id not in t["seen_in"]:
        t["seen_in"].append(ref_id)
    _save(root, "references.json", refs)
    _save(root, "techniques.json", techs)


def set_brand_verdict(root: Path, technique_id: str, brand: str, verdict: str) -> None:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    techs = _load(root, "techniques.json")
    t = next((x for x in techs if x["id"] == technique_id), None)
    if t is None:
        raise KeyError(f"unknown technique {technique_id}")
    t["brands"][brand] = verdict
    _save(root, "techniques.json", techs)


def find(root: Path, text: str) -> list[dict]:
    q = text.lower()
    return [t for t in _load(root, "techniques.json")
            if q in " ".join([t["name"], t["what"], t["recipe"]]).lower()]


def render(root: Path) -> Path:
    techs, refs = _load(root, "techniques.json"), {r["id"]: r for r in _load(root, "references.json")}
    out = ["# Technique library", "", f"{len(techs)} techniques from {len(refs)} references. Generated; edit with library.py.", ""]
    for status, head in (("have", "Have"), ("partial", "Partial"), ("missing", "Missing")):
        out += [f"## {head}", ""]
        for t in sorted((t for t in techs if t["status"] == status), key=lambda t: t["name"].lower()):
            out.append(f"### {t['name']}")
            out.append(t["what"])
            out.append(f"- Recipe: {t['recipe']}")
            for label, key in (("Tool", "tool"), ("Cost", "cost"), ("Works when", "works_when"), ("Fails when", "fails_when")):
                if t.get(key):
                    out.append(f"- {label}: {t[key]}")
            if t["brands"]:
                out.append("- Brands: " + ", ".join(f"{b} {v}" for b, v in sorted(t["brands"].items())))
            if t["seen_in"]:
                out.append("- Seen in: " + ", ".join(refs[r]["url"] for r in t["seen_in"] if r in refs))
            out.append("")
    p = _dir(root) / "LIBRARY.md"
    p.write_text("\n".join(out), encoding="utf-8")
    return p


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-ref"); a.add_argument("url"); a.add_argument("--platform", required=True)
    a.add_argument("--creator", required=True); a.add_argument("--notes", default="")
    t = sub.add_parser("add-tech"); t.add_argument("name")
    for f in ("what", "recipe"):
        t.add_argument(f"--{f}", required=True)
    t.add_argument("--status", required=True, choices=STATUSES)
    for f in ("tool", "cost", "works-when", "fails-when", "ref"):
        t.add_argument(f"--{f}", default="")
    ln = sub.add_parser("link"); ln.add_argument("ref_id"); ln.add_argument("tech_id")
    v = sub.add_parser("verdict"); v.add_argument("tech_id"); v.add_argument("brand"); v.add_argument("verdict", choices=VERDICTS)
    up = sub.add_parser("update"); up.add_argument("tech_id")
    for f in UPDATABLE:
        up.add_argument(f"--{f.replace('_', '-')}", default="", **({"choices": STATUSES} if f == "status" else {}))
    fd = sub.add_parser("find"); fd.add_argument("text")
    sub.add_parser("render")
    args = ap.parse_args(argv)
    root = library_root()
    try:
        _run(args, root)
    except (KeyError, ValueError) as e:
        print(str(e).strip("'\""), file=sys.stderr)
        return 2
    return 0


def _run(args, root: Path) -> None:
    if args.cmd == "update":
        print(json.dumps(update_technique(root, args.tech_id, **{f: getattr(args, f) for f in UPDATABLE})))
    elif args.cmd == "add-ref":
        print(json.dumps(add_reference(root, args.url, args.platform, args.creator, args.notes)))
    elif args.cmd == "add-tech":
        print(json.dumps(add_technique(root, args.name, args.what, args.recipe, args.status, args.tool, args.cost,
                                       args.works_when, args.fails_when, args.ref or None)))
    elif args.cmd == "link":
        link(root, args.ref_id, args.tech_id)
    elif args.cmd == "verdict":
        set_brand_verdict(root, args.tech_id, args.brand, args.verdict)
    elif args.cmd == "find":
        for x in find(root, args.text):
            print(f"{x['id']}\t{x['status']}\t{x['what']}")
    else:
        print(render(root))
    if args.cmd not in ("render", "find"):
        render(root)


if __name__ == "__main__":
    sys.exit(main())
