"""Own only the Core process spawned by this launcher; never adopt unknown listeners."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from .procs import ManagedProc
from .services import _env_python
from .utils import port_is_open, windows_hidden_subprocess_kwargs
from .mail_environment import clear_mail_handoffs, mail_handoff_environment, mail_paths


class CoreRuntime:
    def __init__(self, cfg, log):
        self.cfg, self.log = cfg, log
        self.proc = None
        self._log_file = None
        self.token = secrets.token_urlsafe(32)
        self.instance = uuid.uuid4().hex
        self.lock = threading.RLock()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.cfg.core_port}"

    def request(self, route, payload=None):
        request = urllib.request.Request(self.url+route, data=json.dumps(payload).encode() if payload is not None else None,
                                         headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=1) as response:
            body = response.read(65537)
            if len(body) > 65536:
                raise RuntimeError("Core response too large")
            return json.loads(body)

    def ready(self):
        result = self.request("/status")
        capabilities = result.get("capabilities")
        schedule = capabilities.get("schedule") if isinstance(capabilities, dict) else None
        if not (self.proc and result.get("ok") and result.get("service") == "kuro-core"
                and result.get("contract") == "kuro.core.api.v1"
                and isinstance(schedule, dict) and schedule.get("contract") == "kuro.core.schedule.v1"
                and schedule.get("schema") == 3
                and result.get("pid") == self.proc.popen.pid and result.get("instanceId") == self.instance
                and Path(result.get("sourceRoot", "")).resolve() == self.cfg.root.resolve()):
            raise RuntimeError("Core runtime identity mismatch")
        return result

    def start(self):
        with self.lock:
            if not self.cfg.core_enabled:
                return False
            if self.proc and self.proc.popen.poll() is None:
                self.ready()
                return True
            if port_is_open("127.0.0.1", self.cfg.core_port):
                raise RuntimeError("Core port belongs to an unverified process")
            if self._log_file:
                self._log_file.close()
            env = os.environ.copy()
            clear_mail_handoffs(env)
            env["KURO_CORE_TOKEN"] = self.token
            command = [_env_python(self.cfg.env_llm), str(self.cfg.root / "kuro_core_service.py"),
                       "--db", str(self.cfg.core_db_path), "--port", str(self.cfg.core_port), "--instance", self.instance, "--timezone", getattr(self.cfg,"core_timezone","UTC")]
            if getattr(self.cfg, "core_study_enabled", False):
                study_path = getattr(self.cfg, "core_study_snapshot_path", None)
                if study_path is None:
                    raise ValueError("Enabled Study requires an explicit snapshot_path")
                study_path = Path(study_path)
                if not study_path.is_absolute():
                    raise ValueError("Study snapshot_path must be absolute")
                ttl_seconds = getattr(self.cfg, "core_study_ttl_seconds", 3600)
                max_bytes = getattr(self.cfg, "core_study_max_bytes", 2 * 1024 * 1024)
                if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 30 * 24 * 60 * 60:
                    raise ValueError("Study ttl_seconds is out of range")
                if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= 16 * 1024 * 1024:
                    raise ValueError("Study max_bytes is out of range")
                command.extend([
                    "--study-enabled",
                    "--study-snapshot", str(study_path.resolve()),
                    "--study-ttl-seconds", str(ttl_seconds),
                    "--study-max-bytes", str(max_bytes),
                ])
            if getattr(self.cfg, "core_mail_enabled", False):
                mail_path, work_path = mail_paths(self.cfg)
                work_max_bytes = getattr(self.cfg, "core_mail_work_max_bytes", 2097152)
                if type(work_max_bytes) is not int or not 1 <= work_max_bytes <= 2097152:
                    raise ValueError("Mail work_max_bytes is out of range")
                ttl_seconds = getattr(self.cfg, "core_mail_ttl_seconds", 1800)
                max_bytes = getattr(self.cfg, "core_mail_max_bytes", 65536)
                if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 30 * 24 * 60 * 60:
                    raise ValueError("Mail ttl_seconds is out of range")
                if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= 65536:
                    raise ValueError("Mail max_bytes is out of range")
                command.extend([
                    "--mail-enabled",
                    "--mail-status", str(mail_path),
                    "--mail-work", str(work_path),
                    "--mail-work-max-bytes", str(work_max_bytes),
                    "--mail-ttl-seconds", str(ttl_seconds),
                    "--mail-max-bytes", str(max_bytes),
                ])
            log_path = self.cfg.logs_dir / "core" / f"{self.instance}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_file = log_path.open("ab")
            try:
                process = subprocess.Popen(command, cwd=self.cfg.root, env=env, stdout=self._log_file,
                                           stderr=subprocess.STDOUT, **windows_hidden_subprocess_kwargs())
            except Exception:
                self._log_file.close()
                self._log_file = None
                raise
            self.proc = ManagedProc("core", process, log_path, log_path, log_path)
            deadline = time.monotonic()+8
            while time.monotonic() < deadline and self.proc.popen.poll() is None:
                try:
                    self.ready()
                    return True
                except Exception:
                    time.sleep(.1)
            self.stop()
            raise RuntimeError("Core readiness failed; check component logs")

    def _mail_status_path(self):
        return mail_paths(self.cfg)[0]

    def child_environment(self):
        if not self.cfg.core_enabled:
            return {}
        # Pass stable session connection even after startup failure; transport reports unavailable.
        env = {"KURO_CORE_URL": self.url, "KURO_CORE_TOKEN": self.token, "KURO_CORE_INSTANCE": self.instance}
        env.update(mail_handoff_environment(self.cfg))
        return env

    def stop(self):
        with self.lock:
            if self.proc and self.proc.popen.poll() is None:
                try:
                    self.ready()
                    self.request("/shutdown", {})
                    self.proc.popen.wait(timeout=4)
                except Exception:
                    # Exact child handle only, never port-wide kill or unknown owner.
                    self.proc.popen.terminate()
                    self.proc.popen.wait(timeout=4)
            self.proc = None
            if self._log_file:
                self._log_file.close()
                self._log_file = None
