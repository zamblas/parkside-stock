"""Pré-visualização local: python server.py -> http://localhost:8765

Serve index.html e gera data.json ao vivo (mesmo formato que o build.py).
"""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import lidl

PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path in ("/", "/index.html"):
                return self.send(200, (lidl.HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/data.json":
                if "refresh" in u.query:
                    lidl.clear_cache()
                body = json.dumps(lidl.build_data(), ensure_ascii=False).encode()
                return self.send(200, body, "application/json; charset=utf-8")
            self.send(404, b"not found", "text/plain")
        except Exception as e:
            self.send(502, json.dumps({"error": str(e)}).encode(), "application/json")


if __name__ == "__main__":
    print(f"Parkside stock em http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
