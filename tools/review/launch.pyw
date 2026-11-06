"""Open Video Review: start the server silently if it isn't running, then open it as an app window."""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 47615
URL = f"http://127.0.0.1:{PORT}/"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def is_up(port: int = PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as r:
            return r.status == 200
    except OSError:
        return False


def start_server() -> None:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    subprocess.Popen([exe, str(HERE / "server.py")], cwd=str(HERE), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if is_up():
            return
        time.sleep(0.1)


def open_window() -> None:
    for b in BROWSERS:
        if os.path.exists(b):
            subprocess.Popen([b, f"--app={URL}", "--window-size=1440,960"])
            return
    webbrowser.open(URL)


if __name__ == "__main__":
    if not is_up():
        start_server()
    open_window()
