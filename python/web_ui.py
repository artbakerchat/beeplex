"""Local button-driven interface for BeePlex."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
import hmac
import json
import secrets
import webbrowser

STATIC_ASSETS = {
    "/assets/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/assets/style.css": ("style.css", "text/css; charset=utf-8"),
}

ACTION_FUNCTIONS = {
    "status": "connection_status",
    "context": "get_context",
    "today": "get_context",
    "search": "search_memories",
    "browse": "fetch_conversations",
    "read": "read_conversation",
    "todos": "get_todos",
    "score": "score_conversations",
    "disagreements": "disagreement_view",
    "report": "generate_report",
    "diary": "bee_diary",
    "profile": "user_profile",
    "refresh_profile": "user_profile",
}


def perform_action(action, params):
    if action not in ACTION_FUNCTIONS:
        raise ValueError("Unknown BeePlex action.")
    if not isinstance(params, dict):
        raise ValueError("Action parameters must be an object.")

    from pydantic import validate_call

    from . import server

    function = getattr(server, ACTION_FUNCTIONS[action])
    return validate_call(function)(**params)


class LocalHTTPServer(HTTPServer):
    def __init__(self, address, token):
        super().__init__(address, RequestHandler)
        self.ui_token = token


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "BeePlexLocal/1.0"

    def log_message(self, format, *args):
        return

    def _send(self, status, body, content_type):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _json(self, status, payload):
        self._send(
            status,
            json.dumps(payload, ensure_ascii=True),
            "application/json; charset=utf-8",
        )

    def _is_local_request(self):
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        return self.client_address[0] in {"127.0.0.1", "::1"} and host in {
            "127.0.0.1",
            "localhost",
        }

    def do_GET(self):
        if not self._is_local_request():
            self._send(403, "Local access only.", "text/plain; charset=utf-8")
            return
        if self.path == "/":
            from .config import DEMO

            mode = "demo" if DEMO else "live"
            page = (
                files(__package__)
                .joinpath("web_ui_assets", "index.html")
                .read_text(encoding="utf-8")
                .replace("__TOKEN__", self.server.ui_token)
                .replace("__MODE__", mode)
            )
            self._send(200, page, "text/html; charset=utf-8")
            return

        asset = STATIC_ASSETS.get(self.path)
        if asset is None:
            self._send(404, "Not found.", "text/plain; charset=utf-8")
            return
        filename, content_type = asset
        content = (
            files(__package__)
            .joinpath("web_ui_assets", filename)
            .read_text(encoding="utf-8")
        )
        self._send(200, content, content_type)

    def do_POST(self):
        if not self._is_local_request():
            self._json(403, {"error": "Local access only."})
            return
        if self.path != "/api/action":
            self._json(404, {"error": "Not found."})
            return
        supplied_token = self.headers.get("X-BeePlex-Token", "")
        if not hmac.compare_digest(supplied_token, self.server.ui_token):
            self._json(403, {"error": "This page is no longer authorized. Reload it and try again."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                raise ValueError("Invalid request size.")
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError("Request must be a JSON object.")
            result = perform_action(request.get("action"), request.get("params", {}))
        except Exception as exc:
            from pydantic import ValidationError

            from .client import BeeError

            status = 400 if isinstance(exc, (ValueError, ValidationError, BeeError)) else 500
            message = str(exc) if status == 400 else "BeePlex could not complete that action."
            self._json(status, {"error": message})
            return
        self._json(200, result)


def serve(port=8765, open_browser=True):
    token = secrets.token_urlsafe(32)
    try:
        httpd = LocalHTTPServer(("127.0.0.1", port), token)
    except OSError:
        httpd = LocalHTTPServer(("127.0.0.1", 0), token)
    address, active_port = httpd.server_address
    url = f"http://{address}:{active_port}/"
    print(f"BeePlex local interface: {url}")
    print("Press Ctrl+C to stop the interface.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeePlex interface stopped.")
    finally:
        httpd.server_close()