"""Server: style round API and media."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import server  # noqa: E402
import style  # noqa: E402
from _fx import make_clip  # noqa: E402

P = "my-project"


class StyleServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / P).mkdir()
        clip = make_clip(self.root / "c.mp4", seconds=1)
        n = style.new_round(self.root, P, "Round one")
        style.add_candidate(self.root, P, n, clip, "Bold captions", "captions", "library", technique="bold")
        style.add_candidate(self.root, P, n, clip, "Whip", "transition", "claude", explain="my idea")
        self.srv = server.make_server(self.root, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def req(self, path, body=None):
        r = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                   data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_style_api_and_send(self):
        s, b = self.req(f"/api/style/{P}/1")
        self.assertEqual(s, 200)
        text = b.decode()
        self.assertNotIn("c-c1.mp4\"", text.replace("/c-c1.mp4", ""))
        self.assertNotIn("_style", text)
        d = json.loads(b)
        self.assertEqual([c["origin"] for c in d["candidates"]], ["library", "claude"])
        self.assertTrue(d["candidates"][0]["video_url"].startswith(f"/media/{P}/style-1/"))
        self.assertEqual(self.req(d["candidates"][0]["video_url"])[0], 200)
        s, _ = self.req(f"/api/style/{P}/1/send", {"reactions": {"c1": {"verdict": "keep"}}, "note": ""})
        self.assertEqual(s, 400)
        s, b = self.req(f"/api/style/{P}/1/send", {"reactions": {"c1": {"verdict": "keep"},
                                                                  "c2": {"verdict": "drop", "note": "no"}}, "note": "ok"})
        self.assertEqual((s, json.loads(b)["status"]), (200, "sent"))
        lst = json.loads(self.req("/api/videos")[1])
        self.assertEqual([v["kind"] for v in lst if v["id"] == f"{P}/style-1"], ["style"])

    def test_style_media_whitelist_404(self):
        for p in [f"/media/{P}/style-1/round.json", f"/media/{P}/style-1/../_review/x", f"/media/{P}/style-9/c-c1.mp4"]:
            self.assertEqual(self.req(p)[0], 404, p)


if __name__ == "__main__":
    unittest.main()
