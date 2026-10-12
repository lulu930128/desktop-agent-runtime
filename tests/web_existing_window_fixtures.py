"""Disposable IO for the real KuroQtLauncherWindow, never a production profile."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import shutil
import threading
import time
import uuid

from web_candidate_fixtures import SyntheticConversation, core_today


class ExistingWindowFixture:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(exist_ok=False)
        self.calls = []
        self.reserved = []
        self.ws = SyntheticConversation()
        self.api = self.capability = self.controller = None
        self.original_connect = socket.socket.connect
        self.memory_env = os.environ.get("KURO_MEMORY_ROOT")
        self.previous_cwd = Path.cwd()
        self.probe_server = None
        self.probe_hits = 0
        self.timing = []
        self.timing_started = time.monotonic()
        self.timing_lock = threading.Lock()

    def mark(self, phase, **metadata):
        # Synthetic fixture only. Never record arguments, status, tokens, IDs,
        # exception text, or raw bridge responses.
        from PySide6.QtCore import QCoreApplication, QThread
        app = QCoreApplication.instance()
        with self.timing_lock:
            self.timing.append(dict(phase=phase, ms=round((time.monotonic()-self.timing_started)*1000, 3),
                gui=bool(app and QThread.currentThread() == app.thread()), **metadata))

    def trace_port(self, port):
        for name in ("request_status", "refresh_status", "refresh_data"):
            original = getattr(port, name)
            def observed(*args, _original=original, _name=name, **kwargs):
                self.mark(_name, inflight=port.status_inflight, waiters=len(port.status_waiters))
                return _original(*args, **kwargs)
            setattr(port, name, observed)
        # Adapter captured the original bound method at construction.
        port.adapter.request_status = port.request_status
        for target, name in ((port.adapter, "read_status"), (port.adapter, "_state_result")):
            original = getattr(target, name)
            def observed(*args, _original=original, _name=name, **kwargs):
                self.mark(_name + ":enter")
                try: return _original(*args, **kwargs)
                finally: self.mark(_name + ":exit")
            setattr(target, name, observed)
        port.delivered.connect(lambda *_: self.mark("queued_delivery", inflight=port.status_inflight,
            waiters=len(port.status_waiters), closed=port.broker.closed))
        def response(raw):
            reply = json.loads(raw)
            value = reply.get("result", {})
            self.mark("broker_response", ok=value.get("ok") is True,
                timeout=value.get("error") == "read_timeout",
                cancelled=value.get("error") in {"stale_context", "context_changed_before_operation"})
        port.wire.response.connect(response)

    def start(self):
        from kuro_core.api_server import CoreApiServer
        from kuro_core.schedule_api import ScheduleCapability
        from kuro_launcher.config import load_config
        self.ws.start()
        self.token = "synthetic-existing-window-" + uuid.uuid4().hex
        self.capability = ScheduleCapability(self.root / "core.sqlite3", default_timezone="Asia/Taipei")
        self.api = CoreApiServer(port=0, token=self.token)
        self.capability.register_routes(self.api)
        self.api.register("GET", "/status", lambda _: {"contract": "kuro.core.api.v1",
            "capabilities": {"schedule": self.capability.status()}})
        self.api.register("GET", "/v1/today", lambda _: core_today())
        self.api.start()
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        fixture = self
        class Probe(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.probe_hits += 1
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers(); self.wfile.write(b"SYNTHETIC reachable")
            def log_message(self, *_): pass
        self.probe_server = ThreadingHTTPServer(("127.0.0.1", 0), Probe)
        self.probe_thread = threading.Thread(target=self.probe_server.serve_forever, daemon=True)
        self.probe_thread.start()
        self.probe_port = self.probe_server.server_address[1]
        ports = []
        for _ in range(3):
            sock = socket.socket(); sock.bind(("127.0.0.1", 0))
            self.reserved.append(sock); ports.append(sock.getsockname()[1])
        allowed = {self.ws.port, self.api.port, self.probe_port, *ports}
        if allowed & {1188, 18890, 23456, 23567, 23568, 23569}:
            raise RuntimeError("Disposable port conflicts with production")
        def bounded(sock, address):
            if not isinstance(address, tuple) or address[0] != "127.0.0.1" or address[1] not in allowed:
                raise PermissionError("Only exact disposable ports are allowed")
            return self.original_connect(sock, address)
        socket.socket.connect = bounded
        os.environ["KURO_MEMORY_ROOT"] = str(self.root / "memories")
        for name in ("characters", "projects/fixture", "llm", "logs", "bridge", "voice", "env", "pet"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "launcher_qt.py").write_text("# SYNTHETIC root identity only\n", encoding="utf-8")
        (self.root / "characters/actor.yaml").write_text(json.dumps({"character_config": {
            "conf_uid": "actor", "conf_name": "SYNTHETIC actor", "default_project_id": "project"}}), encoding="utf-8")
        (self.root / "projects/fixture/project.yaml").write_text(json.dumps({
            "project_id": "project", "display_name": "SYNTHETIC project"}), encoding="utf-8")
        (self.root / "llm/tool_policy.json").write_text(json.dumps({"default_mode": "blocked"}), encoding="utf-8")
        paths = {"ROOT": str(self.root)}
        for key, name in {"open_llm_vtuber_dir": "llm", "characters_dir": "characters", "projects_dir": "projects",
                "bridge_dir": "bridge", "tts_dir": "voice", "env_tts": "env", "env_llm": "env",
                "runtime_conf_path": "runtime.yaml", "logs_dir": "logs", "pet_electron_dir": "pet"}.items():
            paths[key] = str(self.root / name)
        config = {"paths": paths, "startup_profile": {"auto_start": False},
            "network": {name: {"host": "127.0.0.1", "port": port} for name, port in
                (("llm", self.ws.port), ("bridge", ports[0]), ("tts", ports[1]), ("pet_control", ports[2]))},
            "core": {"enabled": True, "port": self.api.port, "db_path": str(self.root / "core.sqlite3")},
            "llm": {"openai": {"default_model": "synthetic-model", "models": ["synthetic-model"],
                "model_env": "W6_SYNTHETIC_UNUSED_MODEL"}}}
        config["network"]["tts"]["mode"] = "central"
        self.config_path = self.root / "kuro_launcher.settings.yaml"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        self.cfg = load_config(self.config_path)
        # Canonical Memory imports use a local-only root, never private cwd.
        os.chdir(self.root)
        return self

    def make_controller(self, cfg, log):
        from kuro_launcher.qt_controller import QtLauncherController
        if self.controller is not None or cfg != self.cfg: raise RuntimeError("Exactly one isolated Controller required")
        controller = QtLauncherController(cfg, log)
        self.controller = controller
        lock = controller._pet_lifecycle_lock
        fixture = self
        class TimedPetLock:
            def __enter__(self):
                fixture.mark("pet_lock:wait")
                lock.acquire(); fixture.mark("pet_lock:acquired")
                return self
            def __exit__(self, *_):
                lock.release(); fixture.mark("pet_lock:released")
        controller._pet_lifecycle_lock = TimedPetLock()
        controller.core_runtime.token = self.token
        # Only external process/device/prompt-refresh IO is substituted. The
        # actual Controller, lifecycle, Core HTTP client and Memory store remain.
        controller._maybe_refresh_memory_prompt = lambda: self.calls.append("synthetic-prompt-refresh")
        def profile(**_):
            self.calls.append("synthetic-profile")
            self.ws.rotate_context()
            return {"ok": True, "mode": "synthetic-no-process"}
        controller._start_profile_impl = profile
        controller._stop_bridge_impl = lambda **_: self.calls.append("synthetic-bridge-stop")
        controller.stop_pet_electron = lambda **_: self.calls.append("synthetic-pet-stop")
        for name in ("read_today", "read_runtime_status", "read_memory_records", "read_schedule_view",
                "read_core_status", "read_schedule_notifications", "read_tool_policy_summary", "close",
                "presentation_state", "read_companion_diagnostics", "reconcile_runtime"):
            original = getattr(controller, name)
            def observed(*args, _original=original, _name=name, **kwargs):
                self.calls.append(_name)
                self.mark(_name + ":enter")
                try: return _original(*args, **kwargs)
                finally: self.mark(_name + ":exit")
            setattr(controller, name, observed)
        return controller

    def enable_synthetic_pet(self):
        """Substitute only device transport; never launch Pet or capture a device."""
        self.mark("synthetic_pet:enable")
        renderer = {"available": True, "micEnabled": False, "cameraEnabled": False, "screenEnabled": False}
        self.controller._read_pet_shell_status = lambda **_: {"renderer": dict(renderer), "mode": "SYNTHETIC"}
        def command(action, *args, **kwargs):
            self.calls.append("synthetic-device:" + action)
            if action == "mic-start": renderer["micEnabled"] = True
            if action in {"mic-submit", "mic-cancel"}: renderer["micEnabled"] = False
            media = {"ok": True, "images": []}
            if action == "mic-submit": media["capture"] = {"format": "pcm16le", "sampleRate": 16000, "data": "AAAAAA=="}
            return {"ok": True, "result": media}
        self.controller.run_pet_command = command

    def stage_restart(self, harness, output, namespace, parent_pid):
        """Byte-identical relaunch helper with an exclusively synthetic root."""
        source = Path(__file__).resolve().parents[1] / "kuro_launcher/relaunch.py"
        target = self.root / "kuro_launcher/relaunch.py"
        target.parent.mkdir()
        shutil.copyfile(source, target)
        argv = ["-I", "-B", str(harness), "--output", str(output), "--namespace", namespace,
                "--restarted-from", str(parent_pid)]
        (self.root / "launcher_qt.py").write_text(
            "# SYNTHETIC restart entry, never production main\nimport os, sys\n"
            + "os.execv(sys.executable, [sys.executable] + " + repr(argv) + ")\n", encoding="utf-8")
        return source.read_bytes() == target.read_bytes()

    def close(self, *, restore=True):
        if hasattr(self.ws, "thread"): self.ws.close()
        if self.api is not None: self.api.stop()
        if self.capability is not None: self.capability.stop()
        if self.probe_server is not None:
            self.probe_server.shutdown(); self.probe_server.server_close(); self.probe_thread.join(2)
        for sock in self.reserved: sock.close()
        # The one-shot native child keeps its process-local bounds until exit:
        # even an in-flight worker cannot resolve a production root/endpoint.
        # Reusable unit fixtures must drain their owned workers before restore.
        if restore:
            socket.socket.connect = self.original_connect
            os.chdir(self.previous_cwd)
            if self.memory_env is None: os.environ.pop("KURO_MEMORY_ROOT", None)
            else: os.environ["KURO_MEMORY_ROOT"] = self.memory_env
