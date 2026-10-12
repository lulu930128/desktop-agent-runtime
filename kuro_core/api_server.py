"""Domain-neutral loopback HTTP transport; capabilities register explicit routes."""
from __future__ import annotations

import json
import logging
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

LOG = logging.getLogger(__name__)
MAX_BYTES = 65536


class ApiConflict(Exception):
    """A capability rejected a conflicting command."""


class ExclusiveServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CoreApiServer:
    def __init__(self, *, port, token, host="127.0.0.1"):
        if host != "127.0.0.1" or type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Core requires IPv4 loopback and a valid port")
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("Session token required")
        self.token = token
        self.routes = {}
        self.thread = None
        self.server = ExclusiveServer((host, port), self._handler())
        self.server.daemon_threads = False
        self.server.block_on_close = True

    @property
    def port(self):
        return self.server.server_address[1]

    def register(self, method, path, handler):
        if self.thread or method not in {"GET", "POST"} or (method, path) in self.routes:
            raise ValueError("Routes must be unique and registered before serving")
        self.routes[method, path] = handler

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread:
            self.server.shutdown()
            self.thread.join(timeout=5)
        # Drain request handlers before the capability releases its database lease.
        self.server.server_close()

    def _handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *args):
                pass  # Never log URLs, bodies or authentication headers.

            def send_json(self, code, payload):
                body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def dispatch(self):
                auth = self.headers.get_all("Authorization", [])
                if "Origin" in self.headers or len(auth) != 1 or not secrets.compare_digest(
                    auth[0].encode("utf-8"), f"Bearer {owner.token}".encode("utf-8")
                ):
                    self.send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                try:
                    parsed = urlsplit(self.path)
                    query = (
                        parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                        if parsed.query
                        else {}
                    )
                    if any(len(values) != 1 for values in query.values()):
                        raise ValueError("Repeated query fields")
                    if self.command == "GET":
                        argument = {key: values[0] for key, values in query.items()}
                    else:
                        if parsed.query or "Transfer-Encoding" in self.headers or self.headers.get_content_type() != "application/json":
                            raise ValueError("JSON body required; query/transfer encoding not supported")
                        lengths = self.headers.get_all("Content-Length", [])
                        if len(lengths) != 1:
                            raise ValueError("One Content-Length required")
                        length = int(lengths[0])
                        if not 0 < length <= MAX_BYTES:
                            raise ValueError("Body must be between 1 and 65536 bytes")
                        raw = self.rfile.read(length)
                        if len(raw) != length:
                            raise ValueError("Incomplete body")
                        argument = json.loads(raw.decode("utf-8"))
                        if not isinstance(argument, dict):
                            raise ValueError("JSON object required")
                    handler = owner.routes.get((self.command, parsed.path))
                    if handler is None:
                        raise LookupError("Unknown route")
                    self.send_json(200, {"ok": True, **handler(argument)})
                except ApiConflict as exc:
                    self.send_json(409, {"ok": False, "error": "conflict", "message": str(exc)})
                except PermissionError:
                    self.send_json(403, {"ok": False, "error": "confirmation_required"})
                except LookupError:
                    self.send_json(404, {"ok": False, "error": "not_found"})
                except (ValueError, TypeError, OverflowError) as exc:
                    self.send_json(400, {"ok": False, "error": "invalid_request", "message": str(exc)})
                except Exception:
                    # Do not expose capability paths or payloads through transport diagnostics.
                    LOG.error("Core API request failed")
                    self.send_json(503, {"ok": False, "error": "core_unavailable"})

            do_GET = dispatch
            do_POST = dispatch
        return Handler
