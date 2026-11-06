"""One-time setup on Windows.

1. Starts the review server with Windows (a hidden "Video Review server" entry in the Startup folder) and starts it
   now, so the app is always reachable.
2. Opens the app in Edge. Install it from there (Edge menu > Apps > Install this site as an app, tick
   "Pin to taskbar"): Edge gives the installed app its own window, taskbar button and icon. Pinning a plain
   browser window instead pins Edge itself.
3. Prints the Claude Code hook block for ~/.claude/settings.json (this script never edits Claude settings).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import launch  # noqa: E402

START_MENU = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def make_shortcut(lnk: Path, script: Path, description: str) -> Path:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
        "$s.TargetPath=$env:TGT;$s.Arguments='\"'+$env:ARG+'\"';$s.WorkingDirectory=$env:WD;"
        "$s.IconLocation=$env:ICO;$s.Description=$env:DESC;$s.WindowStyle=7;$s.Save()"
    )
    env = dict(os.environ, LNK=str(lnk), TGT=str(pyw if pyw.exists() else sys.executable), ARG=str(script),
               WD=str(HERE), ICO=f"{HERE / 'icon.ico'},0", DESC=description)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True)
    return lnk


def hook_block() -> dict:
    cmd = f'node "{(HERE / "hook" / "announce.mjs").as_posix()}"'
    return {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd, "timeout": 5}]}]}}


if __name__ == "__main__":
    startup = START_MENU / "Startup" / "Video Review server.lnk"
    print(f"Autostart: {make_shortcut(startup, HERE / 'server.py', 'Video Review server (hidden)')}")
    old = START_MENU / "Video Review.lnk"  # earlier versions pinned a launcher, which Windows shows as Edge
    if old.exists():
        old.unlink()
        print(f"Removed old launcher shortcut: {old}")
    if not launch.is_up():
        launch.start_server()
    edge = next((b for b in launch.BROWSERS if "msedge" in b and os.path.exists(b)), None)
    subprocess.Popen([edge, launch.URL] if edge else ["cmd", "/c", "start", launch.URL])
    print("In Edge: menu (...) > Apps > Install this site as an app > tick 'Pin to taskbar'.")
    print("\nHook block for ~/.claude/settings.json (merge into an existing 'hooks' key):")
    print(json.dumps(hook_block(), indent=2))
