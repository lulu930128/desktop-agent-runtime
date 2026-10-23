"""Composition and process identity for the single Launcher-owned Core host."""
import os
import logging
import threading
from pathlib import Path

from .api_server import CoreApiServer
from .integrations import IntegrationRegistry
from .schedule_api import ScheduleCapability
from .today_capability import TodayCapability
from .assistant_settings import AssistantSettings

LOG = logging.getLogger(__name__)


class CoreApplication:
    def __init__(self, db_path, *, port, token, instance_id, host="127.0.0.1",
                 default_timezone="UTC", study_enabled=False, study_snapshot_path=None,
                 study_ttl_seconds=3600, study_max_bytes=2097152,
                 mail_enabled=False, mail_status_path=None, mail_ttl_seconds=1800, mail_max_bytes=65536,
                 mail_work_path=None, mail_work_max_bytes=2097152, hubs=None):
        if not instance_id:
            raise ValueError("Instance identity required")
        self.instance_id = instance_id
        self.stop_event = threading.Event()
        self.integration_stop = threading.Event()
        self.integration_worker = None
        self.schedule = None
        self.integrations = IntegrationRegistry(
            study_enabled=study_enabled, study_snapshot_path=study_snapshot_path,
            study_ttl_seconds=study_ttl_seconds, study_max_bytes=study_max_bytes,
            mail_enabled=mail_enabled, mail_status_path=mail_status_path,
            mail_ttl_seconds=mail_ttl_seconds, mail_max_bytes=mail_max_bytes, hubs=hubs)
        self.today = TodayCapability(self.integrations, default_timezone=default_timezone,
                                    mail_work_path=mail_work_path, mail_work_max_bytes=mail_work_max_bytes)
        # Bind before any lease/schema IO: a port collision must not touch a DB.
        self.api = CoreApiServer(port=port, token=token, host=host)
        try:
            self.schedule = ScheduleCapability(db_path, default_timezone=default_timezone)
            self.assistant_settings = AssistantSettings(self.schedule.store.path)
            from .omi_integration import OmiIntegration
            self.integrations.readonly_sources['omi'] = OmiIntegration(self.assistant_settings)
            self.assistant_settings.register_routes(self.api)
            self.schedule.register_routes(self.api)
            self.integrations.register_routes(self.api)
            self.today.register_routes(self.api)
            self.api.register("GET", "/status", self._status)
            self.api.register("POST", "/shutdown", self._shutdown)
        except Exception:
            self.api.stop()
            if self.schedule:
                self.schedule.stop()
            raise

    @property
    def port(self):
        return self.api.port

    def start(self):
        try:
            self.api.start()
            self.schedule.start()
            if self.integration_worker is None and not self.integration_stop.is_set():
                self.integration_worker = threading.Thread(
                    target=self._read_integrations, name="kuro-core-integration-read", daemon=True)
                self.integration_worker.start()
        except Exception:
            self.stop()
            raise

    def stop(self):
        self.stop_event.set()
        self.integration_stop.set()
        self.schedule.stop_event.set()
        self.integrations.close()
        self.api.stop()
        self.schedule.stop()
        if self.integration_worker:
            self.integration_worker.join(timeout=3)
            if self.integration_worker.is_alive():
                raise RuntimeError("Core integration reader did not stop")

    def _read_integrations(self):
        # Core-owned transport worker; never share Schedule's execution or stop event.
        while not self.integration_stop.is_set():
            try:
                self.integrations.background_read(self.integration_stop)
            except PermissionError:
                # The affected Hub closes its admission permanently; no retry/bypass.
                LOG.error("Core Hub read blocked at permission boundary")
            except Exception:
                LOG.error("Core Hub snapshot read failed")
            self.integration_stop.wait(1)

    def _status(self, query):
        if query:
            raise ValueError("Status does not accept query fields")
        return {"service": "kuro-core", "contract": "kuro.core.api.v1",
                "instanceId": self.instance_id, "pid": os.getpid(),
                "sourceRoot": str(Path(__file__).resolve().parents[1]),
                "capabilities": {"schedule": self.schedule.status(),
                                 "assistantSettings": self.assistant_settings.runtime_policy(),
                                 "integrations": self.integrations.status(),
                                 "today": self.today.status()}}

    def _shutdown(self, payload):
        if payload != {}:
            raise LookupError("Unknown route")
        self.stop_event.set()
        return {"stopping": True}
