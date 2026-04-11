import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from emailtunnel import logger
except ImportError:
    logger = logging.getLogger(__name__)


def create_control_server(forwarder, token, host, port):
    class ControlHandler(BaseHTTPRequestHandler):
        server_version = "DatmailControl/1.0"

        def do_POST(self):
            if self.path != "/control/resend":
                self.send_error(404)
                return

            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_error(401)
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length))
                forwarder.resend_archived_mail(
                    request_uuid=payload["request_uuid"],
                    target=payload["target"],
                    sender=payload["sender"],
                    original_target=payload["original_target"],
                )
            except (KeyError, ValueError, TypeError):
                self.send_error(400)
                return
            except Exception:
                logger.exception("Failed to resend archived mail")
                self.send_error(502)
                return

            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "queued"}).encode("utf-8"))

        def log_message(self, format, *args):
            return

    return ThreadingHTTPServer((host, port), ControlHandler)
