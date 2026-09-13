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
        if not (self.proc and result.get("ok") and result.get("service") == "kuro-core"
                and result.get("contract") == "kuro.core.schedule.v1" and result.get("schema") == 3
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
            env["KURO_CORE_TOKEN"] = self.token
            command = [_env_python(self.cfg.env_llm), str(self.cfg.root / "kuro_core_service.py"),
                       "--db", str(self.cfg.core_db_path), "--port", str(self.cfg.core_port), "--instance", self.instance, "--timezone", getattr(self.cfg,"core_timezone","UTC")]
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

    def child_environment(self):
        if not self.cfg.core_enabled:
            return {}
        # Pass stable session connection even after startup failure; transport reports unavailable.
        return {"KURO_CORE_URL": self.url, "KURO_CORE_TOKEN": self.token, "KURO_CORE_INSTANCE": self.instance}

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
