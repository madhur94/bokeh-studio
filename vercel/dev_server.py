"""Local test server. Production is served by Vercel's static CDN and Python runtime."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
from api.process import handler


class LocalHandler(handler, SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/process"):
            return handler.do_GET(self)
        return SimpleHTTPRequestHandler.do_GET(self)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).resolve().parent / "public"), **kwargs)


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    print("Bokeh Studio: http://127.0.0.1:8503", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8503), LocalHandler).serve_forever()
