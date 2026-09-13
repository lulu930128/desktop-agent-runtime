"""Real controller/Popen/HTTP recovery against isolated Electron children only."""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import launcher_qt  # noqa: E402,F401
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.runtime_logging import setup_runtime_logging
from kuro_launcher.utils import http_post_json


class UnavailableCore:
    def start(self):
        raise RuntimeError("isolated Core unavailable")

    def child_environment(self):
        return {}


def main():
    evidence = ROOT / "launcher_logs" / "work-panel-validation"
    evidence.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="process-", dir=evidence))
    setup_runtime_logging(scratch)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    (scratch / "package.json").write_text(json.dumps({"name": "kuro-isolated-lifecycle-test",
        "main": str(ROOT / "tests" / "work_panel_process_fixture.cjs")}), encoding="utf-8")
    controller = QtLauncherController.__new__(QtLauncherController)
    controller.cfg = SimpleNamespace(root=ROOT, pet_electron_dir=scratch, logs_dir=scratch,
        pet_control_host="127.0.0.1", pet_control_port=port, pet_control_url=f"http://127.0.0.1:{port}",
        llm_url="http://127.0.0.1:1", llm_host="127.0.0.1", llm_port=1,
        launcher_control_url="http://127.0.0.1:1")
    controller._pet_electron_runtime = lambda: (ROOT / "pet-electron/node_modules/electron/dist/electron.exe", None)
    controller.proc_pet_electron = None
    controller._pet_lifecycle_lock = threading.RLock()
    controller._pet_instance_id = ""
    controller._last_pet_exit_pid = None
    controller._pet_output = None
    controller.work_panel_control_token = ""
    controller.core_runtime = UnavailableCore()
    controller.log = lambda _line: None
    checks = []
    try:
        result = controller.ensure_work_panel(timeout_s=8, source="isolated-cold-start")
        assert result["final_status"] == "recovered" and result["recovery_attempt"] == 1, result
        assert result["pid"] != result["previous_pid"], result
        checks.append("crashed first renderer replaced exactly once by tracked child handle")
        checks.append("Core startup failure does not block Work Panel")
        first_pid = result["pid"]
        http_post_json(controller.pet_control_endpoint("/command"), {"action": "set-briefing-visible", "enabled": False})
        assert controller._read_pet_shell_status()["workPanel"]["visible"] is False
        result = controller.ensure_work_panel(source="isolated-reopen")
        assert result["pid"] == first_pid and result["recovery_attempt"] == 0
        checks.append("hide and reopen reuses same child and instance")
        for _ in range(5):
            assert controller.ensure_work_panel(source="isolated-repeat")["pid"] == first_pid
        checks.append("repeated activation does not spawn additional children")
        child = controller.proc_pet_electron
        child.terminate()  # Deliberate crash of this fixture's own exact Popen handle.
        child.wait(timeout=4)
        result = controller.ensure_work_panel(source="isolated-child-exit")
        assert result["ok"] and result["pid"] != first_pid and result["recovery_attempt"] == 0
        checks.append("exited child reconciles and new Electron starts")
        (evidence / "process-result.json").write_text(json.dumps({"ok": True, "checks": checks,
            "scope": "real Launcher controller and isolated Electron fixture; production VBS/runtime not restarted",
            "scratch": str(scratch)}, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "checks": checks}))
    finally:
        child = controller.proc_pet_electron
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=4)
        controller._reconcile_tracked_pet_process()


if __name__ == "__main__":
    main()
