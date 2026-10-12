"""Qt delivery only: Core owns eligibility, leases, quiet hours and retry policy."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QSystemTrayIcon


@dataclass
class _DisplayRequest:
    title: str
    deadline: float
    done: threading.Event = field(default_factory=threading.Event)
    result: str = "unknown"
    cancelled: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class QtScheduleDelivery(QObject):
    """One worker through claim/authorize/display/ack; widgets stay on Qt thread.

    CoreRuntime bounds each HTTP request to one second. UI dispatch has a two
    second deadline; expired queued signals never display. No local retry queue.
    Qt showMessage has no delivery receipt: delivered means API handoff only.
    """

    display_requested = Signal(object)
    completed = Signal(str)
    DISPLAY_TIMEOUT = 2.0

    def __init__(self, controller, tray, log, parent=None):
        super().__init__(parent)
        self.controller, self.tray, self.log = controller, tray, log
        self.busy = False
        self.stopped = threading.Event()
        self.worker = None
        self.pending = None
        self.display_requested.connect(self._display)
        self.completed.connect(self._finish)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.poll)

    def start(self):
        if not self.stopped.is_set():
            self.timer.start()

    def available(self):
        return (self.tray is not None and self.tray.isVisible()
                and QSystemTrayIcon.isSystemTrayAvailable()
                and QSystemTrayIcon.supportsMessages())

    @Slot()
    def poll(self):
        if self.stopped.is_set() or self.busy or not self.available():
            return
        self.busy = True
        self.worker = threading.Thread(target=self._deliver, daemon=True,
                                       name="kuro-qt-schedule-delivery")
        self.worker.start()

    def _deliver(self):
        error = ""
        try:
            claim = self.controller.schedule_notification_action({"action": "claim"})
            delivery = claim.get("delivery")
            if not delivery or self.stopped.is_set():
                return
            identity = {"id": delivery["id"], "leaseToken": delivery["leaseToken"]}
            authorized = self.controller.schedule_notification_action({"action": "authorize", **identity})
            if authorized.get("ok") is False or authorized.get("state") != "dispatching":
                return
            request = _DisplayRequest(str(authorized.get("title") or "有安排需要查看"),
                                      time.monotonic() + self.DISPLAY_TIMEOUT)
            self.pending = request
            if not self.stopped.is_set():
                self.display_requested.emit(request)
                request.done.wait(self.DISPLAY_TIMEOUT)
            with request.lock:
                request.cancelled = True
                result = request.result
            self.controller.schedule_notification_action({"action": "ack", **identity, "result": result})
        except Exception as exc:
            # Do not leak lease tokens, notification titles or private responses.
            error = f"Schedule notification delivery failed: {type(exc).__name__}"
        finally:
            self.pending = None
            self.completed.emit(error)

    @Slot(object)
    def _display(self, request):
        with request.lock:
            if (request.cancelled or self.stopped.is_set()
                    or time.monotonic() >= request.deadline):
                request.done.set()
                return
            try:
                if self.available():
                    self.tray.showMessage("Kuro · 排程提醒", request.title,
                                          QSystemTrayIcon.MessageIcon.Information, 8000)
                    request.result = "delivered"
                else:
                    request.result = "failed"
            except Exception:
                request.result = "failed"
            finally:
                request.done.set()

    @Slot(str)
    def _finish(self, error):
        self.busy = False
        if error:
            self.log(error)

    def stop(self):
        self.stopped.set()
        self.timer.stop()
        request = self.pending
        if request is not None:
            with request.lock:
                request.cancelled = True
                request.done.set()
        if self.worker is not None:
            # Claim/authorize/ack use bounded HTTP; never wait for Qt callbacks.
            self.worker.join(timeout=3.5)
