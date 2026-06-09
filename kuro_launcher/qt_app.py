from __future__ import annotations

import base64
import datetime
import mimetypes
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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
    QtLauncherController,
    RuntimeStatus,
)
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
        self.startup_auto_start_fired = False
        self.last_status: RuntimeStatus | None = None
        self.pet_toggle_buttons: dict[str, QPushButton] = {}
        self.stack_order = ["home", "chat", "briefing", "profile", "pet", "runtime", "settings"]
        self.app_font_stack, self.editor_font_stack = self._load_font_stacks()
        self.chat_client = QtRuntimeChatClient(self)
        self.chat_live_blocks: list[tuple[str, str, str]] = []
        self.chat_base_transcript = ""
        self.chat_attachments: list[dict] = []

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
        sidebar_layout.addWidget(main_label)
        self._add_nav_button(sidebar_layout, "home", "Home")
        self._add_nav_button(sidebar_layout, "chat", "Chat")
        self._add_nav_button(sidebar_layout, "briefing", "Briefing")
        self._add_nav_button(sidebar_layout, "profile", "Profile")
        self._add_nav_button(sidebar_layout, "pet", "Pet Controls")
        self._add_nav_button(sidebar_layout, "runtime", "Runtime")

        sidebar_layout.addStretch()
        self.quick_status = QLabel("status pending")
        self.quick_status.setObjectName("QuickStatus")
        self.quick_status.setWordWrap(True)
        sidebar_layout.addWidget(self.quick_status)
        self._add_nav_button(sidebar_layout, "settings", "⚙  Settings")

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_home_page())
        self.chat_page = self._build_chat_page()
        self.stack.addWidget(self.chat_page)
        self.stack.addWidget(self._build_briefing_page())
        self.stack.addWidget(self._build_workspace_page())
        self.stack.addWidget(self._build_pet_page())
        self.stack.addWidget(self._build_runtime_page())
        self.stack.addWidget(self._build_settings_page())

        shell.addWidget(sidebar)
        shell.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._set_page("home")

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

    def _build_home_page(self) -> QWidget:
        page, layout = self._page(
            "Home",
            "Kuro desktop runtime console",
        )

        service_row = QHBoxLayout()
        for key, label in [
            ("HomeBridge", "Bridge"),
            ("HomeTTS", "TTS"),
            ("HomeLLM", "LLM"),
            ("HomePet", "Pet Shell"),
        ]:
            card = self._status_card(label)
            self.service_labels[key] = card.findChild(QLabel, "StatusValue")
            service_row.addWidget(card)
        layout.addLayout(service_row)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setObjectName("ContentSplitter")

        left = QFrame()
        left.setObjectName("Panel")
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        current_title = QLabel("Current Session")
        current_title.setObjectName("SectionTitle")
        left_layout.addWidget(current_title)
        self.home_profile_label = QLabel("Profile pending")
        self.home_profile_label.setObjectName("MetaText")
        self.home_profile_label.setWordWrap(True)
        left_layout.addWidget(self.home_profile_label)
        self.home_chat_label = QLabel("Chat pending")
        self.home_chat_label.setObjectName("MetaText")
        self.home_chat_label.setWordWrap(True)
        left_layout.addWidget(self.home_chat_label)

        action_row = QHBoxLayout()
        action_row.addWidget(self._command_button("啟動 Profile", self._start_profile))
        action_row.addWidget(self._command_button("Chat", lambda: self._set_page("chat")))
        action_row.addWidget(self._command_button("Pet", lambda: self._set_page("pet")))
        action_row.addStretch()
        left_layout.addLayout(action_row)
        left_layout.addStretch()
        body.addWidget(left)

        right = QFrame()
        right.setObjectName("Panel")
        right_layout = QVBoxLayout(right)
        briefing_title = QLabel("Briefing")
        briefing_title.setObjectName("SectionTitle")
        right_layout.addWidget(briefing_title)
        self.home_briefing_label = QLabel("Briefing pending")
        self.home_briefing_label.setObjectName("MetaText")
        self.home_briefing_label.setWordWrap(True)
        right_layout.addWidget(self.home_briefing_label)
        self.home_briefing_list = QListWidget()
        self.home_briefing_list.setObjectName("SectionList")
        self.home_briefing_list.itemClicked.connect(self._on_briefing_section_clicked)
        right_layout.addWidget(self.home_briefing_list, 1)
        briefing_actions = QHBoxLayout()
        briefing_actions.addWidget(self._command_button("Open Briefing", lambda: self._set_page("briefing")))
        briefing_actions.addWidget(self._command_button("Refresh", self.refresh_briefing))
        briefing_actions.addStretch()
        right_layout.addLayout(briefing_actions)
        body.addWidget(right)

        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 1)
        layout.addWidget(body, 1)
        return page

    def _build_chat_page(self) -> QWidget:
        page, layout = self._page(
            "Chat",
            "同一個桌寵前端的文字與附件入口。",
        )
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
        actions.addWidget(self._command_button("刷新 Briefing", self.refresh_briefing))
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _build_workspace_page(self) -> QWidget:
        page, layout = self._page(
            "Profile",
            "角色、服裝、專案與記憶設定。",
        )
        self.workspace_status = QLabel("Profile ready.")
        self.workspace_status.setObjectName("StatusBanner")
        self.workspace_status.setWordWrap(True)
        layout.addWidget(self.workspace_status)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("WorkspaceTabs")
        self.workspace_tabs.addTab(self._build_character_tab(), "角色")
        self.workspace_tabs.addTab(self._build_outfit_tab(), "衣服")
        self.workspace_tabs.addTab(self._build_project_tab(), "專案")
        self.workspace_tabs.addTab(self._build_memory_tab(), "記憶")
        layout.addWidget(self.workspace_tabs, 1)

        actions = QHBoxLayout()
        actions.addWidget(self._command_button("啟動 Profile", self._start_profile))
        actions.addWidget(self._command_button("套用服裝到 Shell", lambda: self._run_task("apply-outfit", self.controller.apply_outfit)))
        actions.addWidget(self._command_button("重新讀取 Profiles", self._reload_profiles))
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _build_character_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)

        left = QFrame()
        left.setObjectName("Panel")
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        self.character_combo = QComboBox()
        self.character_combo.currentIndexChanged.connect(self._on_character_changed)
        left_layout.addWidget(self._field("角色", self.character_combo))

        self.character_detail = QLabel("")
        self.character_detail.setObjectName("MetaText")
        self.character_detail.setWordWrap(True)
        left_layout.addWidget(self.character_detail)

        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("MetaText")
        left_layout.addWidget(self.preview_meta)

        self.preview_image_label = QLabel("選取角色後會在這裡顯示預覽")
        self.preview_image_label.setObjectName("PreviewImage")
        self.preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image_label.setMinimumHeight(360)
        self.preview_image_label.setWordWrap(True)
        left_layout.addWidget(self.preview_image_label, 1)
        layout.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("Panel")
        right_layout = QVBoxLayout(right)
        prompt_title = QLabel("Prompt Preview")
        prompt_title.setObjectName("SectionTitle")
        right_layout.addWidget(prompt_title)
        self.prompt_tabs = QTabWidget()
        self.prompt_tabs.setObjectName("PromptTabs")
        for key, label in PROMPT_TABS:
            box = QPlainTextEdit()
            box.setObjectName("PromptBox")
            box.setReadOnly(True)
            box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.prompt_boxes[key] = box
            self.prompt_tabs.addTab(box, label)
        right_layout.addWidget(self.prompt_tabs, 1)
        layout.addWidget(right, 1)
        return page

    def _build_outfit_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        self.outfit_combo = QComboBox()
        self.outfit_combo.addItem("帽T", "hoodie")
        self.outfit_combo.addItem("原版", "normal")
        self.outfit_combo.currentIndexChanged.connect(self._on_outfit_changed)
        panel_layout.addWidget(self._field("目前服裝", self.outfit_combo))
        hint = QLabel("服裝選擇仍沿用 pet-electron control server 的 set-outfit command。")
        hint.setObjectName("MetaText")
        hint.setWordWrap(True)
        panel_layout.addWidget(hint)
        panel_layout.addWidget(self._command_button("套用服裝到 Shell", lambda: self._run_task("apply-outfit", self.controller.apply_outfit)))
        panel_layout.addStretch()
        layout.addWidget(panel)
        layout.addStretch()
        return page

    def _build_project_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        panel_layout.addWidget(self._field("專案", self.project_combo))
        self.thinking_combo = QComboBox()
        self.thinking_combo.addItem("Normal", "normal")
        self.thinking_combo.addItem("High", "high")
        self.thinking_combo.addItem("Low", "low")
        self.thinking_combo.currentIndexChanged.connect(self._on_thinking_changed)
        panel_layout.addWidget(self._field("Thinking Power", self.thinking_combo))
        self.project_detail = QLabel("")
        self.project_detail.setObjectName("MetaText")
        self.project_detail.setWordWrap(True)
        panel_layout.addWidget(self.project_detail)
        panel_layout.addStretch()
        layout.addWidget(panel)
        layout.addStretch()
        return page

    def _build_chat_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(10)

        hint = QLabel("聊天頁整合既有 chat_history，訊息與附件會送進同一個桌寵前端。")
        hint.setObjectName("MetaText")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.chat_connection_status = QLabel("Runtime Chat 尚未連線。")
        self.chat_connection_status.setObjectName("StatusBanner")
        self.chat_connection_status.setWordWrap(True)
        outer.addWidget(self.chat_connection_status)

        actions = QHBoxLayout()
        actions.addWidget(self._command_button("連線 Runtime Chat", self._connect_chat))
        actions.addWidget(self._command_button("斷線", self._disconnect_chat))
        actions.addWidget(self._command_button("中斷輸出", self._interrupt_chat))
        actions.addStretch()
        outer.addLayout(actions)

        history_actions = QHBoxLayout()
        history_actions.addWidget(
            self._command_button("更新列表", self._refresh_history_list)
        )
        history_actions.addWidget(
            self._command_button(
                "同步選取聊天",
                self._apply_selected_history,
            )
        )
        history_actions.addWidget(
            self._command_button(
                "建立新聊天",
                self._create_chat_history,
            )
        )
        history_actions.addWidget(self._command_button("刪除聊天", self._delete_selected_history))
        history_actions.addStretch()
        outer.addLayout(history_actions)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)
        self.history_list = QListWidget()
        self.history_list.setObjectName("SectionList")
        self.history_list.setMinimumWidth(340)
        self.history_list.itemSelectionChanged.connect(self._on_history_selected)
        layout.addWidget(self.history_list, 0)
        self.history_transcript = QTextEdit()
        self.history_transcript.setObjectName("TranscriptBox")
        self.history_transcript.setReadOnly(True)
        layout.addWidget(self.history_transcript, 1)
        outer.addLayout(layout, 1)

        attachment_row = QHBoxLayout()
        attachment_row.setSpacing(10)
        attachment_row.addWidget(self._command_button("附加檔案", self._add_chat_attachments))
        attachment_row.addWidget(self._command_button("清除附件", self._clear_chat_attachments))
        self.chat_attachment_label = QLabel("尚未附加檔案。")
        self.chat_attachment_label.setObjectName("MetaText")
        self.chat_attachment_label.setWordWrap(True)
        attachment_row.addWidget(self.chat_attachment_label, 1)
        outer.addLayout(attachment_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.chat_input = QPlainTextEdit()
        self.chat_input.setObjectName("PromptBox")
        self.chat_input.setPlaceholderText("輸入要送給目前 runtime 角色的訊息。")
        self.chat_input.setMaximumHeight(96)
        input_row.addWidget(self.chat_input, 1)
        self.chat_send_button = self._command_button("送出", self._send_chat_text)
        input_row.addWidget(self.chat_send_button)
        outer.addLayout(input_row)
        return page

    def _build_memory_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(10)

        hint = QLabel("記憶頁直接操作目前角色的 canonical long_term.json；LLM 在線時會同步刷新 runtime 記憶 prompt。")
        hint.setObjectName("MetaText")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        actions = QHBoxLayout()
        actions.addWidget(self._command_button("新增", self._add_memory_dialog))
        actions.addWidget(self._command_button("啟停", self._toggle_selected_memory))
        actions.addWidget(self._command_button("批准", self._approve_selected_memory))
        actions.addWidget(self._command_button("拒絕", self._reject_selected_memory))
        actions.addWidget(self._command_button("刪除", self._delete_selected_memory))
        actions.addWidget(self._command_button("整理", self._compact_memory))
        actions.addWidget(
            self._command_button(
                "刷新 Runtime 記憶 Prompt",
                lambda: self._run_task("refresh-memory", self.controller.refresh_memory_prompt),
            )
        )
        actions.addWidget(self._command_button("更新列表", self._refresh_memory_list))
        actions.addStretch()
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
        page, layout = self._page(
            "Pet Controls",
            "純桌寵控制面板：直接控制 pet-electron，狀態來自 pet control server `/status`。",
        )
        self.pet_status_label = QLabel("Pet status pending")
        self.pet_status_label.setObjectName("StatusBanner")
        self.pet_status_label.setWordWrap(True)
        layout.addWidget(self.pet_status_label)

        command_panel = QFrame()
        command_panel.setObjectName("Panel")
        command_layout = QVBoxLayout(command_panel)
        command_title = QLabel("Quick Commands")
        command_title.setObjectName("SectionTitle")
        command_layout.addWidget(command_title)
        command_row = QHBoxLayout()
        for label, task_name, fn in [
            ("停止輸出", "pet-interrupt", self.controller.interrupt_pet),
            ("顯示桌寵", "pet-show", self.controller.show_pet),
            ("移到下一個螢幕", "pet-move-display", self.controller.move_pet_next_display),
            ("重載桌寵前端", "pet-reload", self.controller.reload_pet_frontend),
            ("關閉桌寵", "pet-close", self.controller.stop_pet_electron),
            ("開桌寵 Shell", "open-pet", self.controller.launch_pet_electron),
        ]:
            command_row.addWidget(
                self._command_button(label, lambda task_name=task_name, fn=fn: self._run_task(task_name, fn))
            )
        command_row.addStretch()
        command_layout.addLayout(command_row)
        layout.addWidget(command_panel)

        toggle_panel = QFrame()
        toggle_panel.setObjectName("Panel")
        toggle_layout = QVBoxLayout(toggle_panel)
        toggle_title = QLabel("Live Toggles")
        toggle_title.setObjectName("SectionTitle")
        toggle_layout.addWidget(toggle_title)
        toggle_grid = QGridLayout()
        toggle_grid.setHorizontalSpacing(12)
        toggle_grid.setVerticalSpacing(12)
        toggles = [
            ("mic-toggle", "麥克風"),
            ("toggle-camera", "攝影機"),
            ("toggle-screen", "螢幕分享"),
            ("set-game-mode", "Game mode"),
        ]
        for index, (action, label) in enumerate(toggles):
            button = QPushButton(label)
            button.setObjectName("ToggleButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, action=action: self._run_task(
                    f"pet-toggle:{action}",
                    lambda action=action, checked=checked: self.controller.set_pet_toggle(action, checked),
                )
            )
            self.pet_toggle_buttons[action] = button
            toggle_grid.addWidget(button, index // 4, index % 4)
        toggle_layout.addLayout(toggle_grid)
        layout.addWidget(toggle_panel)

        expression_panel = QFrame()
        expression_panel.setObjectName("Panel")
        expression_layout = QGridLayout(expression_panel)
        expression_layout.setHorizontalSpacing(12)
        expression_layout.setVerticalSpacing(12)
        expression_title = QLabel("Expression / Outfit")
        expression_title.setObjectName("SectionTitle")
        expression_layout.addWidget(expression_title, 0, 0, 1, 2)
        self.pet_expression_combo = QComboBox()
        for expression_id, label in self.controller.expression_options():
            self.pet_expression_combo.addItem(label, expression_id)
        expression_layout.addWidget(self._field("表情", self.pet_expression_combo), 1, 0)
        expression_layout.addWidget(
            self._command_button(
                "套用表情",
                lambda: self._run_task(
                    "pet-expression",
                    lambda: self.controller.set_expression(str(self.pet_expression_combo.currentData() or "neutral")),
                ),
            ),
            1,
            1,
        )
        self.pet_outfit_combo = QComboBox()
        self.pet_outfit_combo.addItem("帽T", "hoodie")
        self.pet_outfit_combo.addItem("原版", "normal")
        self.pet_outfit_combo.currentIndexChanged.connect(self._on_pet_outfit_changed)
        expression_layout.addWidget(self._field("服裝", self.pet_outfit_combo), 2, 0)
        expression_layout.addWidget(
            self._command_button("套用服裝", lambda: self._run_task("apply-outfit", self.controller.apply_outfit)),
            2,
            1,
        )
        layout.addWidget(expression_panel)

        self.pet_detail = QLabel("")
        self.pet_detail.setObjectName("MetaText")
        self.pet_detail.setWordWrap(True)
        layout.addWidget(self.pet_detail, 1)
        return page

    def _build_runtime_page(self) -> QWidget:
        page, layout = self._page(
            "Runtime",
            "Bridge / TTS / LLM / pet-electron 仍沿用原本 pipeline；這裡只提供統一控制入口。",
        )
        self.runtime_status_label = QLabel("Runtime status pending")
        self.runtime_status_label.setObjectName("StatusBanner")
        self.runtime_status_label.setWordWrap(True)
        layout.addWidget(self.runtime_status_label)
        self.runtime_detail = QLabel("")
        self.runtime_detail.setObjectName("MetaText")
        self.runtime_detail.setWordWrap(True)
        layout.addWidget(self.runtime_detail)

        actions = QHBoxLayout()
        actions.addWidget(self._command_button("啟動 Profile", self._start_profile))
        actions.addWidget(self._command_button("停止 Runtime", lambda: self._run_task("stop-runtime", self.controller.stop_profile)))
        actions.addWidget(self._command_button("Bridge 開關", lambda: self._run_task("toggle-bridge", self.controller.toggle_bridge)))
        actions.addWidget(self._command_button("開桌寵 Shell", lambda: self._run_task("open-pet", self.controller.launch_pet_electron)))
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._page(
            "Settings",
            "低階設定、端點與診斷工具。",
        )
        runtime_panel = QFrame()
        runtime_panel.setObjectName("Panel")
        runtime_layout = QVBoxLayout(runtime_panel)
        runtime_title = QLabel("Runtime Settings")
        runtime_title.setObjectName("SectionTitle")
        runtime_layout.addWidget(runtime_title)
        runtime_actions = QHBoxLayout()
        runtime_actions.addWidget(self._command_button("套用桌寵後端端點", lambda: self._run_task("pet-backend-config", self.controller.apply_pet_backend_config)))
        runtime_actions.addWidget(self._command_button("Bridge 重啟", lambda: self._run_task("restart-bridge", self.controller.restart_bridge)))
        runtime_actions.addWidget(self._command_button("Translate Debug", lambda: self._run_task("translate-debug", self.controller.translate_debug)))
        runtime_actions.addStretch()
        runtime_layout.addLayout(runtime_actions)
        layout.addWidget(runtime_panel)

        pet_panel = QFrame()
        pet_panel.setObjectName("Panel")
        pet_layout = QVBoxLayout(pet_panel)
        pet_title = QLabel("Pet Settings")
        pet_title.setObjectName("SectionTitle")
        pet_layout.addWidget(pet_title)
        pet_grid = QGridLayout()
        pet_grid.setHorizontalSpacing(12)
        pet_grid.setVerticalSpacing(12)
        for index, (action, label) in enumerate([
            ("toggle-browser", "Browser Panel"),
            ("set-live2d-inspector", "Live2D Inspector"),
        ]):
            button = QPushButton(label)
            button.setObjectName("ToggleButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, action=action: self._run_task(
                    f"pet-toggle:{action}",
                    lambda action=action, checked=checked: self.controller.set_pet_toggle(action, checked),
                )
            )
            self.pet_toggle_buttons[action] = button
            pet_grid.addWidget(button, index // 2, index % 2)
        pet_layout.addLayout(pet_grid)
        layout.addWidget(pet_panel)

        path_panel = QFrame()
        path_panel.setObjectName("Panel")
        path_layout = QVBoxLayout(path_panel)
        path_title = QLabel("Paths")
        path_title.setObjectName("SectionTitle")
        path_layout.addWidget(path_title)
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

        self.log_box = QTextEdit()
        self.log_box.setObjectName("LogBox")
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box, 1)

        actions = QHBoxLayout()
        actions.addWidget(self._command_button("刷新狀態", self.refresh_status))
        actions.addWidget(self._command_button("開 Logs 目錄", self.controller.open_logs_dir))
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _field(self, label: str, widget: QWidget) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        layout.addWidget(label_widget)
        layout.addWidget(widget)
        return box

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

    def _command_button(self, label: str, callback: Callable[[], object]) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("CommandButton")
        button.clicked.connect(lambda _checked=False: callback())
        return button

    def _set_page(self, key: str) -> None:
        stack_key = key
        if key.startswith("briefing:"):
            stack_key = "briefing"
            self.selected_briefing_key = key.split(":", 1)[1] or "overview"
            self._select_briefing_list_item(self.selected_briefing_key)
            self._render_selected_briefing_section()
        elif key == "workspace":
            stack_key = "profile"
        elif key == "diagnostics":
            stack_key = "settings"

        self.stack.setCurrentIndex(self.stack_order.index(stack_key))
        for page_key, button in self.nav_buttons.items():
            checked = page_key == stack_key
            button.setChecked(checked)

    def _refresh_profile_controls(self) -> None:
        combos = [self.character_combo, self.project_combo, self.outfit_combo, self.thinking_combo]
        if hasattr(self, "pet_outfit_combo"):
            combos.append(self.pet_outfit_combo)
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
        if hasattr(self, "pet_outfit_combo"):
            self._set_combo_by_data(self.pet_outfit_combo, self.controller.outfit_id)
        self._set_combo_by_data(self.thinking_combo, self.controller.thinking_power)
        for combo in combos:
            combo.blockSignals(False)

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
        if hasattr(self, "pet_outfit_combo"):
            self.pet_outfit_combo.blockSignals(True)
            self._set_combo_by_data(self.pet_outfit_combo, self.controller.outfit_id)
            self.pet_outfit_combo.blockSignals(False)
        self._update_preview_asset()

    def _on_pet_outfit_changed(self, _index: int = -1) -> None:
        self.controller.set_outfit(str(self.pet_outfit_combo.currentData() or "normal"))
        self.outfit_combo.blockSignals(True)
        self._set_combo_by_data(self.outfit_combo, self.controller.outfit_id)
        self.outfit_combo.blockSignals(False)
        self._update_preview_asset()

    def _on_thinking_changed(self, _index: int = -1) -> None:
        self.controller.set_thinking_power(str(self.thinking_combo.currentData() or "normal"))
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
        asset = self.controller.preview_asset()
        if asset.path:
            pixmap = QPixmap(asset.path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    560,
                    380,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_image_label.setPixmap(scaled)
                self.preview_image_label.setText("")
                self.preview_meta.setText(f"{asset.kind} · {asset.path}")
                return
        self.preview_image_label.setPixmap(QPixmap())
        self.preview_image_label.setText(asset.error or "這個角色目前沒有可直接顯示的預覽圖")
        self.preview_meta.setText(asset.kind or "")

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

        self.history_list.blockSignals(True)
        self.history_list.clear()
        records = self.controller.read_history_records()
        selected_row = 0
        for record in records:
            item = QListWidgetItem(
                f"{record.title}\n{record.timestamp or '-'} · {record.preview or '沒有摘要'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record.uid)
            self.history_list.addItem(item)
            if record.uid == previous_uid:
                selected_row = self.history_list.count() - 1
        self.history_list.blockSignals(False)
        if records:
            self.history_list.setCurrentRow(selected_row)
            self.selected_history_uid = str(self.history_list.item(selected_row).data(Qt.ItemDataRole.UserRole) or "")
            self._render_history_messages(self.selected_history_uid)
        else:
            self.selected_history_uid = ""
            self.history_transcript.setPlainText("這個角色目前還沒有聊天紀錄。")

    def _on_history_selected(self) -> None:
        item = self.history_list.currentItem()
        if not item:
            return
        self.selected_history_uid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self._render_history_messages(self.selected_history_uid)

    def _render_history_messages(self, history_uid: str) -> None:
        messages = self.controller.read_history_timeline(history_uid)
        if not messages:
            self.chat_base_transcript = "這段聊天目前沒有可顯示的訊息。"
            self.chat_live_blocks = []
            self.history_transcript.setPlainText(self.chat_base_transcript)
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

    def _connect_chat(self) -> None:
        ws_url = f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws"
        self.chat_client.connect_to(ws_url)
        self._set_chat_status(f"Runtime Chat connecting: {ws_url}", error=False)

    def _disconnect_chat(self) -> None:
        self.chat_client.disconnect()
        self._set_chat_status("Runtime Chat 已斷線。", error=True)

    def _interrupt_chat(self) -> None:
        sent = self.chat_client.send_interrupt()
        if sent:
            self._append_log(f"[{log_ts()}] 已送出 Runtime Chat 中斷。")
        else:
            self._run_task("pet-interrupt", self.controller.interrupt_pet)

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
        if not hasattr(self, "chat_attachment_label"):
            return
        if not self.chat_attachments:
            self.chat_attachment_label.setText("尚未附加檔案。")
            return
        names = ", ".join(str(item.get("name") or "file") for item in self.chat_attachments[:4])
        if len(self.chat_attachments) > 4:
            names += f" +{len(self.chat_attachments) - 4}"
        self.chat_attachment_label.setText(f"已附加 {len(self.chat_attachments)} 個：{names}")

    def _visible_chat_input_text(self, text: str, attachments: list[dict]) -> str:
        names = [str(item.get("name") or "file") for item in attachments]
        attachment_line = f"附件：{', '.join(names)}" if names else ""
        return "\n".join(part for part in [text, attachment_line] if part).strip()

    def _send_chat_text(self) -> None:
        text = self.chat_input.toPlainText().strip()
        attachments = list(self.chat_attachments)
        if not text and not attachments:
            return
        self.pending_chat_submit = {"text": text, "attachments": attachments}
        self.chat_send_button.setEnabled(False)
        self._run_task(
            "pet-send-text",
            lambda text=text, attachments=attachments: self.controller.send_pet_text(text, attachments),
        )

    def _apply_selected_history(self) -> None:
        if not self.selected_history_uid:
            QMessageBox.information(self, "聊天記錄", "請先選擇一段聊天。")
            return
        if self.chat_client.connected:
            if self.chat_client.select_history(self.selected_history_uid):
                self._append_log(f"[{log_ts()}] 已透過 Runtime Chat 同步聊天：{self.selected_history_uid}")
                self._clear_pending_history_choice()
            return
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
        if self.chat_client.connected:
            self.chat_client.create_history(force_new=True)
            self._clear_pending_history_choice()
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
        self.chat_connection_status.setProperty("error", error)
        self.chat_connection_status.style().unpolish(self.chat_connection_status)
        self.chat_connection_status.style().polish(self.chat_connection_status)

    def _on_chat_state_changed(self, state: str, connected: bool) -> None:
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

    def _on_chat_client_changed(self, client_uid: str, conf_name: str, conf_uid: str) -> None:
        suffix = f" · {conf_name or conf_uid or '-'} · client={client_uid[:8] or '-'}"
        self._set_chat_status(f"Runtime Chat 已連線{suffix}", error=False)

    def _on_chat_error(self, message: str) -> None:
        self._append_log(f"[{log_ts()}] Runtime Chat error: {message}")
        self._set_chat_status(f"Runtime Chat 錯誤：{message}", error=True)

    def _on_chat_history_changed(self, history_uid: str, _title: str) -> None:
        if history_uid:
            self.selected_history_uid = history_uid
        self._refresh_history_list()
        self._refresh_memory_list()
        self._refresh_prompt_boxes()

    def _on_chat_assistant_text_changed(self, text: str) -> None:
        if not text:
            return
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
        if not history_uid:
            QMessageBox.information(self, "聊天記錄", "請先選擇要刪除的聊天。")
            return

        title = current_item.text().splitlines()[0] if current_item else history_uid
        answer = QMessageBox.question(
            self,
            "刪除聊天記錄",
            f"確定要刪除這段聊天嗎？\n\n{title}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.chat_client.connected:
            if self.chat_client.delete_history(history_uid):
                self._append_log(f"[{log_ts()}] 已透過 Runtime Chat 刪除聊天：{history_uid}")
            return
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
        if name == "pet-send-text":
            self.chat_send_button.setEnabled(True)
            pending = self.pending_chat_submit or {}
            text = str(pending.get("text") or "")
            attachments = list(pending.get("attachments") or [])
            self.pending_chat_submit = None
            self.chat_input.setPlainText("")
            self.chat_attachments = []
            self._render_chat_attachments()
            self.chat_live_blocks.append(("User", self._chat_timestamp(), self._visible_chat_input_text(text, attachments)))
            self.chat_live_blocks.append(("Kuro", self._chat_timestamp(), ""))
            self._render_chat_transcript_with_live()
            self._set_chat_status("已送出到桌寵，等待回覆。", error=False)
            if isinstance(result, dict):
                inner = result.get("result") if isinstance(result.get("result"), dict) else {}
                warnings = inner.get("warnings") if isinstance(inner, dict) else None
                if isinstance(warnings, list) and warnings:
                    QMessageBox.warning(self, "Kuro Desktop Console", "\n".join(str(item) for item in warnings))
        self._append_log(f"[{log_ts()}] task done: {name}")
        self._set_action_status(f"已完成：{name}")
        self.refresh_status()
        if name in {"open-pet", "start-profile"}:
            self.refresh_briefing()
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
        if name == "pet-send-text":
            self.chat_send_button.setEnabled(True)
            self.pending_chat_submit = None
        self._append_log(f"[{log_ts()}] task failed: {name} / {message}")
        self._set_action_status(f"失敗：{name} / {message}", error=True)
        QMessageBox.warning(self, "Kuro Desktop Console", message)
        self.refresh_status()

    def _set_action_status(self, text: str, *, error: bool = False) -> None:
        if not hasattr(self, "workspace_status"):
            return
        self.workspace_status.setText(text)
        self.workspace_status.setProperty("error", error)
        self.workspace_status.style().unpolish(self.workspace_status)
        self.workspace_status.style().polish(self.workspace_status)

    def _apply_status(self, status: RuntimeStatus) -> None:
        self.last_status = status
        values = {
            "HomeBridge": status.bridge,
            "HomeTTS": status.tts,
            "HomeLLM": status.llm,
            "HomePet": status.pet_shell,
        }
        for key, online in values.items():
            label = self.service_labels.get(key)
            if not label:
                continue
            label.setText("online" if online else "offline")
            label.setProperty("online", online)
            label.style().unpolish(label)
            label.style().polish(label)

        ws = "connected" if status.ws_connected else "disconnected"
        self.quick_status.setText(
            f"Bridge {'on' if status.bridge else 'off'} · "
            f"LLM {'on' if status.llm else 'off'} · Pet {status.pet_mode or '-'} · WS {ws}"
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
        if hasattr(self, "home_profile_label"):
            self.home_profile_label.setText(
                "\n".join(
                    [
                        f"profile: {status.conf_name or '-'}",
                        f"pet_mode: {status.pet_mode or '-'}",
                        f"ws: {'connected' if status.ws_connected else 'disconnected'}",
                        f"ai_state: {self._compact_label_text(status.ai_state, 80) or '-'}",
                    ]
                )
            )
        if hasattr(self, "home_chat_label"):
            self.home_chat_label.setText(
                "\n".join(
                    [
                        f"history: {self._compact_label_text(status.current_history_title or status.current_history_uid, 120) or '-'}",
                        f"latest_user: {self._compact_label_text(status.latest_user_text, 120) or '-'}",
                        f"latest_assistant: {self._compact_label_text(status.latest_assistant_text, 120) or '-'}",
                    ]
                )
            )
        self._sync_pet_controls(status)
        if hasattr(self, "workspace_status") and not status.llm:
            self._set_action_status(
                "Runtime 尚未完整在線：聊天同步、建立新聊天、刷新記憶 prompt 需要先啟動 Profile。",
                error=True,
            )

    def _sync_pet_controls(self, status: RuntimeStatus) -> None:
        state_by_action = {
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
            for combo_name in ("outfit_combo", "pet_outfit_combo"):
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
                        f"reader_visible: {status.reader_visible}",
                        f"briefing_visible: {status.briefing_visible}",
                        f"game_mode: {status.pet_game_mode}",
                        f"mic_enabled: {status.mic_enabled}",
                        f"camera_enabled: {status.camera_enabled}",
                        f"screen_enabled: {status.screen_enabled}",
                        f"browser_panel_enabled: {status.browser_panel_enabled}",
                        f"current_history_uid: {status.current_history_uid or '-'}",
                        f"current_history_title: {status.current_history_title or '-'}",
                        f"latest_user_text: {status.latest_user_text or '-'}",
                        f"latest_assistant_text: {status.latest_assistant_text or '-'}",
                    ]
                )
            )

    def _pet_toggle_label(self, action: str, checked: bool) -> str:
        base = {
            "mic-toggle": "麥克風",
            "toggle-camera": "攝影機",
            "toggle-screen": "螢幕分享",
            "toggle-browser": "Browser Panel",
            "set-game-mode": "Game mode",
            "set-live2d-inspector": "Live2D Inspector",
        }.get(action, action)
        return f"{base}  {'ON' if checked else 'OFF'}"

    def _apply_briefing(self, summary: BriefingSummary) -> None:
        if not summary.ok:
            self.briefing_meta.setText(f"Briefing offline: {summary.error}")
            self.briefing_sections = {}
            self._clear_layout(self.briefing_detail_layout)
            if hasattr(self, "home_briefing_label"):
                self.home_briefing_label.setText(f"Briefing offline: {summary.error}")
            if hasattr(self, "home_briefing_list"):
                self.home_briefing_list.clear()
            return

        self.briefing_sections = {section.key: section for section in summary.sections}
        stale_text = self._briefing_freshness_text(summary.date)
        self.briefing_meta.setText(
            f"{summary.title} · date={summary.date or '-'} · "
            f"updated={self._format_time(summary.updated_at)} · {stale_text}"
        )
        self._update_briefing_nav_counts(summary)
        self._refresh_briefing_section_list(summary)
        if self.selected_briefing_key not in self.briefing_sections:
            self.selected_briefing_key = "overview"
        self._render_selected_briefing_section()
        self._refresh_home_briefing(summary, stale_text)

    def _update_briefing_nav_counts(self, summary: BriefingSummary) -> None:
        counts = {key: count for key, _label, count in summary.section_counts}
        button = self.nav_buttons.get("briefing")
        if not button:
            return
        total = sum(counts.values())
        button.setText(f"{self.nav_base_labels.get('briefing', 'Briefing')}    {total}")

    def _refresh_home_briefing(self, summary: BriefingSummary, stale_text: str) -> None:
        if hasattr(self, "home_briefing_label"):
            self.home_briefing_label.setText(
                f"{summary.title or 'Briefing'} · {summary.date or '-'} · {stale_text}"
            )
        if not hasattr(self, "home_briefing_list"):
            return
        self.home_briefing_list.blockSignals(True)
        self.home_briefing_list.clear()
        for section in summary.sections[:6]:
            item = QListWidgetItem(
                f"{section.label}\n{section.count} items · {section.subtitle or section.key}"
            )
            item.setData(Qt.ItemDataRole.UserRole, section.key)
            self.home_briefing_list.addItem(item)
        self.home_briefing_list.blockSignals(False)

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

    def closeEvent(self, event) -> None:
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
#Panel, #StatusCard, #MetricCard {
    background: #171c27;
    border: 1px solid #303849;
    border-radius: 8px;
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
#StatusValue[online="true"] {
    color: #70e28a;
}
#MetricValue {
    color: #ffffff;
    font-size: 28px;
    font-weight: 800;
}
#Tag {
    color: #bfa8ff;
    background: #251d3a;
    border: 1px solid #41315f;
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
    background: #7b61ff;
    border: 0;
    border-radius: 7px;
    color: white;
    font-weight: 800;
    padding: 10px 14px;
}
#CommandButton:hover {
    background: #8f78ff;
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
    background: #183328;
    border-color: #376c55;
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
}
#SectionList::item:selected {
    background: #243044;
    color: #ffffff;
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
    border: 1px solid #303849;
    border-radius: 8px;
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
