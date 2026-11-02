"""ElevenLabs voiceover per scene, with word-level alignment.

Reads the key from .env.local (never prints it). One request per scene,
with previous/next text for natural flow. Writes, per voice:
  audio/elevenlabs/<voice>/sNN.mp3 + sNN.align.json, and sample-<voice>.mp3 (all scenes joined).
Usage: python eleven_vo.py <project_dir> <voice_name> <voice_id> [model]
"""
import base64, json, os, re, subprocess, sys, urllib.request

proj, vname, vid = sys.argv[1], sys.argv[2], sys.argv[3]
model = sys.argv[4] if len(sys.argv) > 4 else "eleven_multilingual_v2"
env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env.local")
key = [l.split("=", 1)[1].strip() for l in open(env) if l.startswith("ELEVENLABS_API_KEY=")][0]

rows = [l for l in open(os.path.join(proj, "VO_SCRIPT.md"), encoding="utf-8") if re.match(r"\| \d\d ", l)]
lines = [r.split("|")[2].strip() for r in rows]
out = os.path.join(proj, "audio", "elevenlabs", vname)
os.makedirs(out, exist_ok=True)

files = []
for i, text in enumerate(lines):
    path = os.path.join(out, f"s{i+1:02d}.mp3")
    files.append(path)
    if os.path.exists(path):
        continue  # never pay twice for the same scene
    body = {
        "text": text, "model_id": model,
        "previous_text": " ".join(lines[max(0, i-2):i]) or None,
        "next_text": " ".join(lines[i+1:i+3]) or None,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.15, "use_speaker_boost": True, "speed": float(os.environ.get("EL_SPEED", "1.0"))},
    }
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps?output_format=mp3_44100_128",
        data=json.dumps(body).encode(), headers={"xi-api-key": key, "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req))
    open(path, "wb").write(base64.b64decode(r["audio_base64"]))
    json.dump(r.get("alignment"), open(path.replace(".mp3", ".align.json"), "w"))

lst = os.path.join(out, "concat.txt")
gap = os.path.join(out, "gap.mp3")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.35", "-b:a", "128k", gap], check=True)
with open(lst, "w") as f:
    for p in files:
        f.write(f"file '{p}'\nfile '{gap}'\n")
sample = os.path.join(proj, "audio", "elevenlabs", f"sample-{vname}.mp3")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ac", "1", "-b:a", "128k", sample], check=True)
print(vname, "ok", sum(len(t) for t in lines), "chars")
