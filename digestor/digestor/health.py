import json, logging, sqlite3, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

log = logging.getLogger(__name__)


def _make_handler(db_path: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthz":
                try:
                    conn = sqlite3.connect(db_path, timeout=2)
                    conn.execute("SELECT 1")
                    conn.close()
                    db_status = "ok"
                except Exception as e:
                    db_status = str(e)

                status = 200 if db_status == "ok" else 503
                body = json.dumps({"status": "ok" if status == 200 else "error", "db": db_status}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass  # silence access logs

    return Handler


def start_health_server(db_path: str, port: int = 8080) -> threading.Thread:
    server = HTTPServer(("0.0.0.0", port), _make_handler(db_path))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Health server on :%d", port)
    return t
