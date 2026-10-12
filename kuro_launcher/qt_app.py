from __future__ import annotations

from types import SimpleNamespace

import base64
import datetime
import mimetypes
import threading
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, QTimer, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QStyle,
    QComboBox,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .qt_chat_client import QtRuntimeChatClient
from .qt_work_companion_view import ComposerEdit, WorkCompanionView, transcript_html
from .qt_notifications import QtScheduleDelivery
from .qt_core_pages import MAIN_NAV_KEYS, SETTINGS_LABELS, TodayPage, SchedulePage, CoreHealthPage
from .qt_controller import (
    PreviewAsset,
    QtLauncherController,
    RuntimeStatus,
)
from .records import HistoryRecord
from .utils import log_ts


BRIEFING_NAV = [
    ("overview", "今日大綱"),
    ("tasks", "待處理"),
    ("mail", "Mail"),
    ("study", "Study"),
    ("messages", "Messages"),
    ("stocks", "Stocks"),
    ("news", "News"),
    ("calendar", "Calendar"),
    ("notes", "Notes"),
]

PROMPT_TABS = [
    ("persona", "角色"),
    ("project", "專案"),
    ("tool", "工具"),
    ("policy", "限制"),
    ("contract", "格式"),
]

MEMORY_STATUS_LABELS = {
    "active": "啟用",
    "pending_confirmation": "待確認",
    "superseded": "已取代",
    "disabled": "停用",
    "pending_delete": "待刪除",
}

MAX_CHAT_ATTACHMENTS = 6
CHAT_ATTACHMENT_LIMIT_MIB = {"image": 8, "audio": 12, "archive": 24, "file": 16, "text": 4, "code": 4}


class KuroQtLauncherWindow(QMainWindow):
    task_finished = Signal(str, object)
    task_failed = Signal(str, str)
    log_signal = Signal(str)
    restart_requested = Signal()

    def __init__(self, cfg: AppConfig, *, web_bundle=None):
        super().__init__()
        self._web_mode = web_bundle is not None
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
        if self._web_mode:
            self._init_web_presentation(web_bundle)
            return
        self.ui_preferences = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                                         "Kuro", "WorkCompanion")
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_base_labels: dict[str, str] = {}
        self.service_labels: dict[str, QLabel] = {}
        self.prompt_boxes: dict[str, QPlainTextEdit] = {}
        self.selected_history_uid = ""
        self.pending_history_uid = ""
        self.pending_force_new_history = False
        self.pending_chat_submit: dict | None = None
        self.sidebar_update_expanded = False
        self.sidebar_services_expanded = False
        self.sidebar_services_user_toggled = False
        self.history_records_by_uid: dict[str, HistoryRecord] = {}
        self.history_item_action_buttons: dict[str, QPushButton] = {}
        self.chat_auto_empty_history_uid = ""
        self.chat_auto_empty_create_pending = False
        self.chat_auto_empty_started = False
        self.chat_auto_connect_paused = False
        self.chat_blank_draft_active = True
        self.startup_auto_start_fired = False
        self.last_status: RuntimeStatus | None = None
        self.pet_toggle_buttons: dict[str, QPushButton] = {}
        self.main_nav_keys = set(MAIN_NAV_KEYS)
        self.configure_nav_keys = {"profile", "pet", "chat_memory"}
        self.system_nav_keys = {"runtime", "settings"}
        self.settings_nav_keys = self.configure_nav_keys | self.system_nav_keys
        self.stack_order = list(MAIN_NAV_KEYS)
        self.settings_order = list(SETTINGS_LABELS)
        self.settings_labels = dict(SETTINGS_LABELS)
        self.settings_dialog_buttons: dict[str, QPushButton] = {}
        self.app_font_stack, self.editor_font_stack = self._load_font_stacks()
        self.chat_client.message_received.connect(self._on_chat_protocol_message)
        self.chat_client.history_operation_changed.connect(self._history_controls_changed)
        self.chat_live_blocks: list[tuple[str, str, str]] = []
        self.chat_base_transcript = ""
        self.chat_attachments: list[dict] = []
        self.chat_runtime_state = "offline"
        self.preview_original_pixmap = QPixmap()
        self.preview_zoom = 1.0
        self.preview_fit_mode = True
        self.preview_refresh_inflight = False
        self.preview_refresh_pending = False
        self.preview_status_signature = ""

        self.setWindowTitle("Kuro Work Companion")
        self.resize(1380, 860)
        self.setMinimumSize(1120, 720)
        self._build_ui()
        self._wire_signals()
        self._create_tray()
        self._start_notification_delivery()
        self._refresh_profile_controls()
        self._refresh_workspace_data()
        self._append_log(f"[{log_ts()}] Qt launcher ready.")

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.timeout.connect(self.chat_client.expire_history_request)
        self.status_timer.timeout.connect(self._refresh_core_pages)
        self.status_timer.timeout.connect(self._ensure_desktop_entry)
        self.status_timer.start(2500)
        self.runtime_timer = QTimer(self)
        self.runtime_timer.timeout.connect(lambda: self._run_task('runtime-reconcile', self.controller.reconcile_runtime, quiet=True))
        self.runtime_timer.start(10000)
        self.refresh_status()
        self.today_page.refresh()
        self._schedule_startup_auto_start()

    def _init_web_presentation(self, bundle) -> None:
        """Same native owner, with no Widget presentation objects or observers."""
        from .qt_web_host import create_existing_window_host
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
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray.setToolTip("Kuro")
        menu = QMenu(self)
        menu.addAction("Show Kuro", self.reveal)
        menu.addAction("Quit Kuro", self.quit_application)
        self.tray.setContextMenu(menu)
        app_menu = self.menuBar().addMenu("Kuro")
        app_menu.addAction("Restart Kuro", self._confirm_restart_launcher)
        app_menu.addAction("Quit Kuro", self.quit_application)
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
            ("history", lambda: None if self._web_mode else self._discard_auto_empty_history_if_safe("__close__")),
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

    def _wire_signals(self) -> None:
        self.task_finished.connect(self._on_task_finished)
        self.task_failed.connect(self._on_task_failed)
        self.log_signal.connect(self._append_log)
        self.chat_client.state_changed.connect(self._on_chat_state_changed)
        self.chat_client.assistant_text_changed.connect(self._on_chat_assistant_text_changed)
        self.chat_client.history_changed.connect(self._on_chat_history_changed)
        self.chat_client.client_changed.connect(self._on_chat_client_changed)
        self.chat_client.error_occurred.connect(self._on_chat_error)
        self.chat_client.log_event.connect(lambda message: self._append_log(f"[{log_ts()}] {message}"))

    def _load_font_stacks(self) -> tuple[str, str]:
        available_families = set(QFontDatabase.families())
        preferred_ui_fonts = [
            "Microsoft JhengHei UI",
            "Microsoft JhengHei",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Segoe UI",
        ]
        bundled_family = ""
        font_path = Path(__file__).with_name("NaikaiFont-Regular.ttf")
        if font_path.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    bundled_family = families[0]

        selected_family = next(
            (family for family in preferred_ui_fonts if family in available_families),
            bundled_family,
        )
        if selected_family:
            self.setFont(QFont(selected_family, 10))

        ui_fonts = [*preferred_ui_fonts, bundled_family, "sans-serif"]
        editor_fonts = [
            "Microsoft JhengHei UI",
            "Microsoft JhengHei",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Cascadia Mono",
            "Consolas",
            bundled_family,
            "monospace",
        ]
        return self._font_stack(ui_fonts), self._font_stack(editor_fonts)

    def _font_stack(self, families: list[str]) -> str:
        seen: set[str] = set()
        quoted: list[str] = []
        for family in families:
            family = (family or "").strip()
            if not family or family in seen:
                continue
            seen.add(family)
            if family in {"sans-serif", "monospace"}:
                quoted.append(family)
            else:
                quoted.append(f'"{family.replace(chr(34), "")}"')
        return ", ".join(quoted)

    def _build_ui(self) -> None:
        self.setStyleSheet(APP_STYLE.replace("__APP_FONT_STACK__", self.app_font_stack)
                           .replace("__EDITOR_FONT_STACK__", self.editor_font_stack))
        self.chat_page = self._build_chat_page()
        self.today_page = TodayPage(self.controller, self)
        self.schedule_page = SchedulePage(self.controller, self)
        self.settings_surface = self._build_settings_surface()
        self.work_companion = WorkCompanionView(
            chat=self.chat_page, today=self.today_page, schedule=self.schedule_page,
            settings=self.settings_surface)
        self.chat_host = self.work_companion
        self.work_companion.return_focus = self.history_toggle
        self.stack = self.work_companion.stack
        self.nav_buttons = self.work_companion.nav_buttons
        self.settings_entry_button = self.nav_buttons["settings"]
        self.history_drawer = self.work_companion.history_drawer
        self.history_list = self.history_drawer.list
        self.history_drawer.selected.connect(self._request_history_selection)
        self.history_drawer.create_requested.connect(self._create_chat_history)
        self.history_drawer.delete_requested.connect(self._delete_history_by_uid)
        self.history_drawer.refresh_requested.connect(self._refresh_history_list)
        self.work_companion.page_changed.connect(self._set_page)
        self.today_page.summary_changed.connect(self.sidebar_today_status.setText)
        self.today_page.context_requested.connect(self._use_today_context)
        self.today_page.schedule_requested.connect(lambda: self._set_page("schedule"))
        self.setCentralWidget(self.work_companion)
        self._history_controls_changed()

    def _build_status_panels(self, sidebar_layout) -> None:
        self.sidebar_update_panel = QFrame()
        self.sidebar_update_panel.setObjectName("SidebarPanel")
        sidebar_update_layout = QVBoxLayout(self.sidebar_update_panel)
        sidebar_update_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_update_layout.setSpacing(0)
        self.sidebar_update_toggle = QPushButton("更新狀態    Ready")
        self.sidebar_update_toggle.setObjectName("SidebarPanelToggle")
        self.sidebar_update_toggle.setCheckable(True)
        self.sidebar_update_toggle.clicked.connect(self._toggle_sidebar_update_panel)
        sidebar_update_layout.addWidget(self.sidebar_update_toggle)
        self.sidebar_update_body = QWidget()
        self.sidebar_update_body.setObjectName("SidebarPanelBody")
        sidebar_update_body_layout = QVBoxLayout(self.sidebar_update_body)
        sidebar_update_body_layout.setContentsMargins(10, 0, 10, 10)
        sidebar_update_body_layout.setSpacing(6)
        self.sidebar_action_status = QLabel("Ready")
        self.sidebar_action_status.setObjectName("SidebarActionStatus")
        self.sidebar_action_status.setWordWrap(True)
        sidebar_update_body_layout.addWidget(self.sidebar_action_status)
        self.sidebar_today_status = QLabel("Today 尚未讀取")
        self.sidebar_today_status.setObjectName("SidebarStatusDetail")
        self.sidebar_today_status.setWordWrap(True)
        sidebar_update_body_layout.addWidget(self.sidebar_today_status)
        self.sidebar_pet_snapshot_status = QLabel("Pet status pending")
        self.sidebar_pet_snapshot_status.setObjectName("SidebarStatusDetail")
        self.sidebar_pet_snapshot_status.setWordWrap(True)
        sidebar_update_body_layout.addWidget(self.sidebar_pet_snapshot_status)
        self.sidebar_update_body.setVisible(False)
        sidebar_update_layout.addWidget(self.sidebar_update_body)
        sidebar_layout.addWidget(self.sidebar_update_panel)

        self.sidebar_status_panel = QFrame()
        self.sidebar_status_panel.setObjectName("SidebarStatusPanel")
        sidebar_status_layout = QVBoxLayout(self.sidebar_status_panel)
        sidebar_status_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_status_layout.setSpacing(0)
        self.sidebar_services_toggle = QPushButton("服務狀態    pending")
        self.sidebar_services_toggle.setObjectName("SidebarPanelToggle")
        self.sidebar_services_toggle.setCheckable(True)
        self.sidebar_services_toggle.clicked.connect(self._toggle_sidebar_services_panel)
        sidebar_status_layout.addWidget(self.sidebar_services_toggle)
        self.sidebar_services_body = QWidget()
        self.sidebar_services_body.setObjectName("SidebarPanelBody")
        sidebar_services_body_layout = QVBoxLayout(self.sidebar_services_body)
        sidebar_services_body_layout.setContentsMargins(10, 0, 10, 10)
        sidebar_services_body_layout.setSpacing(6)
        for key, label in [
            ("SidebarBridge", "Bridge"),
            ("SidebarTTS", "TTS"),
            ("SidebarLLM", "LLM"),
            ("SidebarPet", "Pet Shell"),
        ]:
            row = self._sidebar_status_row(label)
            self.service_labels[key] = row.findChild(QLabel, "StatusValue")
            sidebar_services_body_layout.addWidget(row)
        self.sidebar_services_body.setVisible(False)
        sidebar_status_layout.addWidget(self.sidebar_services_body)
        sidebar_layout.addWidget(self.sidebar_status_panel)



    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return page, layout

    def _build_settings_surface(self) -> QWidget:
        dialog = QWidget()
        dialog.setObjectName("CompanionSettings")

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("SettingsDialogFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        outer.addWidget(frame)

        head = QFrame()
        head.setObjectName("SettingsDialogHead")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(18, 14, 14, 14)
        head_layout.setSpacing(12)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(3)
        title = QLabel("設定")
        title.setObjectName("SettingsDialogTitle")
        subtitle = QLabel("角色、記憶、感知、權限與桌寵；目前生效值由各服務提供。")
        subtitle.setObjectName("SettingsDialogSub")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        head_layout.addLayout(title_box, 1)
        frame_layout.addWidget(head)

        body = QFrame()
        body.setObjectName("SettingsDialogBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        nav = QFrame()
        nav.setObjectName("SettingsDialogNav")
        nav.setFixedWidth(220)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(14, 14, 14, 14)
        nav_layout.setSpacing(8)
        for key in self.settings_order:
            button = QPushButton(self.settings_labels[key].replace("&", "&&"))
            button.setObjectName("SettingsDialogNavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, page_key=key: self._set_settings_dialog_page(page_key))
            self.settings_dialog_buttons[key] = button
            nav_layout.addWidget(button)
        nav_layout.addStretch()
        body_layout.addWidget(nav)

        self.settings_stack = QStackedWidget()
        self.settings_stack.setObjectName("SettingsDialogStack")
        self.core_health_page = CoreHealthPage(self.controller)
        for builder in (self._build_workspace_page, self._build_chat_memory_page,
                        self._build_perception_page, self._build_tools_page,
                        self._build_pet_page, self._build_settings_page):
            self.settings_stack.addWidget(builder())
        body_layout.addWidget(self.settings_stack, 1)
        frame_layout.addWidget(body, 1)

        self._set_settings_dialog_page("general")
        return dialog

    def _settings_key(self, key: str) -> str:
        key = (key or "").strip()
        aliases = {
            "profile": "general",
            "workspace": "general",
            "runtime": "general",
            "pet": "appearance",
            "memory": "conversation",
            "chat_memory": "conversation",
            "chat-memory": "conversation",
            "settings": "advanced",
            "diagnostics": "advanced",
            "sources": "advanced",
            "assistant": "general",
        }
        key = aliases.get(key, key)
        return key if key in self.settings_order else "general"

    def _set_settings_dialog_page(self, key: str) -> None:
        page_key = self._settings_key(key)
        if not hasattr(self, "settings_stack"):
            return
        self.settings_stack.setCurrentIndex(self.settings_order.index(page_key))
        for button_key, button in self.settings_dialog_buttons.items():
            button.setChecked(button_key == page_key)
        if page_key in {"general", "appearance"}:
            QTimer.singleShot(150, self._request_preview_asset_refresh)
        elif page_key == "advanced":
            self.core_health_page.refresh()
            self._refresh_diagnostics()
        elif page_key == "tools":
            self._refresh_tool_policy()

    def _open_settings_dialog(self, key: str = "general") -> None:
        if not hasattr(self, "work_companion"):
            return
        self._set_settings_dialog_page(key)
        self.work_companion.set_page("settings")


    def _settings_page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        outer.addWidget(title_label)
        outer.addWidget(subtitle_label)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("SettingsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return page, layout

    def _settings_section(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        section = QFrame()
        section.setObjectName("SettingsSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("SettingsSectionTitle")
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("SettingsSectionSub")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)
        return section, layout

    def _settings_inline_controls(self, *widgets: QWidget, stretch: bool = False) -> QWidget:
        box = QWidget()
        box.setObjectName("SettingsInlineControls")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for widget in widgets:
            layout.addWidget(widget)
        if stretch:
            layout.addStretch()
        return box

    def _settings_row(self, title: str, description: str, control: QWidget, *, wide: bool = False) -> QFrame:
        row = QFrame()
        row.setObjectName("SettingsRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("SettingsRowTitle")
        description_label = QLabel(description)
        description_label.setObjectName("SettingsRowDescription")
        description_label.setWordWrap(True)
        text_box.addWidget(title_label)
        text_box.addWidget(description_label)
        layout.addLayout(text_box, 1)

        control.setSizePolicy(QSizePolicy.Policy.Expanding if wide else QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(control, 1 if wide else 0)
        return row

    def _settings_detail_panel(self, title: str, detail: QLabel) -> QFrame:
        panel = QFrame()
        panel.setObjectName("SettingsInfoPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("SettingsRowTitle")
        layout.addWidget(title_label)
        detail.setObjectName("MetaText")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(detail, 1)
        return panel

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)
        layout.addWidget(self._build_chat_tab(), 1)
        return page


    def _build_workspace_page(self) -> QWidget:
        page, layout = self._settings_page(
            "General",
            "Profile 啟動時會使用的角色、專案與推理強度。",
        )
        self.workspace_status = QLabel("Profile ready.")
        self.workspace_status.setObjectName("StatusBanner")
        self.workspace_status.setWordWrap(True)
        layout.addWidget(self.workspace_status)

        profile_section, profile_layout = self._settings_section(
            "Active profile",
            "只保留啟動 runtime 需要的核心設定；外觀與 debug 另放在其他分類。",
        )
        self.character_combo = QComboBox()
        self.character_combo.setMinimumWidth(320)
        self.character_combo.currentIndexChanged.connect(self._on_character_changed)
        profile_layout.addWidget(
            self._settings_row(
                "角色",
                "決定 persona、預設專案與 Live2D 模型來源。",
                self.character_combo,
                wide=True,
            )
        )
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(320)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        profile_layout.addWidget(
            self._settings_row(
                "專案",
                "決定專案 prompt、工具 prompt 與工作資料夾。",
                self.project_combo,
                wide=True,
            )
        )
        self.thinking_combo = QComboBox()
        self._populate_thinking_combo(self.thinking_combo)
        self.thinking_combo.setMinimumWidth(180)
        self.thinking_combo.currentIndexChanged.connect(self._on_thinking_changed)
        profile_layout.addWidget(
            self._settings_row(
                "Thinking power",
                "調整目前專案使用的推理強度設定。",
                self.thinking_combo,
            )
        )
        self.model_combo = QComboBox()
        for model in self.cfg.openai_models:
            self.model_combo.addItem(model, model)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        profile_layout.addWidget(self._settings_row("LLM 模型", "只列出 Launcher 設定允許的模型；套用後才生效。",
                                                   self.model_combo, wide=True))
        layout.addWidget(profile_section)

        actions_section, actions_layout = self._settings_section(
            "Profile actions",
            "啟動目前 profile，或重新讀取本機 profiles / projects 設定檔。",
        )
        actions_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("套用助理設定", self._confirm_profile_apply, role="primary"),
                self._command_button("重新讀取 Profiles", self._reload_profiles),
                stretch=True,
            )
        )
        layout.addWidget(actions_section)

        detail_section, detail_layout = self._settings_section("Selection details")
        detail_grid = QGridLayout()
        detail_grid.setContentsMargins(0, 0, 0, 0)
        detail_grid.setHorizontalSpacing(12)
        detail_grid.setVerticalSpacing(12)
        detail_grid.setColumnStretch(0, 1)
        detail_grid.setColumnStretch(1, 1)
        self.character_detail = QLabel("")
        self.project_detail = QLabel("")
        detail_grid.addWidget(self._settings_detail_panel("Character", self.character_detail), 0, 0)
        detail_grid.addWidget(self._settings_detail_panel("Project", self.project_detail), 0, 1)
        detail_layout.addLayout(detail_grid)
        layout.addWidget(detail_section)
        layout.addStretch()
        return page

    def _build_chat_memory_page(self) -> QWidget:
        page, layout = self._settings_page(
            "Conversation",
            "對話狀態、初始草稿策略與角色長期記憶。",
        )
        self.chat_settings_status = QLabel(
            "Conversation 自動保存訊息；按「新對話」或送出首則訊息時建立對話。"
        )
        self.chat_settings_status.setObjectName("StatusBanner")
        self.chat_settings_status.setWordWrap(True)
        layout.addWidget(self.chat_settings_status)
        layout.addWidget(self._settings_inline_controls(
            self._command_button("開啟對話紀錄", self._open_history_from_settings),
            self._command_button("建立新對話", self._create_history_from_settings)))

        memory_section, memory_layout = self._settings_section(
            "Character memory",
            "使用目前角色的記憶服務；新增、狀態修改、刪除與整理都會確認角色及內容。每筆最多 260 字。",
        )
        memory_layout.addWidget(self._build_memory_tab(), 1)
        layout.addWidget(memory_section, 1)
        return page


    def _build_chat_tab(self) -> QWidget:
        page = QWidget()
        page.content = QVBoxLayout(page)
        page.content.setContentsMargins(0, 0, 0, 0)
        self._chat_history_rows = []
        self._chat_tool_rows = {}
        self._history_list_loaded = False
        self._history_selection_user_requested = False
        self._profile_applying = False
        header = QHBoxLayout()
        self.history_toggle = QPushButton("☰")
        self.history_toggle.setAccessibleName("開啟對話紀錄")
        self.history_toggle.clicked.connect(self._toggle_history_drawer)
        header.addWidget(self.history_toggle)
        self.chat_title = QLabel("普通對話")
        self.chat_title.setObjectName("PageTitle")
        header.addWidget(self.chat_title, 1)
        assistant_settings = QPushButton("助理設定")
        assistant_settings.clicked.connect(lambda: self._open_settings_dialog("general"))
        header.addWidget(assistant_settings)
        self.chat_identity_label = QLabel("尚未選取對話")
        self.chat_identity_label.setTextFormat(Qt.TextFormat.PlainText)
        self.chat_identity_label.setWordWrap(True)
        page.content.addLayout(header)
        page.content.addWidget(self.chat_identity_label)
        self.chat_context = QFrame()
        context_layout = QHBoxLayout(self.chat_context)
        self.chat_context_label = QLabel()
        self.chat_context_label.setTextFormat(Qt.TextFormat.PlainText)
        self.chat_context_label.setWordWrap(True)
        context_layout.addWidget(self.chat_context_label, 1)
        self.clear_chat_context = QPushButton("移除脈絡標記")
        self.clear_chat_context.setToolTip("移除目前帶入的項目標記；可直接編輯草稿中的參考文字。")
        self.clear_chat_context.clicked.connect(self.chat_context.hide)
        context_layout.addWidget(self.clear_chat_context)
        self.chat_context.hide()
        page.content.addWidget(self.chat_context)
        self.chat_connection_status = QLabel("對話服務尚未連線。")
        self.chat_connection_status.setObjectName("StatusBanner")
        self.chat_connection_status.setWordWrap(True)
        page.content.addWidget(self.chat_connection_status)
        self.history_transcript = QTextEdit()
        self.history_transcript.setObjectName("TranscriptBox")
        self.history_transcript.setReadOnly(True)
        page.content.addWidget(self.history_transcript, 1)
        self.chat_attachment_tray = QFrame()
        self.chat_attachment_tray.setObjectName("AttachmentTray")
        self.chat_attachment_layout = QHBoxLayout(self.chat_attachment_tray)
        self.chat_attachment_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_attachment_layout.addStretch()
        self.chat_attachment_tray.hide()
        page.content.addWidget(self.chat_attachment_tray)
        composer = QFrame()
        composer.setObjectName("ComposerPanel")
        composer_layout = QVBoxLayout(composer)
        self.chat_input = ComposerEdit()
        self.chat_input.setAccessibleName("輸入普通對話")
        self.chat_input.setObjectName("ComposerInput")
        self.chat_input.submit_requested.connect(self._send_chat_text)
        composer_layout.addWidget(self.chat_input)
        controls = QHBoxLayout()
        self.chat_attach_button = QPushButton("＋ 附件")
        self.chat_attach_button.clicked.connect(self._show_chat_add_menu)
        controls.addWidget(self.chat_attach_button)
        controls.addStretch()
        self.chat_thinking_combo = QComboBox()
        self._populate_thinking_combo(self.chat_thinking_combo)
        self.chat_thinking_combo.currentIndexChanged.connect(self._on_thinking_changed)
        controls.addWidget(self.chat_thinking_combo)
        self.chat_send_button = QPushButton("送出")
        self.chat_send_button.clicked.connect(self._send_or_interrupt_chat)
        controls.addWidget(self.chat_send_button)
        composer_layout.addLayout(controls)
        page.content.addWidget(composer)
        page.content.addWidget(QLabel("Enter 送出 · Shift + Enter 換行"))
        return page

    def _toggle_history_drawer(self) -> None:
        visible = not self.history_drawer.isVisible()
        self.chat_host.show_history(visible)
        if visible:
            self._refresh_history_list()

    def _history_controls_changed(self, _operation="") -> None:
        if not hasattr(self, "history_drawer"):
            return
        if _operation:
            self._history_error = ""
        busy = self.chat_client.history_pending or self._chat_response_active() or self._profile_applying
        self.history_drawer.set_state(ready=self.chat_client.history_ready, pending=busy,
                                      error=getattr(self, "_history_error", ""))
        self._update_chat_send_button()

    def _request_history_selection(self, history_uid: str) -> None:
        if self._chat_response_active() or self.pending_chat_submit or self._profile_applying:
            return
        if history_uid == self.chat_client.current_history_uid:
            self.chat_host.show_history(False)
            return
        if self.chat_client.select_history(history_uid):
            self._history_selection_user_requested = True

    def _update_chat_identity(self) -> None:
        if not hasattr(self, "chat_identity_label"):
            return
        uid = self.chat_client.current_history_uid
        record = self.history_records_by_uid.get(uid)
        title = record.title if record else self.chat_client.current_history_title
        self.chat_title.setText(title or "普通對話")
        self.chat_identity_label.setText(
            f"{self.chat_client.conf_name or self.chat_client.conf_uid or '尚未連線'} · "
            f"{self.chat_client.active_project_id or '專案未提供'} · {uid or '尚未選取對話'}\n"
            f"生效模型：{self.chat_client.effective_model or '服務尚未提供'} · "
            f"推理：{self.chat_client.thinking_power or '服務尚未提供'}")
        self.chat_identity_label.setToolTip(f"confUid: {self.chat_client.conf_uid}\ncontext: {self.chat_client.context_id}")
        self.history_drawer.set_records(self.history_records_by_uid.values(), uid)
        if hasattr(self, "chat_settings_status"):
            count = (f"{len(self.history_records_by_uid)} 段" if self._history_list_loaded else "尚未完成讀取")
            if not self.chat_client.history_ready:
                count += "（服務未就緒）"
            self.chat_settings_status.setText("Conversation 自動保存訊息；按「新對話」或送出首則訊息時建立對話。\n"
                f"目前對話：{title or '尚未選取'}\n對話數量：{count}")

    def _build_memory_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        actions = QGridLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        memory_actions = [
            self._command_button("新增", self._add_memory_dialog),
            self._command_button("啟停", self._toggle_selected_memory),
            self._command_button("批准", self._approve_selected_memory),
            self._command_button("拒絕", self._reject_selected_memory),
            self._command_button("刪除", self._delete_selected_memory, role="danger"),
            self._command_button("整理", self._compact_memory),
            self._command_button(
                "刷新 Runtime 記憶 Prompt",
                lambda: self._run_task("refresh-memory", self.controller.refresh_memory_prompt),
            ),
            self._command_button("更新列表", self._refresh_memory_list),
        ]
        for index, button in enumerate(memory_actions):
            actions.addWidget(button, index // 4, index % 4)
        for column in range(4):
            actions.setColumnStretch(column, 1)
        outer.addLayout(actions)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)
        self.memory_list = QListWidget()
        self.memory_list.setObjectName("SectionList")
        self.memory_list.setMinimumWidth(340)
        self.memory_list.itemSelectionChanged.connect(self._on_memory_selected)
        layout.addWidget(self.memory_list, 0)
        self.memory_detail = QTextEdit()
        self.memory_detail.setObjectName("TranscriptBox")
        self.memory_detail.setReadOnly(True)
        layout.addWidget(self.memory_detail, 1)
        outer.addLayout(layout, 1)
        return page

    def _build_pet_page(self) -> QWidget:
        page, layout = self._settings_page(
            "Appearance",
            "桌寵視覺、服裝、表情與一般視窗行為。",
        )
        self.pet_status_label = QLabel("Pet status pending")
        self.pet_status_label.setObjectName("StatusBanner")
        self.pet_status_label.setWordWrap(True)
        layout.addWidget(self.pet_status_label)

        preview_panel, preview_layout = self._settings_section(
            "Model preview",
            "預覽目前角色與服裝會使用的本機素材。",
        )
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("MetaText")
        self.preview_meta.setWordWrap(True)
        preview_layout.addWidget(self.preview_meta)
        preview_tools = self._settings_inline_controls(
            self._tool_button("Fit", self._preview_fit),
            self._tool_button("-", self._preview_zoom_out),
            stretch=True,
        )
        self.preview_zoom_label = QLabel("Fit")
        self.preview_zoom_label.setObjectName("ZoomLabel")
        self.preview_zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_tools.layout().insertWidget(2, self.preview_zoom_label)
        preview_tools.layout().insertWidget(3, self._tool_button("+", self._preview_zoom_in))
        preview_tools.layout().insertWidget(4, self._tool_button("100%", self._preview_actual_size))
        preview_layout.addWidget(preview_tools)

        self.preview_image_label = QLabel("選取角色後會在這裡顯示預覽")
        self.preview_image_label.setObjectName("PreviewImage")
        self.preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image_label.setMinimumSize(520, 220)
        self.preview_image_label.setWordWrap(True)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("PreviewScroll")
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setMinimumHeight(220)
        self.preview_scroll.setWidget(self.preview_image_label)
        preview_layout.addWidget(self.preview_scroll, 1)

        appearance_panel, appearance_layout = self._settings_section(
            "Visual state",
            "一般使用者會調整的桌寵外觀狀態。",
        )
        self.outfit_combo = QComboBox()
        self.outfit_combo.addItem("帽T", "hoodie")
        self.outfit_combo.addItem("原版", "normal")
        self.outfit_combo.setMinimumWidth(180)
        self.outfit_combo.currentIndexChanged.connect(self._on_outfit_changed)
        self.outfit_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        appearance_layout.addWidget(
            self._settings_row(
                "服裝",
                "沿用 pet-electron control server 的 set-outfit command。",
                self._settings_inline_controls(
                    self.outfit_combo,
                    self._command_button("套用服裝到 Shell", lambda: self._run_task("apply-outfit", self.controller.apply_outfit)),
                ),
                wide=True,
            )
        )

        self.pet_expression_combo = QComboBox()
        for expression_id, label in self.controller.expression_options():
            self.pet_expression_combo.addItem(label, expression_id)
        self.pet_expression_combo.setMinimumWidth(180)
        self.pet_expression_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        appearance_layout.addWidget(
            self._settings_row(
                "表情",
                "套用目前桌寵 shell 支援的 expression。",
                self._settings_inline_controls(
                    self.pet_expression_combo,
                    self._command_button(
                        "套用表情",
                        lambda: self._run_task(
                            "pet-expression",
                            lambda: self.controller.set_expression(str(self.pet_expression_combo.currentData() or "neutral")),
                        ),
                    ),
                ),
                wide=True,
            )
        )
        appearance_panel.setProperty("petControlGroup", True)
        appearance_panel.setEnabled(False)
        appearance_panel.setToolTip("尚未取得 Pet 的有效狀態。")
        layout.addWidget(appearance_panel)

        window_panel, window_layout = self._settings_section(
            "Window behavior",
            "只放日常會用到的視窗行為；工程診斷開關收在 Advanced。",
        )
        window_layout.addWidget(
            self._settings_row(
                "Game mode",
                "切換桌寵視窗在遊戲場景下的行為。",
                self._pet_toggle_button("set-game-mode", "Game mode"),
            ),
        )
        window_layout.addWidget(
            self._settings_row(
                "Display",
                "把桌寵移到下一個螢幕。",
                self._command_button(
                    "移到下一個螢幕",
                    lambda: self._run_task("pet-move-display", self.controller.move_pet_next_display),
                ),
            )
        )
        window_layout.addWidget(self._settings_row(
            "滑鼠穿透", "開啟後整個桌寵層穿透；透明區域原本就不攔截滑鼠。",
            self._pet_toggle_button("set-force-ignore-mouse", "滑鼠穿透")))
        window_layout.addWidget(self._settings_inline_controls(
            self._command_button("顯示桌寵", lambda: self._run_task("pet-show", self.controller.show_pet)),
            self._command_button("播放待機動作", lambda: self._run_task("pet-idle", lambda:
                                 self.controller.run_pet_command("play-motion", {"group": "Idle"}))),
            self._command_button("重置桌寵位置", lambda: self._run_task("pet-reset", lambda:
                                 self.controller.run_pet_command("reset-pet-position")))))
        window_panel.setProperty("petControlGroup", True)
        window_panel.setEnabled(False)
        window_panel.setToolTip("尚未取得 Pet 的有效狀態。")
        layout.addWidget(window_panel)
        layout.addWidget(preview_panel, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._settings_page(
            "Advanced",
            "Runtime、工程診斷、prompt preview、paths 與 logs。",
        )
        self.compact_control = QCheckBox("緊湊顯示")
        self.compact_control.setChecked(self.ui_preferences.value("compact", False, type=bool))
        self.compact_control.toggled.connect(self._set_compact_display)
        layout.addWidget(self.compact_control)
        reduced = QCheckBox("降低動態效果（目前 Qt 抽屜不播放動畫，固定啟用）")
        reduced.setChecked(True)
        reduced.setEnabled(False)
        layout.addWidget(reduced)
        self.companion_diagnostics = QPlainTextEdit()
        self.companion_diagnostics.setReadOnly(True)
        layout.addWidget(self.companion_diagnostics)
        layout.addWidget(self._settings_inline_controls(
            self._command_button("重新讀取診斷", self._refresh_diagnostics),
            self._command_button("停止目前輸出", self._interrupt_chat),
            self._command_button("重試啟動對話", lambda: self._confirm_runtime_action("retry-runtime",
                "重試啟動目前 Launcher profile？可能啟動 Conversation、語音依賴及桌寵。", self.controller.retry_runtime)),
            self._command_button("重新啟動 Kuro", self._confirm_restart_launcher)))
        runtime_panel, runtime_layout = self._settings_section(
            "Runtime services",
            "服務狀態與 runtime 控制集中在這裡，避免和日常 profile 設定混在一起。",
        )
        self.runtime_status_label = QLabel("Runtime status pending")
        self.runtime_status_label.setObjectName("StatusBanner")
        self.runtime_status_label.setWordWrap(True)
        runtime_layout.addWidget(self.runtime_status_label)
        self.runtime_detail = QLabel("")
        self.runtime_detail.setObjectName("MetaText")
        self.runtime_detail.setWordWrap(True)
        self.runtime_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        runtime_layout.addWidget(self.runtime_detail)
        runtime_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("停止對話服務", lambda: self._confirm_runtime_action("stop-runtime",
                    "停止目前對話服務？桌寵、Qt、Core 與共享中央語音會保留。",
                    lambda: self.controller.stop_profile(stop_bridge=False, stop_pet=False)), role="danger"),
                self._command_button("Bridge 開關", lambda: self._run_task("toggle-bridge", self.controller.toggle_bridge)),
                stretch=True,
            )
        )
        layout.addWidget(runtime_panel)

        debug_panel, debug_layout = self._settings_section(
            "Debug tools",
            "低階端點、bridge 與翻譯診斷工具。",
        )
        debug_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("套用桌寵後端端點", lambda: self._run_task("pet-backend-config", self.controller.apply_pet_backend_config)),
                self._command_button("Bridge 重啟", lambda: self._run_task("restart-bridge", self.controller.restart_bridge)),
                self._command_button("Translate Debug", lambda: self._run_task("translate-debug", self.controller.translate_debug)),
                stretch=True,
            )
        )
        debug_layout.addWidget(
            self._settings_row(
                "Live2D Inspector",
                "開啟 renderer overlay，用來檢查 Live2D canvas、座標與狀態。",
                self._pet_toggle_button("set-live2d-inspector", "Live2D Inspector"),
            )
        )
        layout.addWidget(debug_panel)

        pet_shell_panel, pet_shell_layout = self._settings_section(
            "Pet shell",
            "只保留 shell 啟動、重載與關閉這類維護操作。",
        )
        self.pet_reload_button = self._command_button("重新載入角色", self._reload_pet_model)
        self.pet_reload_button.setEnabled(False)
        self.pet_reload_button.setToolTip("需要 Pet 提供有效狀態後才能重新載入角色。")
        pet_shell_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("開桌寵 Shell", lambda: self._run_task("open-pet", self.controller.launch_pet_electron)),
                self.pet_reload_button,
                self._command_button("關閉桌寵", lambda: self._run_task("pet-close", self.controller.stop_pet_electron), role="danger"),
                stretch=True,
            )
        )
        self.pet_detail = QLabel("")
        self.pet_detail.setObjectName("MetaText")
        self.pet_detail.setWordWrap(True)
        self.pet_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pet_shell_layout.addWidget(self.pet_detail)
        layout.addWidget(pet_shell_panel)

        prompt_panel, prompt_layout = self._settings_section(
            "Prompt preview",
            "完整 prompt 預覽放在進階頁，避免壓縮一般 profile 設定。",
        )
        self.prompt_tabs = QTabWidget()
        self.prompt_tabs.setObjectName("PromptTabs")
        self.prompt_tabs.setMinimumHeight(260)
        for key, label in PROMPT_TABS:
            box = QPlainTextEdit()
            box.setObjectName("PromptBox")
            box.setReadOnly(True)
            box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.prompt_boxes[key] = box
            self.prompt_tabs.addTab(box, label)
        prompt_layout.addWidget(self.prompt_tabs, 1)
        layout.addWidget(prompt_panel, 1)

        path_panel, path_layout = self._settings_section(
            "Paths",
            "目前 launcher 使用的本機路徑與端點。",
        )
        paths = QLabel(
            "\n".join(
                [
                    f"root: {self.cfg.root}",
                    f"open_llm: {self.cfg.open_llm_dir}",
                    f"pet_electron: {self.cfg.pet_electron_dir}",
                    f"logs: {self.cfg.logs_dir}",
                    f"bridge: {self.cfg.bridge_url}",
                    f"llm: {self.cfg.llm_url}",
                    f"pet_control: {self.cfg.pet_control_url}",
                ]
            )
        )
        paths.setObjectName("MonoText")
        paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_layout.addWidget(paths)
        layout.addWidget(path_panel)

        log_panel, log_layout = self._settings_section("Logs")
        self.log_box = QTextEdit()
        self.log_box.setObjectName("LogBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(130)
        log_layout.addWidget(self.log_box, 1)
        log_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("刷新狀態", self.refresh_status),
                self._command_button("開 Logs 目錄", self.controller.open_logs_dir),
                stretch=True,
            )
        )
        layout.addWidget(log_panel, 1)
        self.core_health_page.setMinimumHeight(380)
        layout.addWidget(self.core_health_page)
        self._build_status_panels(layout)
        return page

    def _set_compact_display(self, enabled: bool) -> None:
        self.ui_preferences.setValue("compact", bool(enabled))
        self.ui_preferences.sync()
        if self.ui_preferences.status() != QSettings.Status.NoError:
            self._set_action_status("顯示已調整，但本機偏好無法保存。", error=True)
        self._render_chat_transcript_with_live()

    def _open_history_from_settings(self) -> None:
        self._set_page("chat")
        self.chat_host.show_history(True)
        self._refresh_history_list()

    def _use_today_context(self, context: dict) -> None:
        if self.pending_chat_submit or self._chat_response_active() or self._profile_applying:
            self._set_action_status("目前對話仍忙碌；Today 內容尚未帶入。", error=True)
            return
        self._set_page("chat")
        draft = self.chat_input.toPlainText().rstrip()
        self.chat_input.setPlainText((draft + "\n\n" if draft else "") + "[Core Today 參考]\n" + context["text"])
        self.chat_context_label.setText(f"目前帶入：{context.get('title') or context['workId']} · {context.get('source') or 'Core'}")
        self.chat_context.show()
        self.chat_input.setFocus()
        self._set_chat_status("Today 內容已帶入草稿，請確認後按送出。")

    def _create_history_from_settings(self) -> None:
        self._set_page("chat")
        self._create_chat_history()

    def _build_perception_page(self) -> QWidget:
        page, layout = self._settings_page("語音與感知", "錄音只有按下「完成並送出」才會建立對話回合。")
        self.perception_status = QLabel("感知狀態尚未取得；需要 Pet 的擷取能力。")
        self.perception_status.setWordWrap(True)
        layout.addWidget(self.perception_status)
        section, body = self._settings_section("麥克風", "錄音保留在本機，可暫停、繼續或取消。")
        row = QHBoxLayout()
        self.microphone_buttons = {}
        for action, title in (("start", "開始錄音"), ("pause", "暫停"), ("resume", "繼續"),
                              ("submit", "完成並送出"), ("cancel", "取消")):
            control = self._command_button(title, lambda action=action: self._microphone_action(action))
            control.setObjectName("Mic_" + action)
            control.setEnabled(False)
            control.setToolTip("尚未取得 Pet 擷取能力狀態。")
            self.microphone_buttons[action] = control
            row.addWidget(control)
        body.addLayout(row)
        layout.addWidget(section)
        for action, title, description in (
            ("toggle-camera", "鏡頭", "啟用後，下次明確送出的訊息可附上鏡頭畫面。"),
            ("toggle-screen", "本回合螢幕擷取", "只用於下一次送出的訊息，不是持續背景監控。")):
            control = self._pet_toggle_button(action, title)
            control.setEnabled(False)
            control.setToolTip("尚未取得 Pet 擷取能力狀態。")
            layout.addWidget(self._settings_row(title, description, control))
        layout.addStretch()
        return page

    def _build_tools_page(self) -> QWidget:
        page, layout = self._settings_page("工具與權限", "只呈現已儲存政策；目前 runtime 是否採用，仍需服務確認。")
        layout.addWidget(self._command_button("重新讀取政策", self._refresh_tool_policy))
        self.tools_status = QLabel("尚未讀取工具政策。")
        self.tools_status.setWordWrap(True)
        layout.addWidget(self.tools_status)
        self.tools_list = QPlainTextEdit()
        self.tools_list.setReadOnly(True)
        self.tools_list.setMinimumHeight(260)
        layout.addWidget(self.tools_list, 1)
        unavailable = QPushButton("修改權限（尚未提供）")
        unavailable.setEnabled(False)
        unavailable.setToolTip("目前沒有正式的權限寫入／逐次確認 owner，不能從 UI 繞過政策。")
        layout.addWidget(unavailable)
        layout.addWidget(QLabel("需要確認的工具保持封鎖；沒有全域自動放行開關。"))
        return page

    def _refresh_tool_policy(self) -> None:
        try:
            payload = self.controller.read_tool_policy_summary()
            self.tools_status.setText(f"預設模式：{payload['default_mode']} · runtime 採用：未驗證\n"
                                      "逐次工具確認尚未實作；read_only 仍需執行時參數及能力檢查。")
            self.tools_list.setPlainText("\n\n".join(
                f"{item['name']} · {item['category']} · {item['mode']}\n{item['reason']}"
                for item in payload["tools"]) or "目前沒有已註冊工具。")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.tools_status.setText(f"工具政策未載入：{type(exc).__name__}。請檢查設定後重新讀取。")
            self.tools_list.clear()

    def _refresh_diagnostics(self) -> None:
        try:
            payload = self.controller.read_companion_diagnostics()
            voice = payload.get("voice") or {}
            self.companion_diagnostics.setPlainText("\n".join((
                f"啟動狀態：{payload.get('phase', '尚未提供')}",
                f"原因：{payload.get('reason') or '—'}",
                f"語音：{voice.get('state', '尚未提供')} · {voice.get('reason') or '—'}",
                f"執行版本：{payload.get('sourceRevision', '尚未提供')}",
                f"需要重新啟動：{payload.get('restartRequired', '尚未提供')}",
                f"角色：{self.chat_client.conf_uid} · 專案：{self.chat_client.active_project_id}",
                f"context：{self.chat_client.context_id} · 對話：{self.chat_client.current_history_uid}",
                f"模型：{self.chat_client.effective_model or '服務尚未提供'} · 推理：{self.chat_client.thinking_power or '服務尚未提供'}")))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.companion_diagnostics.setPlainText(f"診斷尚未取得：{type(exc).__name__}")

    def _confirm_runtime_action(self, name: str, description: str, operation) -> None:
        if QMessageBox.question(self, "確認服務操作", description,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._run_task(name, operation)

    def _reload_pet_model(self) -> None:
        if not getattr(self, "last_status", None) or not self.last_status.pet_shell:
            self._set_action_status("Pet 尚未就緒；請先開啟桌寵，才能重新載入角色。", error=True)
            return
        self._confirm_runtime_action("pet-reload", "重新載入桌寵角色？目前的桌寵播放與感知擷取會中斷。",
                                     self.controller.reload_pet_frontend)

    def _status_card(self, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("StatusCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        title = QLabel(label)
        title.setObjectName("CardTitle")
        value = QLabel("unknown")
        value.setObjectName("StatusValue")
        layout.addWidget(title)
        layout.addWidget(value)
        return card

    def _sidebar_status_row(self, label: str) -> QFrame:
        row = QFrame()
        row.setObjectName("SidebarStatusRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        title = QLabel(label)
        title.setObjectName("CardTitle")
        value = QLabel("offline")
        value.setObjectName("StatusValue")
        value.setProperty("compact", True)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title, 1)
        layout.addWidget(value)
        return row

    def _set_sidebar_panel_expanded(self, button: QPushButton, body: QWidget, expanded: bool) -> None:
        button.blockSignals(True)
        try:
            button.setChecked(expanded)
            button.setProperty("expanded", expanded)
            button.style().unpolish(button)
            button.style().polish(button)
        finally:
            button.blockSignals(False)
        body.setVisible(expanded)

    def _toggle_sidebar_update_panel(self, checked: bool = False) -> None:
        self.sidebar_update_expanded = bool(checked)
        self._set_sidebar_panel_expanded(
            self.sidebar_update_toggle,
            self.sidebar_update_body,
            self.sidebar_update_expanded,
        )

    def _toggle_sidebar_services_panel(self, checked: bool = False) -> None:
        self.sidebar_services_expanded = bool(checked)
        self.sidebar_services_user_toggled = True
        self._set_sidebar_panel_expanded(
            self.sidebar_services_toggle,
            self.sidebar_services_body,
            self.sidebar_services_expanded,
        )


    def _command_button(self, label: str, callback: Callable[[], object], *, role: str = "secondary") -> QPushButton:
        button = QPushButton(label)
        object_name = {
            "primary": "PrimaryButton",
            "danger": "DangerButton",
        }.get(role, "CommandButton")
        button.setObjectName(object_name)
        button.clicked.connect(lambda _checked=False: callback())
        return button

    def _tool_button(self, label: str, callback: Callable[[], object]) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("ToolButton")
        button.clicked.connect(lambda _checked=False: callback())
        return button

    def _pet_toggle_button(self, action: str, label: str, *, object_name: str = "ToggleButton") -> QPushButton:
        button = QPushButton(label)
        button.setObjectName(object_name)
        button.setCheckable(True)
        button.clicked.connect(
            lambda checked=False, action=action: self._set_pet_toggle_from_menu(action, checked)
        )
        self.pet_toggle_buttons[action] = button
        return button

    def _set_page(self, key: str) -> None:
        if key in self.settings_nav_keys or key in {
            "workspace",
            "memory",
            "chat-memory",
            "diagnostics",
            "sources",
        }:
            self._open_settings_dialog(key)
            return

        stack_key = key if key in self.main_nav_keys else "chat"
        self.work_companion.set_page(stack_key)
        if stack_key == "chat" and self.chat_blank_draft_active:
            QTimer.singleShot(150, self._ensure_auto_empty_chat)
        elif stack_key == "today":
            self.today_page.refresh()
        elif stack_key == "schedule":
            self.schedule_page.refresh()

    def _refresh_profile_controls(self) -> None:
        combos = [
            combo
            for combo in [
                getattr(self, "character_combo", None),
                getattr(self, "project_combo", None),
                getattr(self, "outfit_combo", None),
                getattr(self, "thinking_combo", None),
                getattr(self, "chat_thinking_combo", None),
                getattr(self, "model_combo", None),
            ]
            if combo is not None
        ]
        for combo in combos:
            combo.blockSignals(True)
        self.character_combo.clear()
        self.project_combo.clear()
        for key, record in self.controller.character_records.items():
            self.character_combo.addItem(f"{record.conf_name} · {record.yaml_path.name}", key)
        for key, project in self.controller.project_records.items():
            self.project_combo.addItem(f"{project.display_name} · {project.project_id}", key)
        self._set_combo_by_data(self.character_combo, self.controller.selected_character_key)
        self._set_combo_by_data(self.project_combo, self.controller.selected_project_key)
        self._set_combo_by_data(self.outfit_combo, self.controller.outfit_id)
        self._sync_thinking_combos(self.controller.thinking_power)
        self._set_combo_by_data(self.model_combo, self.controller.llm_model)
        for combo in combos:
            combo.blockSignals(False)

    def _populate_thinking_combo(self, combo: QComboBox) -> None:
        combo.addItem("快速", "fast")
        combo.addItem("普通", "normal")
        combo.addItem("深度", "deep")

    def _sync_thinking_combos(self, value: str) -> None:
        for combo_name in ("thinking_combo", "chat_thinking_combo"):
            combo = getattr(self, combo_name, None)
            if combo is None:
                continue
            self._set_combo_by_data(combo, value)

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _on_character_changed(self, _index: int = -1) -> None:
        self.controller.set_selected_character(str(self.character_combo.currentData() or ""))
        self._set_combo_by_data(self.project_combo, self.controller.selected_project_key)
        self._refresh_workspace_data()

    def _on_model_changed(self, _index: int = -1) -> None:
        self.controller.set_llm_model(str(self.model_combo.currentData() or ""))
        self._set_action_status("模型選擇尚未套用；按「套用助理設定」後才會切換服務。")

    def _profile_selection(self) -> tuple:
        return (self.controller.selected_character_key, self.controller.selected_project_key,
                self.controller.llm_model, self.controller.thinking_power)

    def _confirm_profile_apply(self) -> bool:
        if self._profile_applying or self._chat_response_active() or self.chat_client.history_pending:
            self._set_action_status("請先完成目前對話／History 操作，再切換助理。", error=True)
            return False
        character, project = self.controller.selected_character(), self.controller.selected_project()
        if not character or not project:
            self._set_action_status("請先選擇角色與專案。", error=True)
            return False
        selection = self._profile_selection()
        description = (f"套用助理設定？可能重新載入 Conversation 與語音依賴。\n\n"
            f"角色：{character.conf_name} ({character.conf_uid})\n專案：{project.display_name}\n"
            f"模型：{selection[2]}\n推理：{selection[3]}")
        if QMessageBox.question(self, "套用助理設定", description,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        if selection != self._profile_selection():
            self._set_action_status("設定已變更，這次確認已失效。", error=True)
            return False
        self._profile_target = (character.conf_uid, project.project_id, selection[2], selection[3])
        self._profile_previous_context = self.chat_client.context_id
        self._profile_owner_done = False
        self._profile_apply_token = uuid.uuid4().hex
        self._set_profile_applying(True)
        token = self._profile_apply_token
        self._start_profile()
        QTimer.singleShot(90000, lambda: self._expire_profile_apply(token))
        return True

    def _set_profile_applying(self, busy: bool) -> None:
        self._profile_applying = busy
        for name in ("character_combo", "project_combo", "model_combo", "thinking_combo", "chat_thinking_combo"):
            getattr(self, name).setEnabled(not busy)
        self._history_controls_changed()

    def _reconcile_profile_apply(self) -> None:
        if not self._profile_applying or not getattr(self, "_profile_owner_done", False):
            return
        actual = (self.chat_client.conf_uid, self.chat_client.active_project_id,
                  self.chat_client.effective_model, self.chat_client.thinking_power)
        if actual == self._profile_target and self.chat_client.context_id != self._profile_previous_context:
            self._set_profile_applying(False)
            self._set_action_status("助理設定已由 Conversation 確認生效。")
        else:
            self._set_action_status("Launcher 已回應；仍等待 Conversation 確認角色、專案、模型與推理。")

    def _expire_profile_apply(self, token: str) -> None:
        if self._profile_applying and token == getattr(self, "_profile_apply_token", ""):
            self._set_profile_applying(False)
            self._set_action_status("助理設定的生效狀態未確認；請重新連線／查看診斷，勿視為套用成功。", error=True)

    def _on_project_changed(self, _index: int = -1) -> None:
        self.controller.set_selected_project(str(self.project_combo.currentData() or ""))
        self._refresh_workspace_data()

    def _on_outfit_changed(self, _index: int = -1) -> None:
        self.controller.set_outfit(str(self.outfit_combo.currentData() or "normal"))
        self._update_preview_asset()

    def _on_thinking_changed(self, _index: int = -1) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            combo = self.thinking_combo
        previous = self.controller.thinking_power
        self.controller.set_thinking_power(str(combo.currentData() or "normal"))
        for combo_name in ("thinking_combo", "chat_thinking_combo"):
            peer = getattr(self, combo_name, None)
            if peer is None or peer is combo:
                continue
            peer.blockSignals(True)
            self._set_combo_by_data(peer, self.controller.thinking_power)
            peer.blockSignals(False)
        self._update_project_detail()
        if combo is self.chat_thinking_combo:
            if not self._confirm_profile_apply():
                self.controller.set_thinking_power(previous)
                for peer in (self.thinking_combo, self.chat_thinking_combo):
                    peer.blockSignals(True)
                    self._set_combo_by_data(peer, previous)
                    peer.blockSignals(False)

    def _reload_profiles(self) -> None:
        self.controller.reload_profiles()
        self._refresh_profile_controls()
        self._refresh_workspace_data()

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
        if self._web_mode:
            self.chat_auto_connect_paused = False
            self._run_task("start-profile", self.controller.start_profile)
            return
        desired_history_uid = self.pending_history_uid
        force_new_history = self.pending_force_new_history
        self._discard_auto_empty_history_if_safe("__profile_restart__")
        self.chat_auto_connect_paused = False
        self._clear_auto_empty_history_marker(allow_recreate=True)
        self._run_task(
            "start-profile",
            lambda: self.controller.start_profile(
                desired_history_uid=desired_history_uid,
                force_new_history=force_new_history,
            ),
        )

    def _refresh_workspace_data(self) -> None:
        self._update_character_detail()
        self._update_project_detail()
        self._update_preview_asset()
        self._refresh_prompt_boxes()
        self._refresh_history_list()
        self._refresh_memory_list()

    def _update_character_detail(self) -> None:
        character = self.controller.selected_character()
        project = self.controller.selected_project()
        if not character:
            self.character_detail.setText("尚未選擇角色。")
            return
        self.character_detail.setText(
            "\n".join(
                [
                    f"conf_name: {character.conf_name}",
                    f"conf_uid: {character.conf_uid or '-'}",
                    f"live2d_model: {character.live2d_model_name or '-'}",
                    f"default_project_id: {character.default_project_id or '-'}",
                    f"project: {project.display_name if project else '-'}",
                ]
            )
        )

    def _update_project_detail(self) -> None:
        project = self.controller.selected_project()
        if not project:
            self.project_detail.setText("尚未選擇專案。")
            return
        self.project_detail.setText(
            "\n".join(
                [
                    f"display_name: {project.display_name}",
                    f"project_id: {project.project_id}",
                    f"project_root: {project.project_root}",
                    f"project_prompt: {project.project_prompt_path}",
                    f"tool_prompt: {project.tool_prompt_path}",
                    f"thinking_power: {self.controller.thinking_power}",
                    f"notes: {project.notes or '-'}",
                ]
            )
        )

    def _update_preview_asset(self) -> None:
        self._request_preview_asset_refresh()

    def _request_preview_asset_refresh(self) -> None:
        if self.preview_refresh_inflight:
            self.preview_refresh_pending = True
            return
        self.preview_refresh_inflight = True
        self._run_task("preview-asset", self.controller.preview_asset, quiet=True)

    def _apply_preview_asset(self, asset: PreviewAsset) -> None:
        self.preview_original_pixmap = QPixmap()
        if asset.path:
            pixmap = QPixmap(asset.path)
            if not pixmap.isNull():
                self.preview_original_pixmap = pixmap
                self.preview_fit_mode = True
                self.preview_zoom = 1.0
                self.preview_meta.setText(f"{asset.kind} · {asset.path}")
                self._render_preview_pixmap()
                return
        self.preview_image_label.setPixmap(QPixmap())
        self.preview_image_label.setText(asset.error or "這個角色目前沒有可直接顯示的預覽圖")
        self.preview_image_label.setMinimumSize(560, 360)
        self.preview_image_label.resize(560, 360)
        self.preview_meta.setText(asset.kind or "")
        self.preview_zoom_label.setText("Fit")

    def _preview_fit(self) -> None:
        self.preview_fit_mode = True
        self._render_preview_pixmap()

    def _preview_actual_size(self) -> None:
        self.preview_fit_mode = False
        self.preview_zoom = 1.0
        self._render_preview_pixmap()

    def _preview_zoom_in(self) -> None:
        self._set_preview_zoom(self.preview_zoom * 1.25)

    def _preview_zoom_out(self) -> None:
        self._set_preview_zoom(self.preview_zoom / 1.25)

    def _set_preview_zoom(self, zoom: float) -> None:
        self.preview_fit_mode = False
        self.preview_zoom = max(0.25, min(4.0, zoom))
        self._render_preview_pixmap()

    def _render_preview_pixmap(self) -> None:
        if self.preview_original_pixmap.isNull():
            return

        if self.preview_fit_mode:
            viewport_size = self.preview_scroll.viewport().size()
            max_width = max(120, viewport_size.width() - 18)
            max_height = max(120, viewport_size.height() - 18)
            scaled = self.preview_original_pixmap.scaled(
                max_width,
                max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_zoom_label.setText("Fit")
        else:
            original_size = self.preview_original_pixmap.size()
            target_width = max(1, int(original_size.width() * self.preview_zoom))
            target_height = max(1, int(original_size.height() * self.preview_zoom))
            scaled = self.preview_original_pixmap.scaled(
                target_width,
                target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_zoom_label.setText(f"{int(round(self.preview_zoom * 100))}%")

        self.preview_image_label.setPixmap(scaled)
        self.preview_image_label.setText("")
        self.preview_image_label.setMinimumSize(scaled.size())
        self.preview_image_label.resize(scaled.size())

    def _refresh_prompt_boxes(self) -> None:
        for key, box in self.prompt_boxes.items():
            preview = self.controller.read_prompt_preview(key)
            header = f"[{preview.title}]"
            if preview.source:
                header += f"\nsource: {preview.source}"
            box.setPlainText(f"{header}\n\n{preview.content}")

    def _refresh_history_list(self, records=None) -> None:
        if records is None:
            if self.chat_client.connected:
                self.chat_client.request_history_list()
            elif hasattr(self, "history_drawer"):
                self.history_drawer.set_state(ready=False, error="對話服務離線；連線後可重新讀取。")
            return
        self.history_records_by_uid = {record.uid: record for record in records if record.uid}
        self.history_drawer.set_records(records, self.chat_client.current_history_uid)
        self._update_chat_identity()
        self._history_controls_changed()






    def _show_blank_chat_draft(self) -> None:
        self.chat_blank_draft_active = True
        self.selected_history_uid = ""
        self.chat_base_transcript = ""
        self.chat_live_blocks = []
        self._chat_history_rows = []
        self._chat_tool_rows = {}
        if hasattr(self, "history_list"):
            self.history_list.blockSignals(True)
            try:
                self.history_list.clearSelection()
                self.history_list.setCurrentRow(-1)
            finally:
                self.history_list.blockSignals(False)
        if hasattr(self, "history_transcript"):
            self.history_transcript.clear()
        if hasattr(self, "chat_context"):
            self.chat_context.hide()


    def _runtime_chat_url(self) -> str:
        return f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws?client_role=qt-primary"

    def _connect_chat(self, *, auto: bool = False) -> None:
        ws_url = self._runtime_chat_url()
        if not auto:
            self.chat_auto_connect_paused = False
        self.chat_client.connect_to(ws_url)
        if self._web_mode: return
        prefix = "Runtime Chat auto connecting" if auto else "Runtime Chat connecting"
        self._set_chat_status(f"{prefix}: {ws_url}", error=False)

    def _disconnect_chat(self) -> None:
        self.chat_auto_connect_paused = True
        self.chat_client.disconnect()
        self._set_chat_status("Runtime Chat 已斷線。", error=True)

    def _interrupt_chat(self) -> None:
        sent = self.chat_client.send_interrupt()
        if sent:
            self._append_log(f"[{log_ts()}] 已送出 Runtime Chat 中斷。")
        else:
            self._set_chat_status("聊天 WebSocket 尚未連線，中斷未送出。", error=True)
        self._update_chat_send_button()

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

    def _ensure_auto_empty_chat(self) -> None:
        if not self.chat_client.history_ready or self.chat_client.history_pending:
            return
        if self.chat_auto_empty_started:
            return
        self.chat_auto_empty_started = self.chat_client.request_history_list()
        self.chat_auto_empty_create_pending = False
        if self.chat_blank_draft_active:
            self._set_chat_status("Runtime Chat 已連線。初始草稿尚未儲存；送出第一則訊息後才會建立對話。", error=False)

    def _history_is_empty(self, history_uid: str) -> bool:
        record = self.history_records_by_uid.get(history_uid)
        return bool(record is not None and record.is_empty)

    def _clear_auto_empty_history_marker(self, *, allow_recreate: bool = False) -> None:
        self.chat_auto_empty_history_uid = ""
        self.chat_auto_empty_create_pending = False
        if allow_recreate:
            self.chat_auto_empty_started = False

    def _discard_auto_empty_history_if_safe(self, next_history_uid: str = "", *, allow_recreate: bool = False) -> bool:
        # A blank draft is never persisted automatically; deletion always needs a user confirmation.
        return False

    def _release_auto_empty_history_marker(self, history_uid: str = "") -> None:
        auto_uid = self.chat_auto_empty_history_uid
        history_uid = (history_uid or "").strip()
        if not auto_uid or not history_uid:
            return
        if history_uid != auto_uid:
            return
        self._clear_auto_empty_history_marker(allow_recreate=False)
        self._append_log(f"[{log_ts()}] 暫存空白聊天已轉為正式聊天：{auto_uid}")

    def _current_auto_empty_history_for_send(self) -> str:
        auto_uid = self.chat_auto_empty_history_uid
        if not auto_uid:
            return ""
        if self.selected_history_uid == auto_uid or self.chat_client.current_history_uid == auto_uid:
            return auto_uid
        return ""


    def _show_chat_add_menu(self) -> None:
        menu = self._build_chat_add_menu()
        menu.exec(self.chat_attach_button.mapToGlobal(self.chat_attach_button.rect().topLeft()))

    def _build_chat_add_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("ChatAddMenu")

        attach_action = menu.addAction("附加檔案")
        attach_action.triggered.connect(lambda _checked=False: self._add_chat_attachments())

        menu.addSeparator()
        controls_label = menu.addAction("桌寵功能")
        controls_label.setEnabled(False)

        state_by_action = self._chat_menu_toggle_states()
        recording = bool(self.last_status and self.last_status.mic_enabled)
        for action, title in (("start", "開始錄音"), ("pause", "暫停錄音"), ("resume", "繼續錄音"),
                              ("submit", "完成錄音並送出"), ("cancel", "取消錄音")):
            control = menu.addAction(title)
            peer = self.microphone_buttons[action]
            control.setEnabled(peer.isEnabled())
            control.setToolTip(peer.toolTip())
            control.triggered.connect(lambda _checked=False, action=action: self._microphone_action(action))
        for label, action_key in [
            ("Camera", "toggle-camera"),
            ("Screen", "toggle-screen"),
        ]:
            toggle_action = menu.addAction(label)
            toggle_action.setCheckable(True)
            toggle_action.setChecked(bool(state_by_action.get(action_key, False)))
            available = bool(self.last_status and self.last_status.capture_available)
            toggle_action.setEnabled(available)
            toggle_action.setToolTip("" if available else "Pet 擷取能力尚未就緒。")
            toggle_action.triggered.connect(
                lambda checked=False, action_key=action_key: self._set_pet_toggle_from_menu(
                    action_key,
                    checked,
                )
            )

        menu.addSeparator()
        show_pet_action = menu.addAction("顯示桌寵")
        show_pet_action.triggered.connect(
            lambda _checked=False: self._run_task("pet-show", self.controller.show_pet)
        )
        stop_action = menu.addAction("停止輸出")
        stop_action.triggered.connect(
            lambda _checked=False: self._interrupt_chat()
        )

        return menu

    def _chat_menu_toggle_states(self) -> dict[str, bool]:
        status = self.last_status
        if status is None:
            return {}
        return {
            "mic-toggle": status.mic_enabled,
            "toggle-camera": status.camera_enabled,
            "toggle-screen": status.screen_enabled,
        }

    def _set_pet_toggle_from_menu(self, action: str, checked: bool) -> None:
        if not self.last_status or not self.last_status.pet_shell:
            self._set_action_status("Pet 尚未連線，操作未送出。", error=True)
            return
        if action in {"toggle-camera", "toggle-screen"} and checked:
            identity = self.chat_client.history_identity()
            if QMessageBox.question(self, "啟用感知輸入",
                    "啟用鏡頭／畫面擷取？下次明確送出的訊息可能包含此影像。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                self._sync_pet_controls(self.last_status)
                return
            if identity != self.chat_client.history_identity():
                self._set_chat_status("對話已切換，感知確認已失效。", error=True)
                return
        self._run_task(
            f"pet-toggle:{action}",
            lambda action=action, checked=checked: self.controller.set_pet_toggle(action, checked),
        )

    def _microphone_action(self, action: str) -> None:
        if action not in self.microphone_buttons or not self.microphone_buttons[action].isEnabled():
            return
        if getattr(self, "_mic_command_inflight", False):
            return
        identity = self.chat_client.history_identity()
        if action == "start":
            if QMessageBox.question(self, "開始錄音", "開始本機錄音？只有按下「完成並送出」才會交給目前對話。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            if identity != self.chat_client.history_identity():
                self._set_chat_status("角色或對話已切換，錄音未開始。", error=True)
                return
            self._capture_identity = identity
        if action == "submit" and identity != getattr(self, "_capture_identity", None):
            self._set_chat_status("錄音所屬對話已變更，請取消後重新錄音。", error=True)
            return
        self._mic_command_inflight = True
        for control in self.microphone_buttons.values():
            control.setEnabled(False)
        self._run_task("microphone:" + action, lambda: self.controller.run_pet_command("mic-" + action))

    def _add_chat_attachments(self) -> None:
        if len(self.chat_attachments) >= MAX_CHAT_ATTACHMENTS:
            QMessageBox.information(self, "Runtime Chat", "附件已達上限。")
            return
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "選擇要附加的檔案",
            str(self.cfg.root),
            "All files (*.*)",
        )
        if not paths:
            return

        skipped: list[str] = []
        for raw_path in paths:
            if len(self.chat_attachments) >= MAX_CHAT_ATTACHMENTS:
                skipped.append("已達附件上限，只附加前 6 個檔案。")
                break
            path = Path(raw_path)
            try:
                size = path.stat().st_size
            except OSError as exc:
                skipped.append(f"{path.name}: {exc}")
                continue
            try:
                payload = self._build_chat_attachment(path, size)
            except (OSError, ValueError) as exc:
                skipped.append(f"{path.name}: {exc}")
                continue
            self.chat_attachments.append(payload)

        self._render_chat_attachments()
        if skipped:
            QMessageBox.information(self, "Runtime Chat", "\n".join(dict.fromkeys(skipped)))

    def _clear_chat_attachments(self) -> None:
        self.chat_attachments = []
        self._render_chat_attachments()

    def _remove_chat_attachment(self, index: int) -> None:
        if 0 <= index < len(self.chat_attachments):
            self.chat_attachments.pop(index)
            self._render_chat_attachments()

    def _build_chat_attachment(self, path: Path, size: int) -> dict:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        kind = self._classify_chat_attachment(path, mime_type)
        limit_mib = CHAT_ATTACHMENT_LIMIT_MIB[kind]
        limit = limit_mib * 1024 * 1024
        if size > limit:
            raise ValueError(f"此類附件上限為 {limit_mib} MiB")
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError(f"此類附件上限為 {limit_mib} MiB")
        if not raw:
            raise ValueError("附件內容為空")
        data = base64.b64encode(raw).decode("ascii")
        return {
            "kind": kind,
            "name": path.name,
            "size": len(raw),
            "mime_type": mime_type,
            "data": f"data:{mime_type};base64,{data}",
        }

    def _classify_chat_attachment(self, path: Path, mime_type: str) -> str:
        normalized = mime_type.lower()
        if normalized.startswith("image/"):
            return "image"
        if normalized.startswith("audio/"):
            return "audio"
        extension = path.suffix.lower()
        if extension in {
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".html",
            ".css",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".txt",
            ".csv",
            ".log",
        }:
            return "code" if extension not in {".txt", ".md", ".csv", ".log"} else "text"
        if extension in {".zip", ".tar", ".tgz", ".gz"}:
            return "archive"
        return "file"

    def _render_chat_attachments(self) -> None:
        if not hasattr(self, "chat_attachment_layout"):
            return
        self._clear_layout(self.chat_attachment_layout)
        if not self.chat_attachments:
            self.chat_attachment_tray.setVisible(False)
            return
        self.chat_attachment_tray.setVisible(True)
        for index, item in enumerate(self.chat_attachments):
            chip = QFrame()
            chip.setObjectName("AttachmentChip")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(10, 5, 6, 5)
            chip_layout.setSpacing(6)
            name = QLabel(str(item.get("name") or "file"))
            name.setObjectName("AttachmentChipLabel")
            chip_layout.addWidget(name)
            remove = QPushButton("x")
            remove.setObjectName("AttachmentRemoveButton")
            remove.setToolTip("移除附件")
            remove.clicked.connect(lambda _checked=False, item_index=index: self._remove_chat_attachment(item_index))
            chip_layout.addWidget(remove)
            self.chat_attachment_layout.addWidget(chip)
        self.chat_attachment_layout.addStretch()

    def _visible_chat_input_text(self, text: str, attachments: list[dict]) -> str:
        names = [str(item.get("name") or "file") for item in attachments]
        attachment_line = f"附件：{', '.join(names)}" if names else ""
        return "\n".join(part for part in [text, attachment_line] if part).strip()

    def _send_or_interrupt_chat(self) -> None:
        if self._chat_response_active():
            self._interrupt_chat()
            return
        self._send_chat_text()

    def _chat_response_active(self) -> bool:
        state = str(self.chat_runtime_state or "").strip().lower()
        if state in {"thinking", "speaking", "thinking/speaking"}:
            return True
        return any(token in state for token in ("thinking", "speaking", "思考", "說話", "说话"))

    def _update_chat_send_button(self) -> None:
        if not hasattr(self, "chat_send_button"):
            return
        busy = self._chat_response_active()
        self.chat_send_button.setText("停止" if busy else "送出")
        self.chat_send_button.setToolTip("中斷這次回覆" if busy else "送出")
        self.chat_send_button.setEnabled(busy or (
            self.chat_client.history_ready and not self.pending_chat_submit
            and not self.chat_client.history_pending and not getattr(self, "_profile_applying", False)))
        self.chat_send_button.setProperty("busy", busy)
        self.chat_send_button.style().unpolish(self.chat_send_button)
        self.chat_send_button.style().polish(self.chat_send_button)

    def _send_chat_text(self) -> None:
        if (not self.chat_client.history_ready or self.pending_chat_submit or self._chat_response_active() or self.chat_client.history_pending
                or getattr(self, "_profile_applying", False)):
            return
        text = self.chat_input.toPlainText().strip()
        attachments = list(self.chat_attachments)
        if not text and not attachments:
            return
        status = getattr(self, "last_status", None)
        if status and (status.camera_enabled or status.screen_enabled):
            self.pending_chat_submit = {"text": text, "attachments": attachments,
                                        "capture_pending": True,
                                        "identity": self.chat_client.history_identity(),
                                        "history_uid": self.chat_client.current_history_uid}
            self._update_chat_send_button()
            self._run_task("chat-capture", lambda: self.controller.run_pet_command("capture-input"))
            return
        self._queue_chat_submit(text, attachments)

    def _queue_chat_submit(self, text: str, attachments: list[dict], capture: dict | None = None) -> None:
        create_history = bool(self.chat_blank_draft_active and not self.selected_history_uid)
        if not self.chat_client.history_ready:
            self._set_chat_status("Runtime Chat 尚未就緒，請先啟動 Profile。", error=True)
            return
        self.pending_chat_submit = {
            "text": text, "attachments": attachments, "capture": capture,
            "auto_empty_history_uid": self._current_auto_empty_history_for_send(),
            "draft_create_history": create_history,
            "identity": self.chat_client.history_identity(),
        }
        self._update_chat_send_button()
        if create_history:
            if not self.chat_client.create_history(force_new=True):
                self.pending_chat_submit = None
                self._update_chat_send_button()
            return
        self._submit_pending_chat()

    def _submit_pending_chat(self) -> None:
        pending = self.pending_chat_submit
        if not pending:
            return
        self.pending_chat_submit = None
        identity = pending.get("identity")
        current_identity = self.chat_client.history_identity()
        if identity is not None and (identity[:3] != current_identity[:3]
                or (not pending.get("draft_create_history") and identity != current_identity)):
            self._set_chat_status("角色或對話已變更，訊息未送出；草稿仍保留。", error=True)
            self._update_chat_send_button()
            return
        text, attachments = pending["text"], pending["attachments"]
        sent = (self.chat_client.send_capture(pending["capture"], attachments)
                if pending.get("capture") else self.chat_client.send_text(text, attachments))
        if not sent:
            self._update_chat_send_button()
            return
        self.chat_input.setPlainText("")
        self.chat_attachments = []
        self._render_chat_attachments()
        self.chat_blank_draft_active = False
        self.chat_runtime_state = "thinking"
        self._release_auto_empty_history_marker(str(pending.get("auto_empty_history_uid") or ""))
        self.chat_live_blocks.append(("User", self._chat_timestamp(), self._visible_chat_input_text(text, attachments)))
        self.chat_live_blocks.append(("Kuro", self._chat_timestamp(), ""))
        self._render_chat_transcript_with_live()
        self._update_chat_send_button()
        self._set_chat_status("已送出到 Runtime，等待回覆。", error=False)

    def _on_chat_protocol_message(self, payload: dict) -> None:
        kind = payload.get("type")
        if kind == "history-list":
            self._history_error = ""
            self._history_list_loaded = True
            records = [HistoryRecord(uid=str(item.get("uid") or ""), title=str(item.get("title") or ""),
                preview=self.controller._normalize_history_message_content(item.get("last_preview") or
                    item.get("summary_short") or item.get("preview") or
                    ((item.get("latest_message") or {}).get("content")
                     if isinstance(item.get("latest_message") or {}, dict) else item.get("latest_message")) or ""),
                timestamp=str(item.get("timestamp") or ""), is_empty=bool(item.get("is_empty", False)))
                for item in payload.get("histories", []) if isinstance(item, dict)]
            self._refresh_history_list(records=records)
            current = self.chat_client.current_history_uid
            if current and not self.selected_history_uid and not self._chat_response_active():
                self.chat_client.select_history(current)
        elif kind == "history-data":
            if payload.get("history_uid") != self.chat_client.current_history_uid:
                return
            rows = payload.get("timeline")
            if not isinstance(rows, list):
                self._on_chat_error("Conversation 未提供正式 timeline，訊息尚未載入。")
                return
            self._history_error = ""
            self._chat_history_rows = [(str(row.get("role") or "event"), str(row.get("timestamp") or ""),
                self.controller._normalize_history_message_content(row.get("content")))
                for row in rows if isinstance(row, dict)]
            self.chat_live_blocks = []
            self._chat_tool_rows = {}
            self._render_chat_transcript_with_live()
            if self._history_selection_user_requested:
                self.chat_input.clear()
                self.chat_context.hide()
                self._clear_chat_attachments()
                self.chat_host.show_history(False)
                self._history_selection_user_requested = False
            self._update_chat_identity()
            limit = payload.get("timeline_limit")
            if isinstance(limit, int) and len(rows) >= limit:
                self._set_chat_status(f"顯示最近 {limit} 則訊息與事件；較早內容尚未提供分頁讀取。", error=False)
        elif kind == "new-history-created":
            self._chat_history_rows = []
            self.chat_live_blocks = []
            self._chat_tool_rows = {}
            self.chat_base_transcript = ""
            self._render_chat_transcript_with_live()
            if self.pending_chat_submit and self.pending_chat_submit.get("draft_create_history"):
                self._submit_pending_chat()
            else:
                self.chat_input.clear()
                self._clear_chat_attachments()
            self.chat_host.show_history(False)
            self._refresh_history_list()
        elif kind == "history-deleted":
            if payload.get("success"):
                if payload.get("history_uid") == self.selected_history_uid:
                    self._show_blank_chat_draft()
                self._refresh_history_list()
            else:
                self._on_chat_error("對話刪除未完成，訊息與事件可能只刪除一部分；請重新讀取後確認。")
        elif kind == "history-error":
            self._history_selection_user_requested = False
        elif kind == "tool_call_status":
            tool_id = str(payload.get("tool_id") or "")
            if not tool_id:
                return
            name = str(payload.get("tool_name") or "工具")
            state = str(payload.get("status") or "未提供")
            content = f"{name} · {state}"
            index = self._chat_tool_rows.get(tool_id)
            block = ("Event", str(payload.get("timestamp") or ""), content)
            if index is None:
                self._chat_tool_rows[tool_id] = len(self.chat_live_blocks)
                self.chat_live_blocks.append(block)
            else:
                self.chat_live_blocks[index] = block
            self._render_chat_transcript_with_live()
        self._history_controls_changed()


    def _create_chat_history(self) -> None:
        if (self.pending_chat_submit or self._chat_response_active()
                or getattr(self, "_profile_applying", False)):
            return
        if not self.chat_client.connected:
            self._set_chat_status("對話服務尚未連線；新對話未建立。", error=True)
            return
        self.chat_client.create_history(force_new=True)

    def _clear_pending_history_choice(self) -> None:
        self.pending_history_uid = ""
        self.pending_force_new_history = False

    def _set_chat_status(self, text: str, *, error: bool = False) -> None:
        if not hasattr(self, "chat_connection_status"):
            return
        self.chat_connection_status.setText(text)
        self.chat_connection_status.setVisible(True)
        self.chat_connection_status.setProperty("error", error)
        self.chat_connection_status.style().unpolish(self.chat_connection_status)
        self.chat_connection_status.style().polish(self.chat_connection_status)

    def _on_chat_state_changed(self, state: str, connected: bool) -> None:
        self.chat_runtime_state = state
        if state == "offline":
            self.pending_chat_submit = None
            self.chat_auto_empty_started = False
        self._update_chat_send_button()
        self._history_controls_changed()
        label = {
            "connecting": "Runtime Chat 連線中。",
            "connected": "Runtime Chat 已連線。",
            "offline": "Runtime Chat 離線。",
            "thinking": "Runtime Chat 思考中。",
            "speaking": "Runtime Chat 回覆中。",
            "idle": "Runtime Chat idle。",
            "interrupted": "Runtime Chat 已中斷。",
        }.get(state, f"Runtime Chat: {state}")
        if connected and self.chat_client.client_uid:
            label += f" client={self.chat_client.client_uid[:8]}"
        self._set_chat_status(label, error=not connected and state in {"offline"})
        if hasattr(self, "work_companion"):
            self.work_companion.runtime_status.setText(label)
        if connected and state == "connected":
            QTimer.singleShot(150, self._ensure_auto_empty_chat)
        elif connected and state == "idle" and self.chat_client.current_history_uid:
            QTimer.singleShot(0, lambda: self.chat_client.select_history(self.chat_client.current_history_uid)
                              if not self.chat_client.history_pending else None)

    def _on_chat_client_changed(self, client_uid: str, conf_name: str, conf_uid: str) -> None:
        self.pending_chat_submit = None
        self._history_error = ""
        self._history_selection_user_requested = False
        self.history_records_by_uid = {}
        self._history_list_loaded = False
        self.history_drawer.set_records([], "")
        self.chat_auto_empty_started = False
        self._show_blank_chat_draft()
        self._update_chat_identity()
        self._history_controls_changed()
        self._set_chat_status(f"對話已連線 · {conf_name or conf_uid}，正在確認對話紀錄。")
        self._reconcile_profile_apply()
        QTimer.singleShot(0, self._ensure_auto_empty_chat)

    def _on_chat_error(self, message: str) -> None:
        self._history_error = message
        self.pending_chat_submit = None
        self._update_chat_send_button()
        self._append_log(f"[{log_ts()}] Runtime Chat error: {message}")
        self._set_chat_status(f"Runtime Chat 錯誤：{message}", error=True)
        if hasattr(self, "history_drawer"):
            self.history_drawer.set_state(ready=self.chat_client.history_ready, error=message)

    def _on_chat_history_changed(self, history_uid: str, _title: str) -> None:
        self.selected_history_uid = history_uid
        self.chat_blank_draft_active = not bool(history_uid)
        if not history_uid:
            self._show_blank_chat_draft()
        if hasattr(self, "history_drawer"):
            self._update_chat_identity()

    def _on_chat_assistant_text_changed(self, text: str) -> None:
        if not text:
            return
        for index in range(len(self.chat_live_blocks) - 1, -1, -1):
            role, timestamp, _old = self.chat_live_blocks[index]
            if role == "Kuro":
                self.chat_live_blocks[index] = (role, timestamp, text)
                break
            if role == "User":
                self.chat_live_blocks.append(("Kuro", self._chat_timestamp(), text))
                break
        else:
            self.chat_live_blocks.append(("Kuro", self._chat_timestamp(), text))
        self._render_chat_transcript_with_live()

    def _render_chat_transcript_with_live(self) -> None:
        bar = self.history_transcript.verticalScrollBar()
        near_bottom = bar.maximum() - bar.value() < 120
        previous = bar.value()
        rows = list(getattr(self, "_chat_history_rows", []))
        rows.extend((role, timestamp, content or ("正在整理回覆…" if role == "Kuro" else ""))
                    for role, timestamp, content in self.chat_live_blocks)
        self.history_transcript.setHtml(transcript_html(rows, compact=self.compact_control.isChecked()))
        bar.setValue(bar.maximum() if near_bottom else min(previous, bar.maximum()))

    def _chat_timestamp(self) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _refresh_memory_list(self) -> None:
        previous_entry_id = self._selected_memory_entry_id()
        self.memory_list.blockSignals(True)
        self.memory_list.clear()
        records = self.controller.read_memory_records()
        self.memory_records_by_id = {record.entry_id: record for record in records}
        character = self.controller.selected_character()
        self.memory_review_conf_uid = character.conf_uid if character else ""
        selected_row = 0
        for record in records:
            status = MEMORY_STATUS_LABELS.get(record.status, record.status or "未知")
            item = QListWidgetItem(
                f"[{status}] ({record.memory_type})\n{record.content}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record.entry_id)
            self.memory_list.addItem(item)
            if record.entry_id == previous_entry_id:
                selected_row = self.memory_list.count() - 1
        self.memory_list.blockSignals(False)
        if records:
            self.memory_list.setCurrentRow(selected_row)
            self._render_memory_detail(str(self.memory_list.item(selected_row).data(Qt.ItemDataRole.UserRole) or ""))
        else:
            self.memory_detail.setPlainText("目前沒有角色長期記憶。")

    def _on_memory_selected(self) -> None:
        item = self.memory_list.currentItem()
        if not item:
            return
        self._render_memory_detail(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _render_memory_detail(self, entry_id: str) -> None:
        for record in self.controller.read_memory_records():
            if record.entry_id != entry_id:
                continue
            status = MEMORY_STATUS_LABELS.get(record.status, record.status or "未知")
            self.memory_detail.setPlainText(
                "\n".join(
                    [
                        f"id: {record.entry_id}",
                        f"status: {status}",
                        f"type: {record.memory_type}",
                        f"enabled: {record.enabled}",
                        f"scope: {record.scope_level}",
                        f"source: {record.source}",
                        f"updated_at: {record.updated_at or '-'}",
                        "",
                        record.content,
                    ]
                )
            )
            return
        self.memory_detail.setPlainText("找不到這條記憶。")

    def _delete_selected_history(self) -> None:
        history_uid = self.selected_history_uid
        current_item = self.history_list.currentItem()
        if current_item:
            history_uid = str(current_item.data(Qt.ItemDataRole.UserRole) or history_uid)
        self._delete_history_by_uid(history_uid)

    def _delete_history_by_uid(self, history_uid: str) -> None:
        history_uid = (history_uid or "").strip()
        if (not history_uid or not self.chat_client.history_ready or self.chat_client.history_pending
                or self._chat_response_active() or self.pending_chat_submit):
            return
        identity = self.chat_client.history_identity()
        record = self.history_records_by_uid.get(history_uid)
        title = record.title if record else history_uid
        answer = QMessageBox.question(self, "刪除聊天記錄",
            f"確定要刪除這段對話及工具事件嗎？無法復原。\n\n{title}\n{history_uid}\n角色：{identity[1]}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if identity != self.chat_client.history_identity():
            self._set_chat_status("角色或對話已切換，刪除確認已失效。", error=True)
            return
        self.chat_client.delete_history(history_uid, confirmed=True)

    def _selected_memory_entry_id(self) -> str:
        if not hasattr(self, "memory_list"):
            return ""
        item = self.memory_list.currentItem()
        if not item:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _add_memory_dialog(self) -> None:
        character = self.controller.selected_character()
        conf_uid = character.conf_uid if character else ""
        content, ok = QInputDialog.getMultiLineText(
            self,
            "新增角色記憶",
            "輸入要加入目前角色的長期記憶（每筆最多 260 字）：",
            getattr(self, "_memory_draft", ""),
        )
        if not ok:
            return
        content = content.strip()
        if not content:
            return
        self._memory_draft = content
        if len(content) > 260:
            self._set_action_status("記憶未新增：目前服務每筆最多 260 字，請縮短內容。", error=True)
            return
        if self._confirm_memory_change(conf_uid, "新增記憶", content):
            self._run_task("add-memory", lambda: self.controller.add_memory(content, expected_conf_uid=conf_uid))

    def _confirm_memory_change(self, conf_uid: str, title: str, content: str) -> bool:
        if not conf_uid or self._profile_applying:
            self._set_action_status("角色尚未選定或正在切換，記憶未變更。", error=True)
            return False
        accepted = QMessageBox.question(self, title, f"角色：{conf_uid}\n{title}？\n\n{content}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        character = self.controller.selected_character()
        if not character or conf_uid != character.conf_uid:
            self._set_action_status("角色已切換，記憶確認已失效。", error=True)
            return False
        return accepted

    def _change_selected_memory(self, action: str, status: str = "") -> None:
        entry_id = self._selected_memory_entry_id()
        record = getattr(self, "memory_records_by_id", {}).get(entry_id)
        if not record or not record.content_digest:
            self._set_action_status("請重新讀取並選擇具有內容摘要的記憶。", error=True)
            return
        conf_uid = self.memory_review_conf_uid
        if action == "toggle":
            status = "disabled" if record.status == "active" else "active"
        title = "刪除記憶（無法復原）" if action == "delete" else f"將記憶設為{MEMORY_STATUS_LABELS[status]}"
        if not self._confirm_memory_change(conf_uid, title, f"{entry_id}\n{record.content}"):
            return
        if action == "delete":
            operation = lambda: self.controller.delete_memory(entry_id, expected_conf_uid=conf_uid,
                                                               expected_digest=record.content_digest)
        else:
            operation = lambda: self.controller.set_memory_status(entry_id, status,
                expected_conf_uid=conf_uid, expected_digest=record.content_digest)
        self._run_task("delete-memory" if action == "delete" else "toggle-memory", operation)

    def _toggle_selected_memory(self) -> None:
        self._change_selected_memory("toggle")

    def _approve_selected_memory(self) -> None:
        self._change_selected_memory("status", "active")

    def _reject_selected_memory(self) -> None:
        self._change_selected_memory("status", "disabled")

    def _delete_selected_memory(self) -> None:
        self._change_selected_memory("delete")

    def _compact_memory(self) -> None:
        records = getattr(self, "memory_records_by_id", {})
        conf_uid = getattr(self, "memory_review_conf_uid", "")
        digests = {key: record.content_digest for key, record in records.items()}
        if not all(digests.values()):
            self._set_action_status("記憶內容摘要不完整，請重新讀取。", error=True)
            return
        if self._confirm_memory_change(conf_uid, "整理角色記憶",
                f"將檢查目前 {len(records)} 條記憶，合併或移除重複／過期項目。"):
            self._run_task("compact-memory", lambda: self.controller.compact_memory(
                expected_conf_uid=conf_uid, expected_digests=digests))

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
        if self._web_mode:
            self.work_web_candidate.owner_port.refresh_status()
            return
        self._run_task("status", self.controller.read_runtime_status, quiet=True)

    def _refresh_core_pages(self) -> None:
        """Refresh only visible Core consumers; never use the Pet snapshot."""
        if self.settings_surface.isVisible():
            if self.settings_stack.currentIndex() == self.settings_order.index("advanced"):
                self.core_health_page.refresh()
            return
        if not self.isVisible():
            return
        page = self.stack.currentWidget()
        if page is self.today_page:
            self.today_page.refresh()
        # Schedule refresh is explicit: periodic reads would reset selection,
        # pagination or an open editor while the user prepares a command.


    def _run_task(self, name: str, fn: Callable[[], object], *, quiet: bool = False) -> None:
        if self._cleanup_done: return
        if self._web_mode:
            self._run_web_task(name, fn)
            return
        if not quiet:
            self._append_log(f"[{log_ts()}] task start: {name}")
            self._set_action_status(f"執行中：{name}")

        def runner() -> None:
            try:
                result = fn()
            except Exception as exc:
                self.task_failed.emit(name, str(exc))
                return
            self.task_finished.emit(name, result)

        threading.Thread(target=runner, daemon=True).start()

    def _on_task_finished(self, name: str, result: object) -> None:
        if name == "start-profile" and getattr(self, "_profile_applying", False):
            self._profile_owner_done = True
            self._reconcile_profile_apply()
            self.refresh_status()
            return
        if name.startswith("microphone:"):
            self._mic_command_inflight = False
            media = result.get("result", {}) if isinstance(result, dict) else {}
            action = name.split(":", 1)[1]
            if action == "submit":
                if self.chat_client.history_identity() != getattr(self, "_capture_identity", None):
                    self._set_chat_status("角色或對話已切換，錄音未送出。", error=True)
                elif media.get("capture") and not self.pending_chat_submit and not self._chat_response_active():
                    images = [{**item, "kind": "image"} for item in media.get("images", [])]
                    self._queue_chat_submit("[語音輸入]", images, media["capture"])
                else:
                    self._set_chat_status("沒有可送出的錄音，或目前對話仍忙碌。", error=True)
            if action in {"submit", "cancel"}:
                self._capture_identity = None
            self.perception_status.setText("Pet 已回應；正在重新讀取感知狀態。")
            self.refresh_status()
            return
        if name == "chat-capture":
            pending = self.pending_chat_submit
            self.pending_chat_submit = None
            self._update_chat_send_button()
            if not pending or not pending.get("capture_pending"):
                return
            if (pending["history_uid"] != self.chat_client.current_history_uid
                    or pending.get("identity") != self.chat_client.history_identity()):
                self._set_chat_status("對話已切換，擷取內容未送出。", error=True)
                return
            media = result.get("result", {}) if isinstance(result, dict) else {}
            if media.get("ok") is not True:
                self._set_chat_status("影像擷取失敗，請重試或關閉影像輸入。", error=True)
                return
            images = [{**item, "kind": "image"} for item in media.get("images", [])]
            self._queue_chat_submit(pending["text"], pending["attachments"] + images)
            return
        if name == 'runtime-reconcile':
            return
        if name == "status" and isinstance(result, RuntimeStatus):
            self._apply_status(result)
            return
        if name == "preview-asset":
            self.preview_refresh_inflight = False
            if isinstance(result, PreviewAsset):
                self._apply_preview_asset(result)
            if self.preview_refresh_pending:
                self.preview_refresh_pending = False
                QTimer.singleShot(250, self._request_preview_asset_refresh)
            return
        self._append_log(f"[{log_ts()}] task done: {name}")
        self._set_action_status(f"已完成：{name}")
        self.refresh_status()
        if name in {"open-pet", "start-profile"}:
            self._refresh_core_pages()
        if name in {"open-pet", "start-profile", "apply-outfit"}:
            QTimer.singleShot(700, self._request_preview_asset_refresh)
            QTimer.singleShot(1800, self._request_preview_asset_refresh)
        if name == "start-profile":
            if isinstance(result, dict):
                history_result = result.get("history") if isinstance(result.get("history"), dict) else {}
                if history_result.get("ok") and not history_result.get("skipped"):
                    history_uid = str(history_result.get("history_uid") or "").strip()
                    if history_uid:
                        self.selected_history_uid = history_uid
                    self._clear_pending_history_choice()
                    self._refresh_history_list()
        if name in {"select-history", "create-history", "delete-history"}:
            if name in {"select-history", "create-history"}:
                self._clear_pending_history_choice()
                if isinstance(result, dict):
                    history_uid = str(result.get("history_uid") or "").strip()
                    if history_uid:
                        self.selected_history_uid = history_uid
            self._refresh_history_list()
        if name in {
            "refresh-memory",
            "add-memory",
            "toggle-memory",
            "approve-memory",
            "reject-memory",
            "delete-memory",
            "compact-memory",
        }:
            self._set_action_status("記憶沒有變更；可能是重複內容或已是目前狀態。"
                                    if result is False else "記憶服務已完成操作。")
            if name == "add-memory" and result is True:
                self._memory_draft = ""
            self._refresh_memory_list()
            self._refresh_prompt_boxes()
        if isinstance(result, dict) and result.get("warning"):
            QMessageBox.warning(self, "Kuro Desktop Console", str(result.get("warning")))

    def _on_task_failed(self, name: str, message: str) -> None:
        if name == "start-profile" and getattr(self, "_profile_applying", False):
            self._set_profile_applying(False)
        if name.startswith("microphone:"):
            self._mic_command_inflight = False
            self.perception_status.setText("錄音操作失敗；尚未送出。請重新讀取狀態或取消。")
        if name == "chat-capture":
            self.pending_chat_submit = None
            self._update_chat_send_button()
        if name == "preview-asset":
            self.preview_refresh_inflight = False
            self.preview_refresh_pending = False
            self._append_log(f"[{log_ts()}] preview refresh failed: {message}")
            return
        if name == "start-profile":
            self.reveal()
        self._append_log(f"[{log_ts()}] task failed: {name} / {message}")
        self._set_action_status(f"失敗：{name} / {message}", error=True)
        if name != "start-profile":
            QMessageBox.warning(self, "Kuro Desktop Console", message)
        self.refresh_status()

    def _set_action_status(self, text: str, *, error: bool = False) -> None:
        if self._web_mode:
            # Project failures without touching retired labels or inventing a
            # healthy status. Private exception payloads never enter HTML.
            if self.work_web_candidate is not None:
                self.work_web_candidate.owner_port.publish("onState", {"ok": False,
                    "error": "lifecycle_operation_failed" if error else "lifecycle_busy", "retry": False})
            return
        for label_name in ("workspace_status", "sidebar_action_status"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(text)
            label.setProperty("error", error)
            label.style().unpolish(label)
            label.style().polish(label)
        if hasattr(self, "sidebar_update_toggle"):
            status = "失敗" if error else "執行中" if text.startswith("執行中") else "完成" if text.startswith("已完成") else "Ready"
            self.sidebar_update_toggle.setText(f"更新狀態    {status}")
            self.sidebar_update_toggle.setProperty("error", error)
            if error or text.startswith("執行中"):
                self.sidebar_update_toggle.setProperty("warning", False)
            self.sidebar_update_toggle.style().unpolish(self.sidebar_update_toggle)
            self.sidebar_update_toggle.style().polish(self.sidebar_update_toggle)

    def _apply_status(self, status: RuntimeStatus) -> None:
        self.last_status = status
        values = {
            "SidebarBridge": status.bridge,
            "SidebarTTS": status.tts,
            "SidebarLLM": status.llm,
            "SidebarPet": status.pet_shell,
        }
        for key, online in values.items():
            label = self.service_labels.get(key)
            if not label:
                continue
            label.setText("online" if online else "offline")
            label.setProperty("online", online)
            label.style().unpolish(label)
            label.style().polish(label)

        if hasattr(self, "sidebar_services_toggle"):
            online_count = sum(1 for online in values.values() if online)
            service_error = online_count < len(values)
            self.sidebar_services_toggle.setText(f"服務狀態    {online_count}/{len(values)} online")
            self.sidebar_services_toggle.setProperty("error", service_error)
            self.sidebar_services_toggle.style().unpolish(self.sidebar_services_toggle)
            self.sidebar_services_toggle.style().polish(self.sidebar_services_toggle)

        ws = "connected" if status.ws_connected else "disconnected"
        if hasattr(self, "sidebar_pet_snapshot_status"):
            pet_text = "\n".join(
                [
                    f"Pet: {'online' if status.pet_shell else 'offline'} · WS {ws}",
                    f"AI: {status.ai_state or '-'} · profile {status.conf_name or '-'}",
                ]
            )
            self.sidebar_pet_snapshot_status.setText(pet_text)
            self.sidebar_pet_snapshot_status.setProperty("error", not status.pet_shell)
            self.sidebar_pet_snapshot_status.style().unpolish(self.sidebar_pet_snapshot_status)
            self.sidebar_pet_snapshot_status.style().polish(self.sidebar_pet_snapshot_status)

        if hasattr(self, "chat_settings_status"):
            self.chat_settings_status.setText(
                "\n".join(
                    [
                        f"初始草稿：{'active' if self.chat_blank_draft_active else 'formal history selected'}",
                        f"Runtime Chat：{'connected' if self.chat_client.connected else 'offline'} · auto {'paused' if self.chat_auto_connect_paused else 'enabled'}",
                    ]
                )
            )

        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.setText(
                f"Bridge {'online' if status.bridge else 'offline'} · "
                f"TTS {'online' if status.tts else 'offline'} · "
                f"LLM {'online' if status.llm else 'offline'} · "
                f"Pet {'online' if status.pet_shell else 'offline'} · WS {ws}"
            )
            self.runtime_status_label.setProperty("error", not (status.bridge and status.tts and status.llm and status.pet_shell))
            self.runtime_status_label.style().unpolish(self.runtime_status_label)
            self.runtime_status_label.style().polish(self.runtime_status_label)
        self.runtime_detail.setText(
            "\n".join(
                [
                    f"pet_mode: {status.pet_mode or '-'}",
                    f"ws_connected: {status.ws_connected}",
                    f"ai_state: {status.ai_state or '-'}",
                    f"conf_name: {status.conf_name or '-'}",
                ]
            )
        )
        self._maybe_auto_connect_chat(status)
        self._sync_pet_controls(status)
        self._maybe_refresh_preview_from_status(status)
        if hasattr(self, "workspace_status") and not status.llm:
            self._set_action_status(
                "Runtime 尚未完整在線：聊天同步、建立新聊天、刷新記憶 prompt 需要先啟動 Profile。",
                error=True,
            )

    def _maybe_refresh_preview_from_status(self, status: RuntimeStatus) -> None:
        character = self.controller.selected_character()
        if not status.pet_shell or not character:
            self.preview_status_signature = ""
            return

        selected_conf = (character.conf_name or "").strip().lower()
        active_conf = (status.conf_name or "").strip().lower()
        if active_conf and selected_conf and active_conf != selected_conf:
            return

        signature = "|".join(
            [
                selected_conf,
                status.current_outfit_id or self.controller.outfit_id,
                "ws" if status.ws_connected else "no-ws",
                "pet" if status.pet_shell else "no-pet",
            ]
        )
        if signature == self.preview_status_signature:
            return
        self.preview_status_signature = signature
        QTimer.singleShot(350, self._request_preview_asset_refresh)

    def _sync_pet_controls(self, status: RuntimeStatus) -> None:
        self.pet_reload_button.setEnabled(status.pet_shell)
        self.pet_reload_button.setToolTip("" if status.pet_shell else "需要 Pet 提供有效狀態後才能重新載入角色。")
        for panel in self.findChildren(QFrame):
            if panel.property("petControlGroup"):
                panel.setEnabled(status.pet_shell)
                panel.setToolTip("" if status.pet_shell else "Pet 尚未提供有效狀態，此操作目前不可用。")
        state_by_action = {
            "mic-toggle": status.mic_enabled,
            "toggle-camera": status.camera_enabled,
            "toggle-screen": status.screen_enabled,
            "set-game-mode": status.pet_game_mode,
            "set-live2d-inspector": status.live2d_inspector_overlay_enabled,
            "set-force-ignore-mouse": status.force_ignore_mouse,
        }
        for action, checked in state_by_action.items():
            button = self.pet_toggle_buttons.get(action)
            if not button:
                continue
            button.blockSignals(True)
            available = status.capture_available if action in {"toggle-camera", "toggle-screen"} else status.pet_shell
            button.setEnabled(available)
            button.setToolTip("" if available else "Pet 尚未提供此功能的有效狀態。")
            button.setChecked(bool(checked))
            button.setText(self._pet_toggle_label(action, bool(checked)))
            button.setProperty("checkedState", bool(checked))
            button.style().unpolish(button)
            button.style().polish(button)
            button.blockSignals(False)
        capture_text = (f"麥克風：{'暫停' if status.mic_paused else '錄音中' if status.mic_enabled else '關閉'} · "
                        f"鏡頭：{'啟用' if status.camera_enabled else '關閉'} · "
                        f"畫面：{'啟用' if status.screen_enabled else '關閉'}") if status.capture_available else "感知狀態未知：Pet 擷取能力尚未就緒。"
        self.perception_status.setText(capture_text)
        self.work_companion.privacy_status.setText(capture_text)
        busy = (getattr(self, "_mic_command_inflight", False) or self._profile_applying
                or self.chat_client.history_pending or self._chat_response_active() or bool(self.pending_chat_submit))
        active = status.mic_enabled
        for action, control in self.microphone_buttons.items():
            allowed = status.capture_available and not busy
            if action == "start":
                allowed = allowed and not active and self.chat_client.history_ready
            elif action == "cancel":
                allowed = status.capture_available and active and not getattr(self, "_mic_command_inflight", False)
            else:
                allowed = allowed and active and self.chat_client.history_ready
                if action == "pause":
                    allowed = allowed and not status.mic_paused
                elif action == "resume":
                    allowed = allowed and status.mic_paused
                elif action == "submit":
                    allowed = allowed and getattr(self, "_capture_identity", None) == self.chat_client.history_identity()
            control.setEnabled(allowed)
            control.setToolTip("" if allowed else "需要有效的 Pet 擷取狀態、錄音所屬對話及可用的 Qt Chat；可取消後重錄。")

        if status.current_expression_id and hasattr(self, "pet_expression_combo"):
            index = self.pet_expression_combo.findData(status.current_expression_id)
            if index >= 0:
                self.pet_expression_combo.blockSignals(True)
                self.pet_expression_combo.setCurrentIndex(index)
                self.pet_expression_combo.blockSignals(False)
        if status.current_outfit_id in {"normal", "hoodie"}:
            self.controller.set_outfit(status.current_outfit_id)
            for combo_name in ("outfit_combo",):
                combo = getattr(self, combo_name, None)
                if combo is None:
                    continue
                combo.blockSignals(True)
                self._set_combo_by_data(combo, status.current_outfit_id)
                combo.blockSignals(False)

        if hasattr(self, "pet_status_label"):
            if status.pet_shell:
                self.pet_status_label.setText(
                    f"Pet online · mode={status.pet_mode or '-'} · ws={'connected' if status.ws_connected else 'disconnected'} · "
                    f"expression={status.current_expression_label or status.current_expression_id or '-'}"
                )
                self.pet_status_label.setProperty("error", False)
            else:
                self.pet_status_label.setText("Pet shell 未在線。請先開桌寵 Shell 或啟動 Profile。")
                self.pet_status_label.setProperty("error", True)
            self.pet_status_label.style().unpolish(self.pet_status_label)
            self.pet_status_label.style().polish(self.pet_status_label)

        if hasattr(self, "pet_detail"):
            self.pet_detail.setText(
                "\n".join(
                    [
                        f"Input: Mic {'ON' if status.mic_enabled else 'OFF'} · Camera {'ON' if status.camera_enabled else 'OFF'} · Screen {'ON' if status.screen_enabled else 'OFF'}",
                        f"Window: Game mode {'ON' if status.pet_game_mode else 'OFF'} · Inspector {'ON' if status.live2d_inspector_overlay_enabled else 'OFF'}",
                    ]
                )
            )

    def _pet_toggle_label(self, action: str, checked: bool) -> str:
        base = {
            "mic-toggle": "Mic",
            "set-force-ignore-mouse": "滑鼠穿透",
            "toggle-camera": "Camera",
            "toggle-screen": "Screen",
            "set-game-mode": "Game mode",
            "set-live2d-inspector": "Live2D Inspector",
        }.get(action, action)
        return f"{base}  {'ON' if checked else 'OFF'}"


    def _compact_label_text(self, value: str, limit: int) -> str:
        text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 1)]}..."

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout:
                self._clear_layout(child_layout)
            if widget:
                widget.deleteLater()

    def _append_log_threadsafe(self, text: str) -> None:
        self.log_signal.emit(text)

    def _append_log(self, text: str) -> None:
        if self._web_mode:
            # Formal stdout is the existing launcher.combined.log tee. Keep
            # diagnostics local; never expose callback text to the renderer.
            print(f"[{log_ts()}] {text}", flush=True)
            return
        if not hasattr(self, "log_box"):
            return
        self.log_box.append(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "preview_fit_mode", False):
            self._render_preview_pixmap()

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


APP_STYLE = """
QMainWindow {
    background: #090b10;
    color: #e8edf7;
}
QWidget {
    font-family: __APP_FONT_STACK__;
    font-size: 13px;
    color: #e8edf7;
}
#Sidebar {
    background: #11151d;
    border-right: 1px solid #252b38;
}
#Brand {
    font-size: 24px;
    font-weight: 800;
}
#BrandSub, #PageSubtitle, #MetaText, #QuickStatus {
    color: #95a1b5;
}
#StatusBanner {
    background: #111722;
    border: 1px solid #2f3b51;
    border-radius: 8px;
    color: #cfd7e6;
    padding: 10px 12px;
}
#StatusBanner[error="true"] {
    background: #271722;
    border-color: #6a3145;
    color: #ffb4c0;
}
#StatusBanner[warning="true"] {
    background: #2b2616;
    border-color: #6a5731;
    color: #ffd38a;
}
#NavGroup {
    color: #7f8da5;
    font-size: 11px;
    font-weight: 800;
    margin-top: 8px;
    text-transform: uppercase;
}
#PageTitle {
    font-size: 28px;
    font-weight: 800;
}
#NavButton {
    background: transparent;
    color: #cfd7e6;
    border: 0;
    border-radius: 8px;
    padding: 10px 12px;
    text-align: left;
    font-weight: 700;
}
#NavButton:hover {
    background: #1a2030;
}
#NavButton:checked {
    background: #243044;
    color: #ffffff;
}
#NavButton[settingsNav="true"] {
    margin-top: 8px;
}
QDialog#SettingsDialog {
    background: transparent;
    color: #e8edf7;
}
#SettingsDialogFrame {
    background: #090b10;
    border: 1px solid #46546b;
    border-radius: 10px;
}
#SettingsDialogHead,
#SettingsDialogFoot {
    background: #10151f;
    border-bottom: 1px solid #303849;
}
#SettingsDialogHead {
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
#SettingsDialogFoot {
    border-top: 1px solid #303849;
    border-bottom: 0;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
}
#SettingsDialogTitle {
    color: #ffffff;
    font-size: 20px;
    font-weight: 850;
}
#SettingsDialogSub {
    color: #95a1b5;
    font-size: 12px;
}
#SettingsDialogBody {
    background: #090b10;
}
#SettingsDialogNav {
    background: #11151d;
    border-right: 1px solid #252b38;
}
#SettingsDialogNavButton {
    background: transparent;
    border: 0;
    border-radius: 7px;
    color: #cfd7e6;
    font-weight: 800;
    min-height: 36px;
    padding: 0 12px;
    text-align: left;
}
#SettingsDialogNavButton:hover {
    background: #1a2030;
}
#SettingsDialogNavButton:checked {
    background: #243044;
    color: #ffffff;
}
#SettingsDialogStack {
    background: #090b10;
    border: 0;
}
QScrollArea#SettingsPageScroll {
    background: transparent;
    background-color: transparent;
    border: 0;
}
#SettingsContent {
    background: #090b10;
}
#SettingsSection {
    background: #111722;
    border: 1px solid #303849;
    border-radius: 8px;
}
#SettingsSectionTitle {
    color: #ffffff;
    font-size: 14px;
    font-weight: 850;
}
#SettingsSectionSub {
    color: #95a1b5;
    font-size: 12px;
}
#SettingsRow {
    background: transparent;
    border-top: 1px solid #252d3b;
}
#SettingsRowTitle {
    color: #d9e2f2;
    font-weight: 850;
}
#SettingsRowDescription {
    color: #95a1b5;
    font-size: 12px;
}
#SettingsInfoPanel {
    background: #0f141e;
    border: 1px solid #252d3b;
    border-radius: 7px;
}
#SettingsInlineControls {
    background: transparent;
    border: 0;
}
QComboBox {
    background: #10151f;
    border: 1px solid #30394a;
    border-radius: 7px;
    color: #e8edf7;
    min-height: 34px;
    padding: 4px 10px;
}
QComboBox:hover {
    border-color: #46546b;
}
QComboBox:focus {
    border-color: #2da996;
}
QComboBox::drop-down {
    border: 0;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: #151b25;
    border: 1px solid #30394a;
    color: #e8edf7;
    selection-background-color: #1f493f;
}
#Panel, #StatusCard, #MetricCard, #SidebarStatusRow {
    background: #171c27;
    border: 1px solid #303849;
    border-radius: 8px;
}
#SidebarPanel, #SidebarStatusPanel {
    background: #171c27;
    border: 1px solid #303849;
    border-radius: 8px;
    margin-bottom: 6px;
}
#SidebarPanelToggle {
    background: transparent;
    border: 0;
    border-radius: 8px;
    color: #e4ebf8;
    font-weight: 800;
    padding: 9px 10px;
    text-align: left;
}
#SidebarPanelToggle:hover {
    background: #202838;
}
#SidebarPanelToggle:checked {
    background: #202838;
}
#SidebarPanelToggle[error="true"] {
    background: #271722;
    color: #ffb4c0;
}
#SidebarPanelToggle[warning="true"] {
    color: #ffd38a;
}
#SidebarPanelToggle[expanded="true"] {
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
}
#SidebarPanelBody {
    background: transparent;
    border: 0;
}
#SidebarActionStatus {
    background: #111722;
    border: 1px solid #2f3b51;
    border-radius: 6px;
    color: #cfd7e6;
    padding: 7px 8px;
}
#SidebarActionStatus[error="true"] {
    background: #271722;
    border-color: #6a3145;
    color: #ffb4c0;
}
#SidebarStatusDetail {
    color: #aab6ca;
    font-size: 12px;
    padding: 1px 0;
}
#SidebarStatusDetail[error="true"] {
    color: #ffb4c0;
}
#SidebarStatusDetail[warning="true"] {
    color: #ffd38a;
}
#SidebarStatusRow {
    background: #111722;
    min-height: 34px;
}
#SidebarStatusRow #CardTitle {
    font-size: 11px;
}
#StatusCard, #MetricCard {
    min-height: 68px;
}
#CardTitle, #SectionTitle, #FieldLabel {
    color: #d9e2f2;
    font-weight: 800;
}
#StatusValue {
    color: #ff6b7a;
    font-size: 18px;
    font-weight: 800;
}
#StatusValue[compact="true"] {
    font-size: 13px;
}
#StatusValue[online="true"] {
    color: #70e28a;
}
#MetricValue {
    color: #ffffff;
    font-size: 28px;
    font-weight: 800;
}
#Tag {
    color: #b9eadf;
    background: #102922;
    border: 1px solid #275748;
    border-radius: 6px;
    padding: 4px 8px;
    font-weight: 800;
}
#CommandButton {
    background: #151b25;
    border: 1px solid #323b4d;
    border-radius: 7px;
    color: #dce5f5;
    font-weight: 800;
    padding: 10px 14px;
}
#CommandButton:hover {
    background: #1d2635;
    border-color: #46546b;
}
#PrimaryButton {
    background: #218c7d;
    border: 1px solid #2da996;
    border-radius: 7px;
    color: #f3fffc;
    font-weight: 900;
    padding: 10px 14px;
}
#PrimaryButton:hover {
    background: #279f8e;
    border-color: #39c0ac;
}
#DangerButton {
    background: #1d1418;
    border: 1px solid #704152;
    border-radius: 7px;
    color: #ffbbc8;
    font-weight: 800;
    padding: 10px 14px;
}
#DangerButton:hover {
    background: #2a1720;
    border-color: #95546a;
}
#ToolButton {
    background: #151c28;
    border: 1px solid #303849;
    border-radius: 7px;
    color: #dce5f5;
    font-weight: 800;
    min-width: 44px;
    padding: 7px 10px;
}
#ToolButton:hover {
    background: #1d2635;
    border-color: #43506a;
}
#ComposerPanel {
    background: #10151f;
    border: 1px solid #303849;
    border-radius: 10px;
}
#ComposerControls {
    background: transparent;
    border: 0;
}
#ComposerInput,
QPlainTextEdit#ComposerInput {
    background: transparent;
    background-color: transparent;
    border: 0;
    color: #d7deeb;
    font-family: __EDITOR_FONT_STACK__;
    selection-background-color: #32415a;
}
QComboBox#ComposerThinkingCombo {
    background: #151c28;
    border: 1px solid #303849;
    border-radius: 16px;
    color: #dce5f5;
    font-weight: 800;
    min-height: 32px;
    min-width: 116px;
    padding: 0 26px 0 12px;
}
QComboBox#ComposerThinkingCombo:hover {
    background: #1d2635;
    border-color: #43506a;
}
QComboBox#ComposerThinkingCombo::drop-down {
    border: 0;
    width: 24px;
}
#ComposerIconButton, #ComposerActionButton {
    background: #151c28;
    border: 1px solid #303849;
    border-radius: 16px;
    color: #dce5f5;
    font-size: 16px;
    font-weight: 900;
    min-height: 32px;
    min-width: 32px;
    padding: 0;
}
#ComposerIconButton:hover, #ComposerActionButton:hover {
    background: #1d2635;
    border-color: #43506a;
}
#ComposerActionButton {
    background: #218c7d;
    border-color: #2da996;
    color: #ffffff;
}
#ComposerActionButton[busy="true"] {
    background: #263246;
    border-color: #4b5870;
}
#AttachmentTray {
    background: transparent;
    border: 0;
}
#AttachmentChip {
    background: #111722;
    border: 1px solid #303849;
    border-radius: 8px;
}
#AttachmentChipLabel {
    color: #cad3e4;
}
#AttachmentRemoveButton {
    background: #252d3b;
    border: 0;
    border-radius: 9px;
    color: #dce5f5;
    font-weight: 900;
    max-height: 18px;
    max-width: 18px;
    min-height: 18px;
    min-width: 18px;
    padding: 0;
}
#AttachmentRemoveButton:hover {
    background: #523044;
    color: #ffd6df;
}
QMenu#ChatAddMenu {
    background: #151922;
    border: 1px solid #303849;
    border-radius: 8px;
    color: #e8edf7;
    padding: 6px;
}
QMenu#ChatAddMenu::item {
    min-width: 190px;
    border-radius: 6px;
    padding: 8px 28px 8px 12px;
}
QMenu#ChatAddMenu::item:selected {
    background: #243044;
}
QMenu#ChatAddMenu::item:disabled {
    color: #7f8da5;
    background: transparent;
}
QMenu#ChatAddMenu::separator {
    height: 1px;
    margin: 6px 4px;
    background: #303849;
}
#ZoomLabel {
    color: #cad3e4;
    min-width: 54px;
    padding: 0 8px;
}
#ToggleButton {
    background: #111722;
    border: 1px solid #303849;
    border-radius: 8px;
    color: #cfd7e6;
    font-weight: 800;
    padding: 12px 14px;
    text-align: left;
}
#ToggleButton:hover {
    background: #1a2030;
}
#ToggleButton:checked, #ToggleButton[checkedState="true"] {
    background: #102922;
    border-color: #2f7e68;
    color: #9af0bd;
}
QComboBox {
    background: #0f141e;
    border: 1px solid #303849;
    border-radius: 6px;
    padding: 8px 10px;
}
QTabWidget::pane {
    border: 1px solid #303849;
    border-radius: 8px;
    background: #121722;
}
QTabBar::tab {
    background: #111722;
    color: #b7c2d6;
    border: 1px solid #303849;
    padding: 9px 16px;
    margin-right: 4px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
}
QTabBar::tab:selected {
    background: #243044;
    color: #ffffff;
}
#SectionList {
    background: #0f141e;
    border: 1px solid #303849;
    border-radius: 8px;
    padding: 6px;
}
#SectionList::item {
    padding: 10px;
    border-radius: 7px;
    color: #f4f7ff;
}
#SectionList::item:selected {
    background: #243044;
    color: #ffffff;
}
#SectionList::item:focus,
#SectionList::item:selected:focus,
QListWidget[historyList="true"]::item:focus,
QListWidget[historyList="true"]::item:selected:focus {
    outline: none;
    border: 0;
}
QListWidget[historyList="true"]::item {
    padding: 2px 6px;
    min-height: 40px;
}
#HistoryItem {
    background: transparent;
    border: 0;
}
#HistoryItemTitle {
    color: #f4f7ff;
    font-weight: 700;
}
#HistoryItemMeta {
    color: #c7d2e5;
}
#HistoryMoreButton {
    background: #151c28;
    border: 1px solid #303849;
    border-radius: 12px;
    color: #dce5f5;
    font-weight: 900;
    max-height: 24px;
    max-width: 30px;
    min-height: 24px;
    min-width: 30px;
    padding: 0;
}
#HistoryMoreButton:hover {
    background: #263246;
    border-color: #56657f;
}
#HistoryMoreButton:focus {
    outline: none;
}
QMenu#HistoryItemMenu {
    background: #202020;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    color: #f2f2f2;
    padding: 6px;
}
QMenu#HistoryItemMenu::item {
    border-radius: 6px;
    padding: 8px 26px 8px 12px;
}
QMenu#HistoryItemMenu::item:selected {
    background: #3a3a3a;
}
#PromptBox, #TranscriptBox, #LogBox,
QPlainTextEdit#PromptBox,
QTextEdit#TranscriptBox,
QTextEdit#LogBox {
    background: #06080d;
    background-color: #06080d;
    border: 1px solid #303849;
    border-radius: 8px;
    color: #d7deeb;
    font-family: __EDITOR_FONT_STACK__;
    selection-background-color: #32415a;
}
#PreviewImage {
    background: #0f141e;
    color: #95a1b5;
}
#MonoText {
    color: #cad3e4;
    font-family: "Cascadia Mono", "Consolas", monospace;
}
QScrollArea, #DetailScroll, #DetailBody {
    background: transparent;
    background-color: #090b10;
    border: 0;
}
QScrollArea#PreviewScroll {
    background: #0f141e;
    background-color: #0f141e;
    border: 1px solid #303849;
    border-radius: 8px;
}
QScrollBar:vertical {
    background: #0f141e;
    border: 0;
    width: 12px;
    margin: 0;
}
QScrollBar:horizontal {
    background: #0f141e;
    border: 0;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #3a465c;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""
