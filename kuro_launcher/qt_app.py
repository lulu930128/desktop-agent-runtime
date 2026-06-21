from __future__ import annotations

import base64
import datetime
import mimetypes
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
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
from .qt_controller import (
    BriefingSection,
    BriefingSummary,
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
MAX_CHAT_ATTACHMENT_BYTES = 24 * 1024 * 1024


class KuroQtLauncherWindow(QMainWindow):
    task_finished = Signal(str, object)
    task_failed = Signal(str, str)
    log_signal = Signal(str)

    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self.controller = QtLauncherController(cfg, self._append_log_threadsafe)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_base_labels: dict[str, str] = {}
        self.service_labels: dict[str, QLabel] = {}
        self.prompt_boxes: dict[str, QPlainTextEdit] = {}
        self.briefing_sections: dict[str, BriefingSection] = {}
        self.selected_briefing_key = "overview"
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
        self.main_nav_keys = {"chat", "briefing"}
        self.configure_nav_keys = {"profile", "pet", "chat_memory", "briefing_settings"}
        self.system_nav_keys = {"runtime", "settings"}
        self.settings_nav_keys = self.configure_nav_keys | self.system_nav_keys
        self.stack_order = ["chat", "briefing"]
        self.settings_order = [
            "general",
            "appearance",
            "conversation",
            "briefing",
            "advanced",
        ]
        self.settings_labels = {
            "general": "General",
            "appearance": "Appearance",
            "conversation": "Conversation",
            "briefing": "Briefing",
            "advanced": "Advanced",
        }
        self.settings_dialog_buttons: dict[str, QPushButton] = {}
        self.briefing_total_count = 0
        self.app_font_stack, self.editor_font_stack = self._load_font_stacks()
        self.chat_client = QtRuntimeChatClient(self)
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

        self.setWindowTitle("Kuro Desktop Console")
        self.resize(1380, 860)
        self.setMinimumSize(1120, 720)
        self._build_ui()
        self._wire_signals()
        self._refresh_profile_controls()
        self._refresh_workspace_data()
        self._append_log(f"[{log_ts()}] Qt launcher ready.")

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(2500)
        self.refresh_status()
        self.refresh_briefing()
        self._schedule_startup_auto_start()

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
        self.setStyleSheet(
            APP_STYLE.replace("__APP_FONT_STACK__", self.app_font_stack).replace(
                "__EDITOR_FONT_STACK__",
                self.editor_font_stack,
            )
        )
        root = QWidget()
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(244)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(8)

        brand = QLabel("Kuro")
        brand.setObjectName("Brand")
        subtitle = QLabel("Desktop Console")
        subtitle.setObjectName("BrandSub")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(10)

        main_label = QLabel("Console")
        main_label.setObjectName("NavGroup")
        self.main_nav_label = main_label
        sidebar_layout.addWidget(self.main_nav_label)
        self._add_nav_button(sidebar_layout, "chat", "Chat")
        self._add_nav_button(sidebar_layout, "briefing", "Briefing")

        sidebar_layout.addStretch()
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
        self.sidebar_briefing_status = QLabel("Briefing pending")
        self.sidebar_briefing_status.setObjectName("SidebarStatusDetail")
        self.sidebar_briefing_status.setWordWrap(True)
        sidebar_update_body_layout.addWidget(self.sidebar_briefing_status)
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

        self.settings_entry_button = QPushButton("⚙  Settings")
        self.settings_entry_button.setObjectName("NavButton")
        self.settings_entry_button.setProperty("settingsNav", True)
        self.settings_entry_button.setCheckable(True)
        self.settings_entry_button.clicked.connect(lambda _checked=False: self._open_settings_dialog())
        sidebar_layout.addWidget(self.settings_entry_button)

        self.stack = QStackedWidget()
        self.chat_page = self._build_chat_page()
        self.stack.addWidget(self.chat_page)
        self.stack.addWidget(self._build_briefing_page())
        self.settings_dialog = self._build_settings_dialog()

        shell.addWidget(sidebar)
        shell.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._set_page("chat")

    def _add_nav_button(self, layout: QVBoxLayout, key: str, label: str) -> None:
        button = QPushButton(label)
        button.setObjectName("NavButton")
        if key == "settings":
            button.setProperty("settingsNav", True)
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, page_key=key: self._set_page(page_key))
        self.nav_buttons[key] = button
        self.nav_base_labels[key] = label
        layout.addWidget(button)

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

    def _build_settings_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("SettingsDialog")
        dialog.setWindowTitle("Kuro Settings")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setMinimumSize(900, 620)
        dialog.resize(1040, 700)
        dialog.finished.connect(lambda _result=0: self.settings_entry_button.setChecked(False))

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("SettingsDialogFrame")
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 190))
        frame.setGraphicsEffect(shadow)
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
        title = QLabel("Settings")
        title.setObjectName("SettingsDialogTitle")
        subtitle = QLabel("Profile、桌寵外觀、對話記憶、Briefing 與進階工具。")
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
        self.settings_stack.addWidget(self._build_workspace_page())
        self.settings_stack.addWidget(self._build_pet_page())
        self.settings_stack.addWidget(self._build_chat_memory_page())
        self.settings_stack.addWidget(self._build_briefing_settings_page())
        self.settings_stack.addWidget(self._build_settings_page())
        body_layout.addWidget(self.settings_stack, 1)
        frame_layout.addWidget(body, 1)

        foot = QFrame()
        foot.setObjectName("SettingsDialogFoot")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.addStretch()
        foot_layout.addWidget(self._command_button("關閉", dialog.close))
        frame_layout.addWidget(foot)

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
            "briefing_settings": "briefing",
            "briefing-sources": "briefing",
            "briefing-settings": "briefing",
            "settings": "advanced",
            "diagnostics": "advanced",
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

    def _open_settings_dialog(self, key: str = "general") -> None:
        if not hasattr(self, "settings_dialog"):
            return
        self._set_settings_dialog_page(key)
        self.settings_entry_button.setChecked(True)
        if not self.settings_dialog.isVisible():
            self._center_settings_dialog()
            self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _center_settings_dialog(self) -> None:
        parent_geometry = self.geometry()
        width = min(1080, max(900, int(parent_geometry.width() * 0.82)))
        height = min(760, max(620, int(parent_geometry.height() * 0.84)))
        self.settings_dialog.resize(width, height)
        frame = self.settings_dialog.frameGeometry()
        frame.moveCenter(parent_geometry.center())
        self.settings_dialog.move(frame.topLeft())

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

    def _build_briefing_page(self) -> QWidget:
        page, layout = self._page(
            "Kuro Briefing",
            "同一個桌面主控台內讀取 pet-electron briefing snapshot，資料 pipeline 保持不變。",
        )
        self.briefing_meta = QLabel("")
        self.briefing_meta.setObjectName("MetaText")
        layout.addWidget(self.briefing_meta)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ContentSplitter")
        self.briefing_section_list = QListWidget()
        self.briefing_section_list.setObjectName("SectionList")
        self.briefing_section_list.setMinimumWidth(250)
        self.briefing_section_list.setMaximumWidth(320)
        self.briefing_section_list.itemClicked.connect(self._on_briefing_section_clicked)
        splitter.addWidget(self.briefing_section_list)

        self.briefing_detail_scroll = QScrollArea()
        self.briefing_detail_scroll.setWidgetResizable(True)
        self.briefing_detail_scroll.setObjectName("DetailScroll")
        self.briefing_detail_body = QWidget()
        self.briefing_detail_body.setObjectName("DetailBody")
        self.briefing_detail_layout = QVBoxLayout(self.briefing_detail_body)
        self.briefing_detail_layout.setContentsMargins(0, 0, 0, 0)
        self.briefing_detail_layout.setSpacing(12)
        self.briefing_detail_scroll.setWidget(self.briefing_detail_body)
        splitter.addWidget(self.briefing_detail_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.addWidget(
            self._command_button(
                "更新每日 Briefing",
                lambda: self._run_task("refresh-daily-briefing", self.controller.refresh_daily_briefing),
                role="primary",
            )
        )
        actions.addWidget(self._command_button("重新讀取 Snapshot", self.refresh_briefing))
        actions.addStretch()
        layout.addLayout(actions)
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
        layout.addWidget(profile_section)

        actions_section, actions_layout = self._settings_section(
            "Profile actions",
            "啟動目前 profile，或重新讀取本機 profiles / projects 設定檔。",
        )
        actions_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("啟動 Profile", self._start_profile, role="primary"),
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
            "初始草稿：未聊天不儲存\nRuntime Chat：LLM online 時自動連線\nHistory：第一則訊息送出後才建立正式對話"
        )
        self.chat_settings_status.setObjectName("StatusBanner")
        self.chat_settings_status.setWordWrap(True)
        layout.addWidget(self.chat_settings_status)

        memory_section, memory_layout = self._settings_section(
            "Character memory",
            "直接管理目前角色的 canonical long_term.json；LLM 在線時可同步刷新 runtime 記憶 prompt。",
        )
        memory_layout.addWidget(self._build_memory_tab(), 1)
        layout.addWidget(memory_section, 1)
        return page

    def _build_briefing_settings_page(self) -> QWidget:
        page, layout = self._settings_page(
            "Briefing",
            "每日摘要來源狀態、snapshot 重新讀取與手動更新。",
        )
        self.briefing_sources_status = QLabel("Briefing source status pending.")
        self.briefing_sources_status.setObjectName("StatusBanner")
        self.briefing_sources_status.setWordWrap(True)
        layout.addWidget(self.briefing_sources_status)

        source_panel, source_layout = self._settings_section(
            "Source status",
            "顯示 briefing snapshot 內各來源的資料覆蓋與更新狀態。",
        )
        self.briefing_source_list = QListWidget()
        self.briefing_source_list.setObjectName("SectionList")
        source_layout.addWidget(self.briefing_source_list, 1)

        actions_panel, actions_layout = self._settings_section(
            "Maintenance",
            "這些是資料刷新操作，不影響主頁面目前瀏覽的位置。",
        )
        actions_layout.addWidget(
            self._settings_inline_controls(
                self._command_button(
                    "更新每日 Briefing",
                    lambda: self._run_task("refresh-daily-briefing", self.controller.refresh_daily_briefing),
                    role="primary",
                ),
                self._command_button("重新讀取 Snapshot", self.refresh_briefing),
                stretch=True,
            )
        )
        layout.addWidget(actions_panel)
        layout.addWidget(source_panel, 1)
        return page

    def _build_chat_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(6)

        left_panel = QFrame()
        left_panel.setObjectName("Panel")
        left_panel.setFixedWidth(420)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        history_title = QLabel("Chats")
        history_title.setObjectName("SectionTitle")
        left_layout.addWidget(history_title)

        self.history_list = QListWidget()
        self.history_list.setObjectName("SectionList")
        self.history_list.setProperty("historyList", True)
        self.history_list.setMinimumWidth(340)
        self.history_list.setMaximumWidth(420)
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.history_list.itemSelectionChanged.connect(self._on_history_selected)
        left_layout.addWidget(self.history_list, 1)
        content.addWidget(left_panel)

        right_panel = QFrame()
        right_panel.setObjectName("Panel")
        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        self.chat_connection_status = QLabel("Runtime Chat 尚未連線。")
        self.chat_connection_status.setObjectName("StatusBanner")
        self.chat_connection_status.setWordWrap(True)
        self.chat_connection_status.setVisible(False)
        right_layout.addWidget(self.chat_connection_status)

        self.history_transcript = QTextEdit()
        self.history_transcript.setObjectName("TranscriptBox")
        self.history_transcript.setReadOnly(True)
        right_layout.addWidget(self.history_transcript, 1)

        self.chat_attachment_tray = QFrame()
        self.chat_attachment_tray.setObjectName("AttachmentTray")
        self.chat_attachment_layout = QHBoxLayout(self.chat_attachment_tray)
        self.chat_attachment_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_attachment_layout.setSpacing(8)
        self.chat_attachment_layout.addStretch()
        self.chat_attachment_tray.setVisible(False)
        right_layout.addWidget(self.chat_attachment_tray)

        composer = QFrame()
        composer.setObjectName("ComposerPanel")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(10, 8, 10, 8)
        composer_layout.setSpacing(6)
        self.chat_input = QPlainTextEdit()
        self.chat_input.setObjectName("ComposerInput")
        self.chat_input.setPlaceholderText("輸入要送給目前 runtime 角色的訊息。")
        self.chat_input.setMaximumHeight(92)
        composer_layout.addWidget(self.chat_input, 1)

        composer_controls = QFrame()
        composer_controls.setObjectName("ComposerControls")
        composer_controls_layout = QHBoxLayout(composer_controls)
        composer_controls_layout.setContentsMargins(0, 0, 0, 0)
        composer_controls_layout.setSpacing(8)
        self.chat_attach_button = QPushButton("+")
        self.chat_attach_button.setObjectName("ComposerIconButton")
        self.chat_attach_button.setToolTip("新增附件或開關桌寵功能")
        self.chat_attach_button.clicked.connect(self._show_chat_add_menu)
        composer_controls_layout.addWidget(self.chat_attach_button)
        composer_controls_layout.addStretch()
        self.chat_thinking_combo = QComboBox()
        self.chat_thinking_combo.setObjectName("ComposerThinkingCombo")
        self.chat_thinking_combo.setToolTip("Thinking power")
        self._populate_thinking_combo(self.chat_thinking_combo)
        self.chat_thinking_combo.currentIndexChanged.connect(self._on_thinking_changed)
        composer_controls_layout.addWidget(self.chat_thinking_combo)
        self.chat_send_button = QPushButton("✓")
        self.chat_send_button.setObjectName("ComposerActionButton")
        self.chat_send_button.setToolTip("送出")
        self.chat_send_button.clicked.connect(self._send_or_interrupt_chat)
        composer_controls_layout.addWidget(self.chat_send_button)
        composer_layout.addWidget(composer_controls)
        right_layout.addWidget(composer)

        content.addWidget(right_panel, 1)
        outer.addLayout(content, 1)
        return page

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
        layout.addWidget(window_panel)
        layout.addWidget(preview_panel, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._settings_page(
            "Advanced",
            "Runtime、工程診斷、prompt preview、paths 與 logs。",
        )
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
                self._command_button("停止 Runtime", lambda: self._run_task("stop-runtime", self.controller.stop_profile), role="danger"),
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
        pet_shell_layout.addWidget(
            self._settings_inline_controls(
                self._command_button("開桌寵 Shell", lambda: self._run_task("open-pet", self.controller.launch_pet_electron)),
                self._command_button("重載桌寵前端", lambda: self._run_task("pet-reload", self.controller.reload_pet_frontend)),
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
        return page

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

    def _metric_card(self, title: str, value: str, unit: str = "") -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        value_label = QLabel(value or "-")
        value_label.setObjectName("MetricValue")
        unit_label = QLabel(unit)
        unit_label.setObjectName("MetaText")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        if unit:
            layout.addWidget(unit_label)
        return card

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
            lambda checked=False, action=action: self._run_task(
                f"pet-toggle:{action}",
                lambda action=action, checked=checked: self.controller.set_pet_toggle(action, checked),
            )
        )
        self.pet_toggle_buttons[action] = button
        return button

    def _set_page(self, key: str) -> None:
        stack_key = key
        if key.startswith("briefing:"):
            stack_key = "briefing"
            self.selected_briefing_key = key.split(":", 1)[1] or "overview"
            self._select_briefing_list_item(self.selected_briefing_key)
            self._render_selected_briefing_section()
        elif key in self.settings_nav_keys or key in {
            "workspace",
            "memory",
            "chat-memory",
            "briefing-sources",
            "briefing-settings",
            "diagnostics",
        }:
            self._open_settings_dialog(key)
            return

        if stack_key not in self.stack_order:
            stack_key = "chat"

        previous_key = ""
        if hasattr(self, "stack") and self.stack.currentIndex() >= 0:
            previous_key = self.stack_order[self.stack.currentIndex()]
        if previous_key == "chat" and stack_key != "chat":
            if self._discard_auto_empty_history_if_safe("__leave_chat__", allow_recreate=True):
                self._show_blank_chat_draft()
                QTimer.singleShot(250, self._refresh_history_list)

        self.stack.setCurrentIndex(self.stack_order.index(stack_key))
        for page_key, button in self.nav_buttons.items():
            button.setVisible(page_key in self.main_nav_keys)
            checked = page_key == stack_key
            button.setChecked(checked)
        self.settings_entry_button.setChecked(False)
        if stack_key == "chat" and self.chat_blank_draft_active:
            QTimer.singleShot(150, self._ensure_auto_empty_chat)

    def _refresh_profile_controls(self) -> None:
        combos = [
            combo
            for combo in [
                getattr(self, "character_combo", None),
                getattr(self, "project_combo", None),
                getattr(self, "outfit_combo", None),
                getattr(self, "thinking_combo", None),
                getattr(self, "chat_thinking_combo", None),
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
        for combo in combos:
            combo.blockSignals(False)

    def _populate_thinking_combo(self, combo: QComboBox) -> None:
        combo.addItem("Normal", "normal")
        combo.addItem("High", "high")
        combo.addItem("Low", "low")

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
        self.controller.set_thinking_power(str(combo.currentData() or "normal"))
        for combo_name in ("thinking_combo", "chat_thinking_combo"):
            peer = getattr(self, combo_name, None)
            if peer is None or peer is combo:
                continue
            peer.blockSignals(True)
            self._set_combo_by_data(peer, self.controller.thinking_power)
            peer.blockSignals(False)
        self._update_project_detail()

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
        if not self.controller.selected_character() or not self.controller.selected_project():
            self._append_log(f"[{log_ts()}] startup_profile 自動啟動略過：角色或專案尚未選定。")
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

    def _refresh_history_list(self) -> None:
        previous_uid = self.selected_history_uid
        current_item = self.history_list.currentItem()
        if current_item:
            previous_uid = str(current_item.data(Qt.ItemDataRole.UserRole) or previous_uid)

        records = self.controller.read_history_records()
        self.history_records_by_uid = {record.uid: record for record in records}
        target_uid = previous_uid or self.chat_auto_empty_history_uid
        self.history_list.blockSignals(True)
        try:
            self.history_list.clear()
            self.history_item_action_buttons = {}
            selected_row = -1
            for record in records:
                title_text = record.title or "新對話"
                item = QListWidgetItem(title_text)
                item.setData(Qt.ItemDataRole.UserRole, record.uid)
                item.setToolTip(title_text)
                self.history_list.addItem(item)
                widget = self._build_history_item_widget(record)
                item.setSizeHint(QSize(0, 40))
                self.history_list.setItemWidget(item, widget)
                if target_uid and record.uid == target_uid:
                    selected_row = self.history_list.count() - 1
            if selected_row >= 0:
                self.history_list.setCurrentRow(selected_row)
            else:
                self.history_list.clearSelection()
                self.history_list.setCurrentRow(-1)
        finally:
            self.history_list.blockSignals(False)
        if selected_row >= 0:
            self.selected_history_uid = str(self.history_list.item(selected_row).data(Qt.ItemDataRole.UserRole) or "")
            self.chat_blank_draft_active = False
            self._render_history_messages(self.selected_history_uid)
        else:
            self._show_blank_chat_draft()
        self._update_history_item_action_buttons()

    def _on_history_selected(self) -> None:
        item = self.history_list.currentItem()
        if not item:
            return
        self.chat_blank_draft_active = False
        self.selected_history_uid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self._render_history_messages(self.selected_history_uid)
        self._update_history_item_action_buttons()
        self._apply_history_selection_from_click(self.selected_history_uid)

    def _build_history_item_widget(self, record: HistoryRecord) -> QFrame:
        row = QFrame()
        row.setObjectName("HistoryItem")
        row.setMinimumHeight(40)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        action = QPushButton("...")
        action.setObjectName("HistoryMoreButton")
        action.setToolTip("更多")
        action.setVisible(False)
        action.setFixedSize(30, 24)
        action.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        action.clicked.connect(
            lambda _checked=False, uid=record.uid, button=action: self._show_history_item_menu(uid, button)
        )
        layout.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.history_item_action_buttons[record.uid] = action
        return row

    def _update_history_item_action_buttons(self) -> None:
        selected_uid = self.selected_history_uid
        for uid, button in self.history_item_action_buttons.items():
            button.setVisible(bool(selected_uid and uid == selected_uid))

    def _show_history_item_menu(self, history_uid: str, button: QPushButton) -> None:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            return
        self._select_history_item(history_uid)
        menu = QMenu(self)
        menu.setObjectName("HistoryItemMenu")
        delete_action = menu.addAction("刪除")
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen == delete_action:
            self._delete_history_by_uid(history_uid)

    def _select_history_item(self, history_uid: str) -> None:
        for row in range(self.history_list.count()):
            item = self.history_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == history_uid:
                self.history_list.setCurrentRow(row)
                return

    def _show_blank_chat_draft(self) -> None:
        self.chat_blank_draft_active = True
        self.selected_history_uid = ""
        self.chat_base_transcript = ""
        self.chat_live_blocks = []
        if hasattr(self, "history_list"):
            self.history_list.blockSignals(True)
            try:
                self.history_list.clearSelection()
                self.history_list.setCurrentRow(-1)
            finally:
                self.history_list.blockSignals(False)
            self._update_history_item_action_buttons()
        if hasattr(self, "history_transcript"):
            self.history_transcript.clear()

    def _render_history_messages(self, history_uid: str) -> None:
        messages = self.controller.read_history_timeline(history_uid)
        if not messages:
            self.chat_base_transcript = ""
            self.chat_live_blocks = []
            self.history_transcript.clear()
            return
        parts = []
        for message in messages:
            role = (
                "User"
                if message.role == "human"
                else "Kuro"
                if message.role in {"ai", "assistant"}
                else "Event"
                if message.role == "event"
                else message.role
            )
            parts.append(f"[{message.timestamp or '-'}] {role}\n{message.content}")
        self.chat_base_transcript = "\n\n".join(parts)
        self.chat_live_blocks = []
        self.history_transcript.setPlainText(self.chat_base_transcript)

    def _runtime_chat_url(self) -> str:
        return f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws?client_role=launcher-console"

    def _connect_chat(self, *, auto: bool = False) -> None:
        ws_url = self._runtime_chat_url()
        if not auto:
            self.chat_auto_connect_paused = False
        self.chat_client.connect_to(ws_url)
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
            self._run_task("pet-interrupt", self.controller.interrupt_pet)
        self.chat_runtime_state = "interrupted"
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
        if not self.chat_client.connected:
            return
        self.chat_auto_empty_started = True
        self.chat_auto_empty_create_pending = False
        if self.chat_blank_draft_active:
            self._set_chat_status("Runtime Chat 已連線。初始草稿尚未儲存；送出第一則訊息後才會建立對話。", error=False)

    def _history_is_empty(self, history_uid: str) -> bool:
        record = self.history_records_by_uid.get(history_uid)
        if record is not None:
            return bool(record.is_empty)
        return not self.controller.read_history_messages(history_uid, limit=1)

    def _clear_auto_empty_history_marker(self, *, allow_recreate: bool = False) -> None:
        self.chat_auto_empty_history_uid = ""
        self.chat_auto_empty_create_pending = False
        if allow_recreate:
            self.chat_auto_empty_started = False

    def _discard_auto_empty_history_if_safe(
        self,
        next_history_uid: str = "",
        *,
        allow_recreate: bool = False,
    ) -> bool:
        auto_uid = self.chat_auto_empty_history_uid
        next_history_uid = (next_history_uid or "").strip()
        if not auto_uid or auto_uid == next_history_uid:
            return False
        if self.chat_auto_empty_create_pending:
            return False
        if not self._history_is_empty(auto_uid):
            self._clear_auto_empty_history_marker(allow_recreate=allow_recreate)
            self._append_log(f"[{log_ts()}] 暫存空白聊天已有內容，保留：{auto_uid}")
            return False
        deleted = False
        if self.chat_client.connected:
            deleted = self.chat_client.delete_history(auto_uid)
            if deleted:
                self._append_log(f"[{log_ts()}] 已刪除未使用的暫存空白聊天：{auto_uid}")
        else:
            try:
                self.controller.delete_history(auto_uid)
                deleted = True
                self._append_log(f"[{log_ts()}] 已刪除未使用的暫存空白聊天：{auto_uid}")
            except Exception as exc:
                self._append_log(f"[{log_ts()}] 暫存空白聊天刪除失敗：{auto_uid} / {exc}")
        self._clear_auto_empty_history_marker(allow_recreate=allow_recreate)
        return deleted

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

    def _apply_history_selection_from_click(self, history_uid: str) -> None:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            return
        self._discard_auto_empty_history_if_safe(history_uid)
        if not (self.last_status and self.last_status.llm):
            self._set_chat_status("已選擇聊天；啟動 Profile 後可同步到桌寵。", error=False)
            return
        self._run_task("select-history", lambda uid=history_uid: self.controller.select_history(uid))

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
        for label, action_key in [
            ("Reader", "set-reader-visible"),
            ("Briefing", "set-briefing-visible"),
            ("Mic", "mic-toggle"),
            ("Camera", "toggle-camera"),
            ("Screen", "toggle-screen"),
            ("Browser", "toggle-browser"),
        ]:
            toggle_action = menu.addAction(label)
            toggle_action.setCheckable(True)
            toggle_action.setChecked(bool(state_by_action.get(action_key, False)))
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
            lambda _checked=False: self._run_task("pet-interrupt", self.controller.interrupt_pet)
        )

        return menu

    def _chat_menu_toggle_states(self) -> dict[str, bool]:
        status = self.last_status
        if status is None:
            return {}
        return {
            "set-reader-visible": status.reader_visible,
            "set-briefing-visible": status.briefing_visible,
            "mic-toggle": status.mic_enabled,
            "toggle-camera": status.camera_enabled,
            "toggle-screen": status.screen_enabled,
            "toggle-browser": status.browser_panel_enabled,
        }

    def _set_pet_toggle_from_menu(self, action: str, checked: bool) -> None:
        self._run_task(
            f"pet-toggle:{action}",
            lambda action=action, checked=checked: self.controller.set_pet_toggle(action, checked),
        )

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
            if size > MAX_CHAT_ATTACHMENT_BYTES:
                skipped.append(f"{path.name}: 檔案超過 24 MB")
                continue
            try:
                payload = self._build_chat_attachment(path, size)
            except OSError as exc:
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
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return {
            "kind": self._classify_chat_attachment(path, mime_type),
            "name": path.name,
            "size": size,
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
        self.chat_send_button.setText("■" if busy else "✓")
        self.chat_send_button.setToolTip("中斷這次回覆" if busy else "送出")
        self.chat_send_button.setEnabled(not bool(self.pending_chat_submit) or busy)
        self.chat_send_button.setProperty("busy", busy)
        self.chat_send_button.style().unpolish(self.chat_send_button)
        self.chat_send_button.style().polish(self.chat_send_button)

    def _send_chat_text(self) -> None:
        text = self.chat_input.toPlainText().strip()
        attachments = list(self.chat_attachments)
        if not text and not attachments:
            return
        create_history = bool(self.chat_blank_draft_active and not self.selected_history_uid)
        if create_history and not (self.last_status and self.last_status.llm):
            self._set_chat_status("Runtime Chat 尚未就緒，請先啟動 Profile。", error=True)
            return
        self.pending_chat_submit = {
            "text": text,
            "attachments": attachments,
            "auto_empty_history_uid": self._current_auto_empty_history_for_send(),
            "draft_create_history": create_history,
        }
        self._update_chat_send_button()
        self._run_task(
            "pet-send-text",
            lambda text=text, attachments=attachments, create_history=create_history: self.controller.send_pet_text_for_chat(
                text,
                attachments,
                create_history=create_history,
            ),
        )

    def _apply_selected_history(self) -> None:
        if not self.selected_history_uid:
            QMessageBox.information(self, "聊天記錄", "請先選擇一段聊天。")
            return
        self._discard_auto_empty_history_if_safe(self.selected_history_uid)
        if not (self.last_status and self.last_status.llm):
            self.pending_history_uid = self.selected_history_uid
            self.pending_force_new_history = False
            self._append_log(f"[{log_ts()}] 已排程聊天同步，啟動 Profile 後套用：{self.selected_history_uid}")
            self._set_chat_status("已排程聊天同步，啟動 Profile 後會套用。", error=False)
            return
        self._run_task(
            "select-history",
            lambda: self.controller.select_history(self.selected_history_uid),
        )

    def _create_chat_history(self) -> None:
        if self.chat_auto_empty_history_uid and self._history_is_empty(self.chat_auto_empty_history_uid):
            self.selected_history_uid = self.chat_auto_empty_history_uid
            self._refresh_history_list()
            self._set_chat_status("目前已在暫存空白對話。", error=False)
            return
        if not (self.last_status and self.last_status.llm):
            self.pending_history_uid = ""
            self.pending_force_new_history = True
            self.selected_history_uid = ""
            self.history_list.clearSelection()
            self.history_transcript.setPlainText("啟動 Profile 時會建立一段新的聊天。")
            self._append_log(f"[{log_ts()}] 已排程建立新聊天，啟動 Profile 後套用。")
            self._set_chat_status("已排程建立新聊天，啟動 Profile 後會套用。", error=False)
            return
        self._run_task("create-history", self.controller.create_history)

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
        self._update_chat_send_button()
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
        if connected and state == "connected":
            QTimer.singleShot(150, self._ensure_auto_empty_chat)

    def _on_chat_client_changed(self, client_uid: str, conf_name: str, conf_uid: str) -> None:
        suffix = f" · {conf_name or conf_uid or '-'} · client={client_uid[:8] or '-'}"
        self._set_chat_status(f"Runtime Chat 已連線{suffix}", error=False)
        QTimer.singleShot(150, self._ensure_auto_empty_chat)

    def _on_chat_error(self, message: str) -> None:
        self._append_log(f"[{log_ts()}] Runtime Chat error: {message}")
        self._set_chat_status(f"Runtime Chat 錯誤：{message}", error=True)

    def _on_chat_history_changed(self, history_uid: str, _title: str) -> None:
        if history_uid:
            self.selected_history_uid = history_uid
            if self.chat_auto_empty_create_pending:
                self.chat_auto_empty_history_uid = history_uid
                self.chat_auto_empty_create_pending = False
                self._append_log(f"[{log_ts()}] 已標記暫存空白聊天：{history_uid}")
        self._refresh_history_list()
        self._refresh_memory_list()
        self._refresh_prompt_boxes()

    def _on_chat_assistant_text_changed(self, text: str) -> None:
        if not text:
            return
        self._release_auto_empty_history_marker(self._current_auto_empty_history_for_send())
        if self.chat_live_blocks and self.chat_live_blocks[-1][0] == "Kuro":
            role, timestamp, _old = self.chat_live_blocks[-1]
            self.chat_live_blocks[-1] = (role, timestamp, text)
        else:
            self.chat_live_blocks.append(("Kuro", self._chat_timestamp(), text))
        self._render_chat_transcript_with_live()

    def _render_chat_transcript_with_live(self) -> None:
        parts: list[str] = []
        base = self.chat_base_transcript.strip()
        if base and not base.startswith("這段聊天目前沒有") and not base.startswith("這個角色目前還沒有"):
            parts.append(base)
        for role, timestamp, content in self.chat_live_blocks:
            if not content and role == "Kuro":
                content = "..."
            parts.append(f"[{timestamp}] {role}\n{content}")
        self.history_transcript.setPlainText("\n\n".join(parts) if parts else self.chat_base_transcript)

    def _chat_timestamp(self) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _refresh_memory_list(self) -> None:
        previous_entry_id = self._selected_memory_entry_id()
        self.memory_list.blockSignals(True)
        self.memory_list.clear()
        records = self.controller.read_memory_records()
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
        if not history_uid:
            QMessageBox.information(self, "聊天記錄", "請先選擇要刪除的聊天。")
            return

        record = self.history_records_by_uid.get(history_uid)
        title = record.title if record else history_uid
        answer = QMessageBox.question(
            self,
            "刪除聊天記錄",
            f"確定要刪除這段聊天嗎？\n\n{title}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if history_uid == self.chat_auto_empty_history_uid:
            self._clear_auto_empty_history_marker(allow_recreate=True)
        self._run_task("delete-history", lambda uid=history_uid: self.controller.delete_history(uid))

    def _selected_memory_entry_id(self) -> str:
        if not hasattr(self, "memory_list"):
            return ""
        item = self.memory_list.currentItem()
        if not item:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _add_memory_dialog(self) -> None:
        content, ok = QInputDialog.getMultiLineText(
            self,
            "新增角色記憶",
            "輸入要加入目前角色的長期記憶：",
        )
        if not ok:
            return
        content = content.strip()
        if not content:
            return
        self._run_task("add-memory", lambda text=content: self.controller.add_memory(text))

    def _toggle_selected_memory(self) -> None:
        entry_id = self._selected_memory_entry_id()
        if not entry_id:
            QMessageBox.information(self, "角色記憶", "請先選擇一條記憶。")
            return
        self._run_task("toggle-memory", lambda eid=entry_id: self.controller.toggle_memory(eid))

    def _approve_selected_memory(self) -> None:
        entry_id = self._selected_memory_entry_id()
        if not entry_id:
            QMessageBox.information(self, "角色記憶", "請先選擇一條記憶。")
            return
        self._run_task("approve-memory", lambda eid=entry_id: self.controller.approve_memory(eid))

    def _reject_selected_memory(self) -> None:
        entry_id = self._selected_memory_entry_id()
        if not entry_id:
            QMessageBox.information(self, "角色記憶", "請先選擇一條記憶。")
            return
        self._run_task("reject-memory", lambda eid=entry_id: self.controller.reject_memory(eid))

    def _delete_selected_memory(self) -> None:
        entry_id = self._selected_memory_entry_id()
        if not entry_id:
            QMessageBox.information(self, "角色記憶", "請先選擇一條記憶。")
            return
        detail = self.memory_detail.toPlainText().strip()
        answer = QMessageBox.question(
            self,
            "刪除角色記憶",
            f"確定要刪除這條記憶嗎？\n\n{detail[:600]}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_task("delete-memory", lambda eid=entry_id: self.controller.delete_memory(eid))

    def _compact_memory(self) -> None:
        answer = QMessageBox.question(
            self,
            "整理角色記憶",
            "確定要整理目前角色的長期記憶嗎？這會合併或移除重複/過期記憶。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_task("compact-memory", self.controller.compact_memory)

    def refresh_status(self) -> None:
        self._run_task("status", self.controller.read_runtime_status, quiet=True)

    def refresh_briefing(self) -> None:
        self._run_task("briefing", self.controller.read_briefing_summary, quiet=True)

    def _run_task(self, name: str, fn: Callable[[], object], *, quiet: bool = False) -> None:
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
        if name == "status" and isinstance(result, RuntimeStatus):
            self._apply_status(result)
            return
        if name == "briefing" and isinstance(result, BriefingSummary):
            self._apply_briefing(result)
            return
        if name == "preview-asset":
            self.preview_refresh_inflight = False
            if isinstance(result, PreviewAsset):
                self._apply_preview_asset(result)
            if self.preview_refresh_pending:
                self.preview_refresh_pending = False
                QTimer.singleShot(250, self._request_preview_asset_refresh)
            return
        if name == "pet-send-text":
            pending = self.pending_chat_submit or {}
            text = str(pending.get("text") or "")
            attachments = list(pending.get("attachments") or [])
            auto_empty_history_uid = str(pending.get("auto_empty_history_uid") or "")
            created_history_uid = ""
            send_result = result
            if isinstance(result, dict):
                history_result = result.get("history") if isinstance(result.get("history"), dict) else {}
                created_history_uid = str(
                    result.get("history_uid")
                    or history_result.get("history_uid")
                    or ""
                ).strip()
                send_result = result.get("send") if isinstance(result.get("send"), dict) else result
            self.pending_chat_submit = None
            self._update_chat_send_button()
            self.chat_input.setPlainText("")
            self.chat_attachments = []
            self._render_chat_attachments()
            self._release_auto_empty_history_marker(auto_empty_history_uid)
            if created_history_uid:
                self.selected_history_uid = created_history_uid
                self.chat_blank_draft_active = False
                self._clear_auto_empty_history_marker(allow_recreate=False)
                self._clear_pending_history_choice()
            self.chat_live_blocks.append(("User", self._chat_timestamp(), self._visible_chat_input_text(text, attachments)))
            self.chat_live_blocks.append(("Kuro", self._chat_timestamp(), ""))
            self._render_chat_transcript_with_live()
            self._set_chat_status("已送出到桌寵，等待回覆。", error=False)
            if isinstance(send_result, dict):
                inner = send_result.get("result") if isinstance(send_result.get("result"), dict) else {}
                warnings = inner.get("warnings") if isinstance(inner, dict) else None
                if isinstance(warnings, list) and warnings:
                    QMessageBox.warning(self, "Kuro Desktop Console", "\n".join(str(item) for item in warnings))
            if created_history_uid:
                QTimer.singleShot(450, self._refresh_history_list)
                QTimer.singleShot(1500, self._refresh_history_list)
        self._append_log(f"[{log_ts()}] task done: {name}")
        self._set_action_status(f"已完成：{name}")
        self.refresh_status()
        if name in {"open-pet", "start-profile", "refresh-daily-briefing"}:
            self.refresh_briefing()
        if name in {"open-pet", "start-profile", "apply-outfit"}:
            QTimer.singleShot(700, self._request_preview_asset_refresh)
            QTimer.singleShot(1800, self._request_preview_asset_refresh)
        if name == "start-profile" and isinstance(result, dict):
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
            self._refresh_memory_list()
            self._refresh_prompt_boxes()
        if isinstance(result, dict) and result.get("warning"):
            QMessageBox.warning(self, "Kuro Desktop Console", str(result.get("warning")))

    def _on_task_failed(self, name: str, message: str) -> None:
        if name == "preview-asset":
            self.preview_refresh_inflight = False
            self.preview_refresh_pending = False
            self._append_log(f"[{log_ts()}] preview refresh failed: {message}")
            return
        if name == "pet-send-text":
            self.pending_chat_submit = None
            self._update_chat_send_button()
        self._append_log(f"[{log_ts()}] task failed: {name} / {message}")
        self._set_action_status(f"失敗：{name} / {message}", error=True)
        QMessageBox.warning(self, "Kuro Desktop Console", message)
        self.refresh_status()

    def _set_action_status(self, text: str, *, error: bool = False) -> None:
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
                    f"Reader {'ON' if status.reader_visible else 'OFF'} · Briefing {'ON' if status.briefing_visible else 'OFF'}",
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
                        f"Current history：{status.current_history_title or status.current_history_uid or '-'}",
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
                    f"briefing_visible: {status.briefing_visible}",
                    f"briefing_date: {status.briefing_date or '-'}",
                    f"briefing_updated_at: {status.briefing_updated_at or '-'}",
                ]
            )
        )
        if status.ai_state:
            self.chat_runtime_state = status.ai_state
            self._update_chat_send_button()
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
        state_by_action = {
            "set-reader-visible": status.reader_visible,
            "set-briefing-visible": status.briefing_visible,
            "mic-toggle": status.mic_enabled,
            "toggle-camera": status.camera_enabled,
            "toggle-screen": status.screen_enabled,
            "toggle-browser": status.browser_panel_enabled,
            "set-game-mode": status.pet_game_mode,
            "set-live2d-inspector": status.live2d_inspector_overlay_enabled,
        }
        for action, checked in state_by_action.items():
            button = self.pet_toggle_buttons.get(action)
            if not button:
                continue
            button.blockSignals(True)
            button.setChecked(bool(checked))
            button.setText(self._pet_toggle_label(action, bool(checked)))
            button.setProperty("checkedState", bool(checked))
            button.style().unpolish(button)
            button.style().polish(button)
            button.blockSignals(False)

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
                        f"Visible: Reader {'ON' if status.reader_visible else 'OFF'} · Briefing {'ON' if status.briefing_visible else 'OFF'} · Browser {'ON' if status.browser_panel_enabled else 'OFF'}",
                        f"Input: Mic {'ON' if status.mic_enabled else 'OFF'} · Camera {'ON' if status.camera_enabled else 'OFF'} · Screen {'ON' if status.screen_enabled else 'OFF'}",
                        f"Window: Game mode {'ON' if status.pet_game_mode else 'OFF'} · Inspector {'ON' if status.live2d_inspector_overlay_enabled else 'OFF'}",
                        f"History: {status.current_history_title or status.current_history_uid or '-'}",
                        f"Latest user: {self._compact_label_text(status.latest_user_text, 120) or '-'}",
                    ]
                )
            )

    def _pet_toggle_label(self, action: str, checked: bool) -> str:
        base = {
            "set-reader-visible": "Reader",
            "set-briefing-visible": "Briefing",
            "mic-toggle": "Mic",
            "toggle-camera": "Camera",
            "toggle-screen": "Screen",
            "toggle-browser": "Browser",
            "set-game-mode": "Game mode",
            "set-live2d-inspector": "Live2D Inspector",
        }.get(action, action)
        return f"{base}  {'ON' if checked else 'OFF'}"

    def _apply_briefing(self, summary: BriefingSummary) -> None:
        if not summary.ok:
            self.briefing_meta.setText(f"Briefing offline: {summary.error}")
            if hasattr(self, "briefing_sources_status"):
                self.briefing_sources_status.setText(f"Briefing offline: {summary.error}")
                self.briefing_sources_status.setProperty("error", True)
                self.briefing_sources_status.setProperty("warning", False)
                self.briefing_sources_status.style().unpolish(self.briefing_sources_status)
                self.briefing_sources_status.style().polish(self.briefing_sources_status)
            if hasattr(self, "briefing_source_list"):
                self.briefing_source_list.clear()
                self.briefing_source_list.addItem(QListWidgetItem(str(summary.error or "Briefing offline.")))
            if hasattr(self, "sidebar_briefing_status"):
                self.sidebar_briefing_status.setText(f"Briefing offline: {summary.error}")
                self.sidebar_briefing_status.setProperty("error", True)
                self.sidebar_briefing_status.setProperty("warning", False)
                self.sidebar_briefing_status.style().unpolish(self.sidebar_briefing_status)
                self.sidebar_briefing_status.style().polish(self.sidebar_briefing_status)
            if hasattr(self, "sidebar_update_toggle") and not bool(self.sidebar_update_toggle.property("error")):
                if not self.sidebar_update_toggle.text().startswith("更新狀態    執行中"):
                    self.sidebar_update_toggle.setText("更新狀態    Briefing offline")
                    self.sidebar_update_toggle.setProperty("warning", True)
                    self.sidebar_update_toggle.style().unpolish(self.sidebar_update_toggle)
                    self.sidebar_update_toggle.style().polish(self.sidebar_update_toggle)
            self.briefing_sections = {}
            self._clear_layout(self.briefing_detail_layout)
            return

        self.briefing_sections = {section.key: section for section in summary.sections}
        stale_text = self._briefing_freshness_text(summary.date)
        self.briefing_meta.setText(
            f"{summary.title} · date={summary.date or '-'} · "
            f"updated={self._format_time(summary.updated_at)} · {stale_text}"
        )
        if hasattr(self, "sidebar_briefing_status"):
            total = sum(count for _key, _label, count in summary.section_counts)
            briefing_warning = stale_text.startswith("stale") or stale_text == "date unknown"
            self.sidebar_briefing_status.setText(
                f"Briefing: {summary.date or '-'} · {stale_text}\nitems: {total} · updated {self._format_time(summary.updated_at)}"
            )
            self.sidebar_briefing_status.setProperty("error", False)
            self.sidebar_briefing_status.setProperty("warning", briefing_warning)
            self.sidebar_briefing_status.style().unpolish(self.sidebar_briefing_status)
            self.sidebar_briefing_status.style().polish(self.sidebar_briefing_status)
            if hasattr(self, "sidebar_update_toggle") and not bool(self.sidebar_update_toggle.property("error")):
                if not self.sidebar_update_toggle.text().startswith("更新狀態    執行中"):
                    self.sidebar_update_toggle.setText(
                        "更新狀態    Briefing stale" if briefing_warning else "更新狀態    Ready"
                    )
                    self.sidebar_update_toggle.setProperty("warning", briefing_warning)
                    self.sidebar_update_toggle.style().unpolish(self.sidebar_update_toggle)
                    self.sidebar_update_toggle.style().polish(self.sidebar_update_toggle)
        self._update_briefing_nav_counts(summary)
        self._refresh_briefing_sources_status(summary, stale_text)
        self._refresh_briefing_section_list(summary)
        if self.selected_briefing_key not in self.briefing_sections:
            self.selected_briefing_key = "overview"
        self._render_selected_briefing_section()

    def _update_briefing_nav_counts(self, summary: BriefingSummary) -> None:
        counts = {key: count for key, _label, count in summary.section_counts}
        total = sum(counts.values())
        self.briefing_total_count = total
        button = self.nav_buttons.get("briefing")
        if not button:
            return
        button.setText(f"{self.nav_base_labels.get('briefing', 'Briefing')}    {total}")

    def _refresh_briefing_sources_status(self, summary: BriefingSummary, stale_text: str) -> None:
        if hasattr(self, "briefing_sources_status"):
            source_count = len(summary.source_status)
            total = sum(count for _key, _label, count in summary.section_counts)
            briefing_warning = stale_text.startswith("stale") or stale_text == "date unknown"
            self.briefing_sources_status.setText(
                f"{summary.title or 'Briefing'} · date={summary.date or '-'} · {stale_text} · "
                f"sources={source_count} · items={total}"
            )
            self.briefing_sources_status.setProperty("error", False)
            self.briefing_sources_status.setProperty("warning", briefing_warning)
            self.briefing_sources_status.style().unpolish(self.briefing_sources_status)
            self.briefing_sources_status.style().polish(self.briefing_sources_status)

        if not hasattr(self, "briefing_source_list"):
            return
        self.briefing_source_list.clear()
        if not summary.source_status:
            item = QListWidgetItem("No source status in current snapshot.")
            self.briefing_source_list.addItem(item)
            return
        for label, status, message in summary.source_status:
            text = f"{label or '-'}\n{status or '-'}"
            if message:
                text += f" · {message}"
            self.briefing_source_list.addItem(QListWidgetItem(text))

    def _refresh_briefing_section_list(self, summary: BriefingSummary) -> None:
        self.briefing_section_list.blockSignals(True)
        self.briefing_section_list.clear()
        for section in summary.sections:
            item = QListWidgetItem(f"{section.icon or '·'}  {section.label}\n{section.count} items · {section.subtitle}")
            item.setData(Qt.ItemDataRole.UserRole, section.key)
            self.briefing_section_list.addItem(item)
        self.briefing_section_list.blockSignals(False)
        self._select_briefing_list_item(self.selected_briefing_key)

    def _select_briefing_list_item(self, section_key: str) -> None:
        if not hasattr(self, "briefing_section_list"):
            return
        for index in range(self.briefing_section_list.count()):
            item = self.briefing_section_list.item(index)
            if item and item.data(Qt.ItemDataRole.UserRole) == section_key:
                self.briefing_section_list.setCurrentRow(index)
                return

    def _on_briefing_section_clicked(self, item: QListWidgetItem) -> None:
        self.selected_briefing_key = str(item.data(Qt.ItemDataRole.UserRole) or "overview")
        self._set_page(f"briefing:{self.selected_briefing_key}")

    def _render_selected_briefing_section(self) -> None:
        if not hasattr(self, "briefing_detail_layout"):
            return
        section = self.briefing_sections.get(self.selected_briefing_key)
        self._clear_layout(self.briefing_detail_layout)
        if not section:
            empty = QLabel("等待 briefing snapshot。")
            empty.setObjectName("MetaText")
            self.briefing_detail_layout.addWidget(empty)
            self.briefing_detail_layout.addStretch()
            return

        header = QFrame()
        header.setObjectName("Panel")
        header_layout = QVBoxLayout(header)
        title = QLabel(f"{section.label}  ·  {section.count} items")
        title.setObjectName("SectionTitle")
        subtitle = QLabel(section.subtitle or section.key)
        subtitle.setObjectName("MetaText")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        self.briefing_detail_layout.addWidget(header)

        if section.modules:
            for module in section.modules:
                card = QFrame()
                card.setObjectName("Panel")
                card_layout = QVBoxLayout(card)
                module_head = QHBoxLayout()
                module_title = QLabel(module.title or module.module_id or "Module")
                module_title.setObjectName("CardTitle")
                module_head.addWidget(module_title)
                module_head.addStretch()
                if module.tag:
                    tag = QLabel(module.tag)
                    tag.setObjectName("Tag")
                    module_head.addWidget(tag)
                card_layout.addLayout(module_head)
                if module.value:
                    card_layout.addWidget(self._metric_card(module.title or "Total", module.value, module.unit))
                for item in module.items:
                    row = QLabel(f"• {item.text}\n  {item.meta}")
                    row.setObjectName("BriefingItem")
                    row.setWordWrap(True)
                    card_layout.addWidget(row)
                self.briefing_detail_layout.addWidget(card)
        else:
            empty = QLabel("這個 section 目前沒有 modules。")
            empty.setObjectName("MetaText")
            self.briefing_detail_layout.addWidget(empty)
        self.briefing_detail_layout.addStretch()

    def _briefing_freshness_text(self, date_text: str) -> str:
        if not date_text:
            return "date unknown"
        try:
            snapshot_date = datetime.date.fromisoformat(date_text[:10])
        except ValueError:
            return "date unparsed"
        today = datetime.datetime.now().date()
        age_days = (today - snapshot_date).days
        if age_days <= 0:
            return "fresh today"
        return f"stale {age_days} day(s)"

    def _format_time(self, value: str) -> str:
        if not value:
            return "-"
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value

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
        if not hasattr(self, "log_box"):
            return
        self.log_box.append(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "preview_fit_mode", False):
            self._render_preview_pixmap()

    def closeEvent(self, event) -> None:
        try:
            self._discard_auto_empty_history_if_safe("__close__")
        except Exception:
            pass
        try:
            self.chat_client.disconnect()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass
        event.accept()


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
#BriefingItem {
    background: #111722;
    border: 1px solid #252d3b;
    border-radius: 6px;
    padding: 10px;
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
