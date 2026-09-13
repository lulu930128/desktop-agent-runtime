"""Loopback-only schedule API. Token comes from the parent environment, never argv."""
from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .schedule_contract import ScheduleConflict, prepare_item, zone, day
from .schedule_notifications import ScheduleNotifications
from .schedule_store import ScheduleStore
from .storage import KuroCoreStore, SCHEMA_VERSION

LOG = logging.getLogger(__name__)
MAX_BYTES = 65536


class ExclusiveServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class ScheduleServer:
    def __init__(self, db_path, *, port, token, instance_id, host="127.0.0.1", default_timezone="UTC"):
        if host != "127.0.0.1" or type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Core requires IPv4 loopback and a valid port")
        if not isinstance(token, str) or len(token) < 32 or not instance_id:
            raise ValueError("Session token and instance identity required")
        self.store = ScheduleStore(db_path)
        self.timezone = str(zone(default_timezone))
        self.notifications = ScheduleNotifications(self.store,self.timezone)
        self.token, self.instance_id = token, instance_id
        self.stop_event = threading.Event()
        self.thread = self.worker = None
        self.materialization = "pending"
        self.notification_status = "pending"
        self._lease = None
        self.server = ExclusiveServer((host, port), self._handler())
        self.server.daemon_threads = False
        self.server.block_on_close = True
        try:
            lock_path = Path(str(self.store.path) + ".service.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._lease = lock_path.open("a+b")
            if lock_path.stat().st_size == 0:
                self._lease.write(b"0")
                self._lease.flush()
            self._lease.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            KuroCoreStore(db_path).initialize()
        except Exception:
            if self._lease:
                self._lease.close()
            self.server.server_close()
            raise

    @property
    def port(self):
        return self.server.server_address[1]

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.worker = threading.Thread(target=self._materialize, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.server.shutdown()
            self.thread.join(timeout=5)
        self.server.server_close()
        if self.worker:
            self.worker.join(timeout=12)
            if self.worker.is_alive():
                raise RuntimeError("Materialization did not stop; retain the database lease")
        if self._lease:
            self._lease.close()
            self._lease = None

    def _materialize(self):
        while not self.stop_event.is_set():
            try:
                horizon = (datetime.now(timezone.utc).date()+timedelta(days=10)).isoformat()
                result = self.store.advance(horizon)
                self.materialization = "complete" if result["complete"] else "incomplete"
                self.notifications.tick()
                self.notification_status = "running"
            except Exception:
                self.materialization = "failed"
                self.notification_status = "failed"
                LOG.exception("Core schedule materialization failed")
            self.stop_event.wait(5)

    def _handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *args):
                pass  # Never log URLs, request bodies or authentication headers.

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
                if self.headers.get("Origin") or not secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {owner.token}"):
                    self.send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                try:
                    parsed = urlsplit(self.path)
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if any(len(values) != 1 for values in query.values()):
                        raise ValueError("Repeated query fields")
                    if self.command == "GET":
                        if parsed.path == "/status":
                            result = {"service": "kuro-core", "contract": "kuro.core.schedule.v1", "schema": SCHEMA_VERSION,
                                      "instanceId": owner.instance_id, "pid": os.getpid(),
                                      "sourceRoot": str(Path(__file__).resolve().parents[1]),
                                      "materialization": owner.materialization, "notificationScheduler": owner.notification_status,
                                      "timezone":owner.timezone,"today":datetime.now(zone(owner.timezone)).date().isoformat()}
                        elif parsed.path == "/v1/schedule/notifications":
                            result = owner.notifications.read()
                        elif parsed.path == "/v1/schedule/view":
                            if set(query)-{"start", "end", "timezone", "limit", "offset"}:
                                raise ValueError("Unknown view fields")
                            start_date = query.get("start", [datetime.now(zone(owner.timezone)).date().isoformat()])[0]
                            result = owner.store.view(start_date, query.get("end", [(day(start_date)+timedelta(days=1)).isoformat()])[0], query.get("timezone", [owner.timezone])[0],
                                                      limit=int(query.get("limit", ["200"])[0]), offset=int(query.get("offset", ["0"])[0]))
                        elif parsed.path == "/v1/schedule/item" and set(query) == {"id"}:
                            result = owner.store.get(query["id"][0])
                        else:
                            raise LookupError("Unknown route")
                    else:
                        if parsed.query or self.headers.get("Transfer-Encoding") or self.headers.get_content_type() != "application/json":
                            raise ValueError("JSON body required; query/transfer encoding not supported")
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= MAX_BYTES:
                            raise ValueError("Body must be between 1 and 65536 bytes")
                        raw = self.rfile.read(length)
                        if len(raw) != length:
                            raise ValueError("Incomplete body")
                        payload = json.loads(raw.decode("utf-8"))
                        if not isinstance(payload, dict):
                            raise ValueError("JSON object required")
                        if parsed.path == "/v1/schedule/mutate":
                            result = owner.store.mutate(payload)
                            try:
                                owner.store.advance((datetime.now(timezone.utc).date()+timedelta(days=10)).isoformat())
                                owner.notifications.tick()
                            except Exception:
                                owner.materialization = "failed"
                                owner.notification_status = "failed"
                                result = {**result, "projection": "pending"}
                                LOG.exception("Schedule saved; projection retry pending")
                        elif parsed.path == "/v1/schedule/prepare" and set(payload)=={"item"}:
                            result = {"item":prepare_item(payload["item"])}
                        elif parsed.path == "/v1/schedule/notification-action":
                            result = owner.notifications.action(payload)
                            owner.notifications.tick()
                        elif parsed.path == "/v1/schedule/materialize":
                            if set(payload) != {"through"}:
                                raise ValueError("through required")
                            # An explicit local command, never an effect of GET.
                            if day(payload["through"]) > datetime.now(timezone.utc).date()+timedelta(days=367):
                                raise ValueError("Materialization horizon exceeds one year")
                            result = owner.store.advance(payload["through"])
                        elif parsed.path == "/shutdown" and payload == {}:
                            owner.stop_event.set()
                            result = {"stopping": True}
                        else:
                            raise LookupError("Unknown route")
                    self.send_json(200, {"ok": True, **result})
                except ScheduleConflict as exc:
                    self.send_json(409, {"ok": False, "error": "conflict", "message": str(exc)})
                except PermissionError:
                    self.send_json(403, {"ok": False, "error": "confirmation_required"})
                except LookupError:
                    self.send_json(404, {"ok": False, "error": "not_found"})
                except (ValueError, TypeError, OverflowError) as exc:
                    self.send_json(400, {"ok": False, "error": "invalid_request", "message": str(exc)})
                except Exception:
                    LOG.exception("Core schedule request failed")
                    self.send_json(503, {"ok": False, "error": "core_unavailable"})

            do_GET = dispatch
            do_POST = dispatch
        return Handler
