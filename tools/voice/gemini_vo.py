"""Gemini 3.8 Flash TTS voiceover per scene (free tier key; paid ~$0.013/min audio if billing is on).

Reads GEMINI_TTS_API_KEY from the toolkit's .env.local (never prints it). Same layout as eleven_vo.py:
  audio/gemini/<voice>/sNN.wav and sample-<voice>.wav (all scenes joined). No word alignment from the API:
  get timings with `npx hyperframes transcribe <wav> --engine parakeet`.
Usage:
  python gemini_vo.py <project_dir> <voice> ["style direction"] [model]      (reads <project_dir>/VO_SCRIPT.md)
  python gemini_vo.py --text "one line" --out x.wav <voice> ["style"] [model]
Voices: Charon, Puck, Kore, Fenrir, Orus, Alnilam, Sadaltager, Achird, Algieba... (30 prebuilt). Language is
auto-detected (Spanish works). Sustained delivery (whispering, sarcastic, out of breath, warm and excited) goes in the
style string and applies to the whole line: split a line to change delivery mid-scene. The text is read verbatim.
Point-in-time tags go inline in the text: <short pause>, <long pause>, <laugh>, <sigh>, <cough>, <breath>.
"""
import base64, json, os, re, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
KEY = [l.split("=", 1)[1].strip() for l in open(os.path.join(ROOT, ".env.local")) if l.startswith("GEMINI_TTS_API_KEY=")][0]


def speak(text, voice, style="", model="gemini-3.8-flash-tts"):
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {"model": model, "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": voice}]}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions",
                                 data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
    for wait in (10, 30, 60, 0):  # free tier: a few requests per minute, so run scenes one at a time
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or not wait:
                raise
            time.sleep(wait)
    audio = [c for s in r["steps"] for c in s.get("content", []) if c.get("type") == "audio"]
    return base64.b64decode(audio[0]["data"])  # WAV, 24 kHz mono 16-bit


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--text":
        text, out, voice = a[1], a[3], a[4]
        data = speak(text, voice, *(a[5:7]))
        open(out, "wb").write(data)
        print(out, "ok")
        sys.exit()
    proj, voice, style = a[0], a[1], (a[2] if len(a) > 2 else "")
    model = a[3] if len(a) > 3 else "gemini-3.8-flash-tts"
    rows = [l for l in open(os.path.join(proj, "VO_SCRIPT.md"), encoding="utf-8") if re.match(r"\| \d\d ", l)]
    lines = [r.split("|")[2].strip() for r in rows]
    out = os.path.join(proj, "audio", "gemini", voice)
    os.makedirs(out, exist_ok=True)
    files = []
    for i, text in enumerate(lines):
        path = os.path.join(out, f"s{i + 1:02d}.wav")
        files.append(path)
        if not os.path.exists(path):  # never pay twice for the same scene
            data = speak(text, voice, style, model)
            open(path, "wb").write(data)
    lst = os.path.join(out, "concat.txt")
    with open(lst, "w") as f:
        for p in files:
            f.write(f"file '{p}'\n")
    sample = os.path.join(proj, "audio", "gemini", f"sample-{voice}.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-af", "apad=pad_dur=0.35", sample], check=True)
    print(voice, "ok", len(lines), "scenes")
