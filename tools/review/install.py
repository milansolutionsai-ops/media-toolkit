"""One-time setup: a "Video Review" Start-menu shortcut, plus the Claude Code hook block to paste.

Pinning to the taskbar is manual (Windows blocks scripts from pinning): Start menu, right-click
"Video Review", "Pin to taskbar". This script never edits Claude's settings itself.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def make_shortcut() -> Path:
    programs = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    lnk = programs / "Video Review.lnk"
    pyw = Path(sys.executable).with_name("pythonw.exe")
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
        "$s.TargetPath=$env:TGT;$s.Arguments='\"'+$env:ARG+'\"';$s.WorkingDirectory=$env:WD;"
        "$s.IconLocation=$env:ICO;$s.Description='Review videos frame by frame';$s.Save()"
    )
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    env = dict(os.environ, LNK=str(lnk), TGT=str(pyw if pyw.exists() else sys.executable),
               ARG=str(HERE / "launch.pyw"), WD=str(HERE),
               ICO=f"{edge},0" if os.path.exists(edge) else r"%SystemRoot%\System32\imageres.dll,18")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True)
    return lnk


def hook_block() -> dict:
    cmd = f'node "{(HERE / "hook" / "announce.mjs").as_posix()}"'
    return {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd, "timeout": 5}]}]}}


if __name__ == "__main__":
    print(f"Shortcut: {make_shortcut()}")
    print("Pin it: Start menu, right-click 'Video Review', 'Pin to taskbar'.")
    print("\nAdd this to ~/.claude/settings.json (merge into an existing 'hooks' key):")
    print(json.dumps(hook_block(), indent=2))
