"""Launcher: detects whether the server is up."""
import importlib.util
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import server  # noqa: E402

spec = importlib.util.spec_from_file_location("launch", HERE.parent / "launch.pyw")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class LaunchTest(unittest.TestCase):
    def test_is_up_false_on_unused_port(self):
        self.assertFalse(launch.is_up(free_port()))

    def test_is_up_true_against_server(self):
        with tempfile.TemporaryDirectory() as d:
            srv = server.make_server(Path(d), 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                self.assertTrue(launch.is_up(srv.server_address[1]))
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
