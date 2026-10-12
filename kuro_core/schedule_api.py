"""Schedule capability: persistence lease, worker and Schedule-only routes."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .api_server import ApiConflict
from .schedule_contract import ScheduleConflict, prepare_item, zone, day
from .schedule_notifications import ScheduleNotifications
from .schedule_store import ScheduleStore
from .storage import KuroCoreStore, SCHEMA_VERSION

LOG = logging.getLogger(__name__)


class ScheduleCapability:
    def __init__(self, db_path, *, default_timezone="UTC"):
        self.store = ScheduleStore(db_path)
        self.timezone = str(zone(default_timezone))
        self.notifications = ScheduleNotifications(self.store, self.timezone)
        self.stop_event = threading.Event()
        self.worker = None
        self.materialization = "pending"
        self.notification_status = "pending"
        self._lease = None
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
            raise

    def start(self):
        if self.worker:
            return
        self.worker = threading.Thread(target=self._materialize, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
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

    def status(self):
        return {"contract": "kuro.core.schedule.v1", "schema": SCHEMA_VERSION,
                "materialization": self.materialization,
                "notificationScheduler": self.notification_status,
                "timezone": self.timezone,
                "today": datetime.now(zone(self.timezone)).date().isoformat()}

    def register_routes(self, api):
        for route, handler in {
            "notifications": lambda query: self.notifications.read(),
            "view": self._view,
            "item": self._item,
        }.items():
            api.register("GET", f"/v1/schedule/{route}", handler)
        for route, handler in {
            "mutate": self._mutate,
            "prepare": self._prepare,
            "notification-action": self._notification_action,
            "notification-command": self._notification_command,
            "materialize": self._advance,
        }.items():
            api.register("POST", f"/v1/schedule/{route}", handler)

    def _view(self, query):
        if set(query)-{"start", "end", "timezone", "limit", "offset"}:
            raise ValueError("Unknown view fields")
        start_date = query.get("start", datetime.now(zone(self.timezone)).date().isoformat())
        return self.store.view(start_date, query.get("end", (day(start_date)+timedelta(days=1)).isoformat()),
                               query.get("timezone", self.timezone),
                               limit=int(query.get("limit", "200")), offset=int(query.get("offset", "0")))

    def _item(self, query):
        if set(query) != {"id"}:
            raise LookupError("Unknown route")
        return self.store.get(query["id"])

    def _mutate(self, payload):
        try:
            result = self.store.mutate(payload)
        except ScheduleConflict as exc:
            raise ApiConflict(str(exc)) from exc
        try:
            self.store.advance((datetime.now(timezone.utc).date()+timedelta(days=10)).isoformat())
            self.notifications.tick()
        except Exception:
            self.materialization = "failed"
            self.notification_status = "failed"
            result = {**result, "projection": "pending"}
            LOG.exception("Schedule saved; projection retry pending")
        return result

    def _prepare(self, payload):
        if set(payload) != {"item"}:
            raise LookupError("Unknown route")
        return {"item": prepare_item(payload["item"])}

    def _notification_action(self, payload):
        try:
            result = self.notifications.action(payload)
            self.notifications.tick()
            return result
        except ScheduleConflict as exc:
            raise ApiConflict(str(exc)) from exc

    def _notification_command(self, payload):
        try:
            return self.notifications.command(payload)
        except ScheduleConflict as exc:
            raise ApiConflict(str(exc)) from exc

    def _advance(self, payload):
        if set(payload) != {"through"}:
            raise ValueError("through required")
        if day(payload["through"]) > datetime.now(timezone.utc).date()+timedelta(days=367):
            raise ValueError("Materialization horizon exceeds one year")
        return self.store.advance(payload["through"])
