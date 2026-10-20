from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QSystemTrayIcon

from .config import AppConfig
from .qt_branding import load_kuro_icon
from .qt_chat_client import QtRuntimeChatClient
from .qt_controller import QtLauncherController, RuntimeStatus
from .qt_notifications import QtScheduleDelivery
from .qt_web_release import VerifiedOwnerBundle
from .utils import log_ts


class KuroQtLauncherWindow(QMainWindow):
    """Single Qt desktop owner with the verified Git Web presentation."""

    task_finished = Signal(str, object)
    task_failed = Signal(str, str)
    log_signal = Signal(str)
    restart_requested = Signal()

    def __init__(self, cfg: AppConfig, *, web_bundle: VerifiedOwnerBundle):
        if not isinstance(web_bundle, VerifiedOwnerBundle):
            raise TypeError("Verified owner bundle required")
        super().__init__()
        icon = load_kuro_icon()
        QApplication.instance().setWindowIcon(icon)
        self.setWindowIcon(icon)
        self.work_web_candidate = None
        self._lifecycle_tasks = set()
        self.explicit_quitting = False
        self._cleanup_done = False
        self.tray = None
        self.cfg = cfg
        self.controller = QtLauncherController(cfg, self._append_log_threadsafe)
        self.controller.request_restart = self.restart_requested.emit
        self.restart_requested.connect(self._restart_launcher)
        self.chat_client = QtRuntimeChatClient(self)
        self.chat_auto_connect_paused = False
        self.startup_auto_start_fired = False
        self.last_status = None
        self._init_web_presentation(web_bundle)

    def _init_web_presentation(self, bundle) -> None:
        """Same native owner, with no Widget presentation objects or observers."""
        from .qt_web_host import create_existing_window_host
        # A parentless Tool suppresses the Windows taskbar/Alt+Tab entry without
        # adding a second native owner or forcing this window always-on-top.
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Kuro Work Companion")
        self.resize(1380, 860)
        self.setMinimumSize(760, 540)
        self.setCentralWidget(create_existing_window_host(self, bundle))
        self.task_finished.connect(self._on_web_task_finished)
        self.task_failed.connect(self._on_web_task_failed)
        self.log_signal.connect(self._append_log)
        self.chat_client.error_occurred.connect(self._append_log)
        self.chat_client.log_event.connect(self._append_log)
        self._create_tray()
        self._start_notification_delivery()
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.work_web_candidate.owner_port.refresh_status)
        self.status_timer.timeout.connect(self.work_web_candidate.owner_port.refresh_data)
        self.status_timer.timeout.connect(self.chat_client.expire_history_request)
        self.status_timer.timeout.connect(self._ensure_desktop_entry)
        self.status_timer.start(2500)
        self.runtime_timer = QTimer(self)
        self.runtime_timer.timeout.connect(lambda: self._run_task("runtime-reconcile", self.controller.reconcile_runtime, quiet=True))
        self.runtime_timer.start(10000)
        # Original renderer owns its initial getState/getData. No duplicate
        # profile/history/Memory/Today initialization or hidden Widget fallback.
        self._schedule_startup_auto_start()

    def _apply_lifecycle_status(self, status) -> None:
        if self._cleanup_done: return
        self.last_status = status
        self._maybe_auto_connect_chat(status)

    def _start_notification_delivery(self) -> None:
        self.schedule_delivery = QtScheduleDelivery(self.controller, self.tray, self._append_log, self)
        self.schedule_delivery.start()

    def _run_web_task(self, name, fn) -> None:
        if self._cleanup_done or name in self._lifecycle_tasks: return
        if name == "runtime-reconcile" and "start-profile" in self._lifecycle_tasks: return
        self._lifecycle_tasks.add(name)
        def work():
            try: return {"ok": True, "value": fn()}
            except Exception: return {"ok": False, "error": "lifecycle_operation_failed"}
        def done(result):
            if self._cleanup_done: return
            if result.get("ok"): self.task_finished.emit(name, result["value"])
            else: self.task_failed.emit(name, result.get("error", "lifecycle_operation_failed"))
        self.work_web_candidate.owner_port.run_worker(work, done)

    def _submit_web_profile(self, work, done) -> None:
        if self._cleanup_done or self._lifecycle_tasks:
            done({"ok": False, "error": "lifecycle_busy", "retry": False})
            return
        self._lifecycle_tasks.add("start-profile")
        def complete(result):
            self._lifecycle_tasks.discard("start-profile")
            if self._cleanup_done: return
            done(result)
            self.refresh_status()
        self.work_web_candidate.owner_port.run_worker(work, complete)

    def _on_web_task_finished(self, name, result) -> None:
        if self._cleanup_done: return
        self._lifecycle_tasks.discard(name)
        if name != "runtime-reconcile": self.refresh_status()

    def _on_web_task_failed(self, name, message) -> None:
        if self._cleanup_done: return
        self._lifecycle_tasks.discard(name)
        self._set_action_status(message, error=True)
        if name == "start-profile": self.reveal()

    def reveal(self) -> None:
        if self.explicit_quitting:
            return
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _create_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.windowIcon())
        self.tray.setToolTip("Kuro")
        menu = QMenu(self)
        menu.addAction("Show Kuro", self.reveal)
        menu.addAction("Restart Kuro", self._confirm_restart_launcher)
        menu.addAction("Quit Kuro", self.quit_application)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self.reveal)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.reveal()

    def cleanup(self) -> None:
        if self._cleanup_done:
            return
        self.explicit_quitting = True
        self._cleanup_done = True
        if self.work_web_candidate is not None:
            self.work_web_candidate.shutdown_candidate()
        for name in ("status_timer", "runtime_timer", "schedule_delivery", "activation_timer"):
            resource = getattr(self, name, None)
            if resource is not None:
                resource.stop()
        for label, operation in (
            ("chat", self.chat_client.disconnect),
            ("runtime", self.controller.close),
        ):
            try:
                operation()
            except Exception as exc:
                self._append_log(f"Quit cleanup {label} failed: {type(exc).__name__}")
        if self.tray is not None:
            self.tray.hide()

    def _ensure_desktop_entry(self) -> None:
        if not self.explicit_quitting and not QSystemTrayIcon.isSystemTrayAvailable():
            if not self.isVisible():
                self.reveal()

    def quit_application(self) -> None:
        self.cleanup()
        QApplication.instance().quit()

    def _schedule_startup_auto_start(self) -> None:
        if not self.cfg.startup_auto_start or self.startup_auto_start_fired:
            return
        self.startup_auto_start_fired = True
        self._append_log(f"[{log_ts()}] startup_profile auto_start=true，已排程自動啟動 Profile。")
        QTimer.singleShot(900, self._run_startup_auto_start)

    def _run_startup_auto_start(self) -> None:
        if self._cleanup_done: return
        if not self.controller.selected_character() or not self.controller.selected_project():
            self._append_log(f"[{log_ts()}] startup_profile 自動啟動略過：角色或專案尚未選定。")
            self.reveal()
            self._set_action_status("startup profile 缺少角色或專案。", error=True)
            return
        character = self.controller.selected_character()
        project = self.controller.selected_project()
        self._append_log(
            f"[{log_ts()}] startup_profile 自動啟動："
            f"角色={character.conf_name if character else '-'}，"
            f"專案={project.display_name if project else '-'}"
        )
        self._start_profile()

    def _start_profile(self) -> None:
        self.chat_auto_connect_paused = False
        self._run_task("start-profile", self.controller.start_profile)

    def _runtime_chat_url(self) -> str:
        return f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws?client_role=qt-primary"

    def _connect_chat(self, *, auto: bool = False) -> None:
        ws_url = self._runtime_chat_url()
        if not auto:
            self.chat_auto_connect_paused = False
        self.chat_client.connect_to(ws_url)

    def _maybe_auto_connect_chat(self, status: RuntimeStatus) -> None:
        if self.chat_auto_connect_paused:
            return
        if not status.llm:
            return
        ws_url = self._runtime_chat_url()
        if self.chat_client.connected:
            return
        if self.chat_client.running and self.chat_client.ws_url == ws_url:
            return
        self._connect_chat(auto=True)

    def _confirm_restart_launcher(self) -> None:
        if QMessageBox.question(self, "Kuro", "重新啟動 Kuro 與目前的服務？",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._restart_launcher()

    def _restart_launcher(self) -> None:
        if self._cleanup_done: return
        import os
        import subprocess
        import sys
        from .utils import windows_hidden_subprocess_kwargs
        log_path = self.cfg.logs_dir / 'launcher-relaunch.log'
        with log_path.open('ab') as output:
            subprocess.Popen([sys.executable, str(self.cfg.root / 'kuro_launcher' / 'relaunch.py'), str(os.getpid())],
                             cwd=self.cfg.root, stdout=output, stderr=output, **windows_hidden_subprocess_kwargs())
        self.controller.lifecycle.desired_running = False
        self.quit_application()

    def refresh_status(self) -> None:
        if self._cleanup_done: return
        self.work_web_candidate.owner_port.refresh_status()

    def _run_task(self, name: str, fn: Callable[[], object], *, quiet: bool = False) -> None:
        if self._cleanup_done: return
        self._run_web_task(name, fn)

    def _set_action_status(self, text: str, *, error: bool = False) -> None:
        # Keep private exception payloads out of the renderer.
        if self.work_web_candidate is not None:
            self.work_web_candidate.owner_port.publish("onState", {"ok": False,
                "error": "lifecycle_operation_failed" if error else "lifecycle_busy", "retry": False})

    def _append_log_threadsafe(self, text: str) -> None:
        self.log_signal.emit(text)

    def _append_log(self, text: str) -> None:
        # Formal stdout uses the existing launcher.combined.log tee.
        print(f"[{log_ts()}] {text}", flush=True)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange
                and self.isMinimized()
                and not self.explicit_quitting):
            # showMinimized() shows again after the state-change event. Defer
            # until it returns, with this QObject as the callback's lifetime.
            QTimer.singleShot(0, self, self._hide_minimized_to_tray)

    def _hide_minimized_to_tray(self) -> None:
        if not self.explicit_quitting and self.isMinimized():
            # Reuse X-to-tray, including its unavailable-tray recovery.
            self.close()

    def closeEvent(self, event) -> None:
        if getattr(self, "explicit_quitting", False):
            self.cleanup()
            event.accept()
            return
        event.ignore()
        if self.tray is not None and self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.reveal()
            self._set_action_status("System tray unavailable; Kuro remains visible. Use Quit Kuro to exit.", error=True)
