"""ElevenLabs sound generation: prompt-to-SFX, a whole kit in one run.

Paid from ElevenLabs plan credits. Adapted from nateherkai/herk-edit-kit,
.claude/skills/motion-showreel/scripts/sfx.mjs (MIT, Copyright (c) Nate Herk).
Key: ELEVENLABS_API_KEY in .env.local (the same one tools/voice/eleven_vo.py uses).

  python tools/paid/eleven_sfx.py kit.json sfx/ --go
  kit.json: {"whoosh_big": ["deep airy whoosh, fast, cinematic", 1.2], "dot_pop": ["tiny rubbery pop, clean", 0.5]}

Durations 0.5-30 s. Existing files are skipped, so a rerun only pays for what's new.
Free first: tools/audio/make_sfx.py (generated) and tools/audio/openverse_sfx.py (real CC0 recordings).
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _paid import UA, gate, key  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kit")
    ap.add_argument("out")
    ap.add_argument("--go", action="store_true", help="actually spend credits")
    a = ap.parse_args()

    out = Path(a.out)
    todo = {n: v for n, v in json.loads(Path(a.kit).read_text(encoding="utf-8")).items() if not (out / f"{n}.mp3").exists()}
    if not todo:
        sys.exit("every sound in the kit already exists")
    gate(a.go, f"ElevenLabs SFX x{len(todo)}: {', '.join(todo)}")
    k = key("ELEVENLABS_API_KEY")
    out.mkdir(parents=True, exist_ok=True)
    for name, (text, seconds) in todo.items():
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/sound-generation",
            data=json.dumps({"text": text, "duration_seconds": min(30, max(0.5, seconds)), "prompt_influence": 0.6}).encode(),
            headers={"xi-api-key": k, "Content-Type": "application/json", "User-Agent": UA})
        try:
            (out / f"{name}.mp3").write_bytes(urllib.request.urlopen(req, timeout=120).read())
            print(name, "saved")
        except urllib.error.HTTPError as e:
            print(name, "ERROR", e.code, e.read()[:200].decode(errors="replace"))


if __name__ == "__main__":
    main()
