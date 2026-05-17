import datetime
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from tkinter import Label as TkLabel, PhotoImage, messagebox

import customtkinter as ctk


def _bootstrap_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(getattr(sys, "_MEIPASS")).resolve()
    else:
        base_dir = Path(__file__).parent.resolve()

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    return base_dir


BASE_DIR = _bootstrap_base_dir()

from kuro_launcher.config import AppConfig, load_config
from kuro_launcher.procs import ManagedProc
from kuro_launcher.project_manager import (
    ProjectDefinition,
    list_project_definitions,
)
from kuro_launcher.runtime_conf import build_runtime_conf, write_runtime_conf
from kuro_launcher.services import (
    probe_tts,
    start_bridge,
    start_llm,
    start_tts,
    validate_profile_assets,
)
from kuro_launcher.utils import (
    build_logs_dir,
    get_listening_pid_windows,
    http_get_json,
    http_post_json,
    load_env_file,
    log_ts,
    port_is_open,
    read_yaml_file,
    sanitize_ascii,
    strip_ansi_and_ctrl,
    taskkill_tree,
)


@dataclass(frozen=True)
class CharacterRecord:
    yaml_path: Path
    conf_name: str
    conf_uid: str
    live2d_model_name: str
    avatar: str
    persona_prompt_path: str
    default_project_id: str


@dataclass(frozen=True)
class HistoryRecord:
    uid: str
    title: str
    preview: str
    timestamp: str
    is_empty: bool


PALETTE = {
    "app_bg": "#edf6ff",
    "panel_bg": "#ffffff",
    "panel_soft": "#f7fbff",
    "panel_alt": "#f2f7ff",
    "panel_border": "#d7e4f4",
    "textbox_bg": "#fcfdff",
    "textbox_border": "#d9e4f5",
    "text": "#20304a",
    "muted": "#64748b",
    "accent_pink": "#f472b6",
    "accent_pink_hover": "#ec4899",
    "accent_blue": "#60a5fa",
    "accent_blue_hover": "#3b82f6",
    "accent_lavender": "#a78bfa",
    "accent_lavender_hover": "#8b5cf6",
    "accent_soft": "#e0edff",
    "success": "#38bdf8",
    "warning": "#f59e0b",
}


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

FONT_UI = "Microsoft JhengHei UI"
FONT_MONO = "Cascadia Mono"


def ui_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_UI, size=size, weight=weight)


def mono_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_MONO, size=size, weight=weight)


class StatusBadge(ctk.CTkFrame):
    def __init__(self, master, name: str):
        super().__init__(
            master,
            corner_radius=18,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        self.grid_columnconfigure(1, weight=1)
        self._name = name
        self.dot = ctk.CTkLabel(self, text="●", text_color=PALETTE["warning"], width=18)
        self.dot.grid(row=0, column=0, padx=(12, 6), pady=8)
        self.label = ctk.CTkLabel(
            self,
            text=f"{name} · Offline",
            font=ui_font(12, "bold"),
            anchor="w",
            text_color=PALETTE["text"],
        )
        self.label.grid(row=0, column=1, padx=(0, 12), sticky="w")

    def set_status(self, online: bool) -> None:
        self.dot.configure(text_color=PALETTE["success"] if online else PALETTE["warning"])
        self.label.configure(text=f"{self._name} · {'Online' if online else 'Offline'}")


def _setup_runtime_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher.combined.log"

    class _Tee:
        def __init__(self, stream_a, stream_b):
            self.stream_a = stream_a
            self.stream_b = stream_b

        def write(self, chunk):
            try:
                self.stream_a.write(chunk)
            except Exception:
                pass
            try:
                self.stream_b.write(chunk)
            except Exception:
                pass

        def flush(self):
            try:
                self.stream_a.flush()
            except Exception:
                pass
            try:
                self.stream_b.flush()
            except Exception:
                pass

    file_handle = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, file_handle)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, file_handle)  # type: ignore[assignment]
    return log_path


def _resolve_repo_path(repo_root: Path, raw_path: str) -> Optional[Path]:
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (repo_root / candidate).resolve()


def _read_text_maybe(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return ""
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "cp936", "ascii"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _pretty_path(path: Optional[Path], root: Path) -> str:
    if path is None:
        return "(未設定)"
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path)


def _normalize_token(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _compact_history_text(content: str, max_len: int = 72) -> str:
    if not isinstance(content, str):
        return ""
    compact = " ".join(content.replace("\r", " ").replace("\n", " ").split())
    compact = compact.strip(" \t\r\n\"'`")
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip(" .,!?;:") + "..."


def _derive_history_title(content: str) -> str:
    return _compact_history_text(content, max_len=28)


def _format_history_timestamp(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(raw)
        return dt.strftime("%m/%d %H:%M")
    except ValueError:
        return raw[:16]


class LauncherApp(ctk.CTk):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self.live2d_catalog = self._load_live2d_catalog()

        self.proc_bridge: Optional[ManagedProc] = None
        self.proc_tts: Optional[ManagedProc] = None
        self.proc_llm: Optional[ManagedProc] = None
        self.proc_pet_electron: Optional[subprocess.Popen] = None
        self.current_run_id: Optional[str] = None

        self._log_q: queue.Queue[str] = queue.Queue()
        self._main_thread_id = threading.get_ident()

        self.character_records: Dict[str, CharacterRecord] = {}
        self.project_records: Dict[str, ProjectDefinition] = {}
        self.history_records: Dict[str, HistoryRecord] = {}
        self.character_var = ctk.StringVar(value="")
        self.project_var = ctk.StringVar(value="")
        self.history_var = ctk.StringVar(value="")
        self.pet_base_url_var = ctk.StringVar(value=self.cfg.llm_url)
        self.pet_ws_url_var = ctk.StringVar(
            value=f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws"
        )

        self._prompt_texts: Dict[str, str] = {}
        self.selection_view_var = ctk.StringVar(value="角色")
        self.preview_mode_var = ctk.StringVar(value="角色預覽")
        self.prompt_view_var = ctk.StringVar(value="角色")
        self._character_radio_buttons: list[ctk.CTkRadioButton] = []
        self._project_radio_buttons: list[ctk.CTkRadioButton] = []
        self._history_radio_buttons: list[ctk.CTkRadioButton] = []
        self._preview_photo: Optional[PhotoImage] = None
        self._force_new_history_on_start = False
        self._transcript_signature = ""
        self._pet_shell_online = False
        self._runtime_history_uid = ""
        self.pet_toggle_vars: Dict[str, ctk.StringVar] = {}

        self.title("Kuro Launcher")
        self.geometry("1380x820")
        self.minsize(1160, 720)
        self.configure(fg_color=PALETTE["app_bg"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self._refresh_character_list()
        self._refresh_project_list()
        self.after(120, self._drain_log_queue)
        self.after(600, self._tick_status)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        shell.grid_columnconfigure(0, weight=0, minsize=198)
        shell.grid_columnconfigure(1, weight=4, uniform="workspace")
        shell.grid_columnconfigure(2, weight=6, uniform="workspace")
        shell.grid_rowconfigure(0, weight=4)
        shell.grid_rowconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(
            shell,
            width=198,
            corner_radius=22,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        sidebar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 14))
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="Kuro Launcher",
            font=ui_font(24, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(18, 4))
        ctk.CTkLabel(
            sidebar,
            text="角色與專案執行台",
            font=ui_font(12),
            text_color=PALETTE["muted"],
        ).grid(row=1, column=0, sticky="w", padx=16)

        controls = ctk.CTkFrame(sidebar, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="new", padx=16, pady=(22, 0))
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            controls,
            text="控制",
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            controls,
            text="啟停角色與開啟桌寵",
            font=ui_font(11),
            text_color=PALETTE["muted"],
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))
        self._action_button(controls, "啟動角色", self.on_start_profile, row=2, primary=True)
        self._action_button(controls, "停止角色", self.on_stop_profile, row=3)
        self._action_button(controls, "開 Electron", self.on_open_electron, row=4)
        self._action_button(controls, "Logs", self.on_open_logs_dir, row=5)

        pet_controls = ctk.CTkFrame(sidebar, fg_color="transparent")
        pet_controls.grid(row=3, column=0, sticky="new", padx=16, pady=(18, 0))
        pet_controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            pet_controls,
            text="桌寵",
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.pet_status_label = ctk.CTkLabel(
            pet_controls,
            text="桌寵 shell 尚未連線。",
            font=ui_font(11),
            text_color=PALETTE["muted"],
            anchor="w",
        )
        self.pet_status_label.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        pet_button_bar = ctk.CTkFrame(pet_controls, fg_color="transparent")
        pet_button_bar.grid(row=2, column=0, sticky="ew")
        pet_button_bar.grid_columnconfigure(0, weight=1)
        self._configure_pet_control_bar(pet_button_bar)

        badge_column = ctk.CTkFrame(sidebar, fg_color="transparent")
        badge_column.grid(row=4, column=0, sticky="sew", padx=16, pady=(16, 16))
        badge_column.grid_columnconfigure(0, weight=1)
        self.badges = {
            "Bridge": StatusBadge(badge_column, "Bridge"),
            "TTS": StatusBadge(badge_column, "TTS"),
            "LLM": StatusBadge(badge_column, "LLM"),
        }
        for idx, badge in enumerate(self.badges.values()):
            badge.grid(row=idx, column=0, sticky="ew", pady=(0 if idx == 0 else 8, 0))

        center_panel = ctk.CTkFrame(shell, fg_color="transparent")
        center_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
        center_panel.grid_columnconfigure(0, weight=1)
        center_panel.grid_rowconfigure(0, weight=4)
        center_panel.grid_rowconfigure(1, weight=5)

        selection_card, selection_body = self._build_card(
            center_panel,
            row=0,
            title="角色 / 專案 / 聊天",
            subtitle="選擇目前要操作的項目。",
            body_fill="both",
            body_expand=True,
        )
        selection_body.grid_columnconfigure(0, weight=1)
        selection_body.grid_rowconfigure(0, weight=0)
        selection_body.grid_rowconfigure(1, weight=1)
        self.selection_segment = ctk.CTkSegmentedButton(
            selection_body,
            values=["角色", "專案", "聊天"],
            variable=self.selection_view_var,
            command=self._on_selection_segment_changed,
            fg_color=PALETTE["accent_soft"],
            selected_color=PALETTE["accent_blue"],
            selected_hover_color=PALETTE["accent_blue_hover"],
            unselected_color=PALETTE["panel_bg"],
            unselected_hover_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=30,
        )
        self.selection_segment.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        selection_stack = ctk.CTkFrame(selection_body, fg_color="transparent")
        selection_stack.grid(row=1, column=0, sticky="nsew")
        selection_stack.grid_columnconfigure(0, weight=1)
        selection_stack.grid_rowconfigure(0, weight=1)

        self.selection_pages: Dict[str, ctk.CTkFrame] = {}
        character_page, self.character_frame = self._build_selector_page(
            selection_stack,
            title="角色",
            subtitle=_pretty_path(self.cfg.characters_dir, self.cfg.root),
            refresh_cmd=self._refresh_character_list,
        )
        project_page, self.project_frame = self._build_selector_page(
            selection_stack,
            title="專案",
            subtitle=_pretty_path(self.cfg.projects_dir, self.cfg.root),
            refresh_cmd=self._refresh_project_list,
        )
        self.selection_pages["角色"] = character_page
        self.selection_pages["專案"] = project_page

        self.history_wrap = ctk.CTkFrame(selection_stack, fg_color="transparent")
        self.history_wrap.grid_columnconfigure(0, weight=1)
        self.history_wrap.grid_rowconfigure(2, weight=1)
        self.selection_pages["聊天"] = self.history_wrap

        history_head = ctk.CTkFrame(self.history_wrap, fg_color="transparent")
        history_head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        history_head.grid_columnconfigure(0, weight=1)
        history_title = ctk.CTkFrame(history_head, fg_color="transparent")
        history_title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            history_title,
            text="聊天紀錄",
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            history_title,
            text="選擇要延續的聊天，或建立新的對話執行緒。",
            text_color=PALETTE["muted"],
            font=ui_font(10),
        ).pack(anchor="w", pady=(1, 0))
        history_actions = ctk.CTkFrame(history_head, fg_color="transparent")
        history_actions.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            history_actions,
            text="套用",
            width=56,
            height=28,
            corner_radius=10,
            command=self.on_apply_history,
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            text_color="#ffffff",
            font=ui_font(11, "bold"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            history_actions,
            text="新增",
            width=56,
            height=28,
            corner_radius=10,
            command=self.on_new_history,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(11, "bold"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            history_actions,
            text="更新",
            width=56,
            height=28,
            corner_radius=10,
            command=self._refresh_history_list,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(11, "bold"),
        ).pack(side="left")

        self.history_status_label = ctk.CTkLabel(
            self.history_wrap,
            text="選擇要延續的聊天，或建立新的對話執行緒。",
            text_color=PALETTE["muted"],
            font=ui_font(11),
            anchor="w",
        )
        self.history_status_label.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        history_shell = ctk.CTkFrame(
            self.history_wrap,
            corner_radius=14,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        history_shell.grid(row=2, column=0, sticky="nsew")
        history_shell.grid_columnconfigure(0, weight=1)
        history_shell.grid_rowconfigure(0, weight=1)
        self.history_frame = ctk.CTkScrollableFrame(
            history_shell,
            fg_color=PALETTE["panel_bg"],
            corner_radius=14,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        self.history_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.history_frame.grid_columnconfigure(0, weight=1)

        for page in self.selection_pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self._show_selection_page()

        preview_card, preview_body = self._build_card(
            center_panel,
            row=1,
            title="預覽",
            subtitle="角色立繪與 prompt 內容集中在這裡。",
            body_fill="both",
            body_expand=True,
        )
        preview_body.grid_columnconfigure(0, weight=1)
        preview_body.grid_rowconfigure(0, weight=0)
        preview_body.grid_rowconfigure(1, weight=1)
        self.preview_segment = ctk.CTkSegmentedButton(
            preview_body,
            values=["角色預覽", "角色", "專案", "工具", "格式"],
            variable=self.preview_mode_var,
            command=self._on_preview_mode_changed,
            fg_color=PALETTE["accent_soft"],
            selected_color=PALETTE["accent_blue"],
            selected_hover_color=PALETTE["accent_blue_hover"],
            unselected_color=PALETTE["panel_bg"],
            unselected_hover_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=30,
        )
        self.preview_segment.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.preview_stage = ctk.CTkFrame(
            preview_body,
            corner_radius=16,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        self.preview_stage.grid(row=1, column=0, sticky="nsew")
        self.preview_stage.grid_columnconfigure(0, weight=1)
        self.preview_stage.grid_rowconfigure(0, weight=1)
        self.preview_image_label = TkLabel(
            self.preview_stage,
            bg=PALETTE["panel_bg"],
            bd=0,
            highlightthickness=0,
        )
        self.preview_image_label.grid(row=0, column=0, sticky="nsew")
        self.preview_empty_label = ctk.CTkLabel(
            self.preview_stage,
            text="選取角色後會在這裡顯示預覽",
            text_color=PALETTE["muted"],
            justify="center",
            wraplength=300,
            font=ui_font(12),
        )
        self.preview_empty_label.grid(row=0, column=0, sticky="nsew")

        self.prompt_box = ctk.CTkTextbox(
            preview_body,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=ui_font(12),
        )
        self.prompt_box.grid(row=1, column=0, sticky="nsew")
        self.prompt_box.configure(state="disabled")
        self._refresh_preview_panel()

        right_panel = ctk.CTkFrame(shell, fg_color="transparent")
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)

        transcript_card = ctk.CTkFrame(
            right_panel,
            corner_radius=18,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        transcript_card.grid(row=0, column=0, sticky="nsew")
        transcript_card.grid_columnconfigure(0, weight=1)
        transcript_card.grid_rowconfigure(1, weight=1)
        transcript_head = ctk.CTkFrame(transcript_card, fg_color="transparent")
        transcript_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        transcript_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            transcript_head,
            text="對話紀錄（唯讀）",
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            transcript_head,
            text="左邊是她，右邊是你；這裡只顯示，不提供輸入。",
            text_color=PALETTE["muted"],
            font=ui_font(12),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        transcript_shell = ctk.CTkFrame(
            transcript_card,
            corner_radius=14,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
        )
        transcript_shell.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        transcript_shell.grid_columnconfigure(0, weight=1)
        transcript_shell.grid_rowconfigure(0, weight=1)
        self.transcript_frame = ctk.CTkScrollableFrame(
            transcript_shell,
            fg_color=PALETTE["textbox_bg"],
            corner_radius=14,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        self.transcript_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.transcript_frame.grid_columnconfigure(0, weight=1)

        log_wrap = ctk.CTkFrame(
            shell,
            corner_radius=20,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        log_wrap.grid(row=1, column=1, columnspan=2, sticky="nsew", pady=(14, 0))
        log_wrap.grid_rowconfigure(1, weight=1)
        log_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            log_wrap,
            text="執行紀錄",
            font=ui_font(17, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        self.log_box = ctk.CTkTextbox(
            log_wrap,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=mono_font(11),
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 14))
        self.log_box.configure(state="disabled")

    def _build_ui_legacy(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        shell.grid_columnconfigure(0, weight=0, minsize=198)
        shell.grid_columnconfigure(1, weight=8)
        shell.grid_columnconfigure(2, weight=12)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=0)

        sidebar = ctk.CTkFrame(
            shell,
            width=198,
            corner_radius=22,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        sidebar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 14))
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="Kuro Launcher",
            font=ui_font(24, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(18, 4))
        ctk.CTkLabel(
            sidebar,
            text="角色與專案執行台",
            font=ui_font(12),
            text_color=PALETTE["muted"],
        ).grid(row=1, column=0, sticky="w", padx=16)

        controls = ctk.CTkFrame(sidebar, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="new", padx=16, pady=(22, 0))
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            controls,
            text="控制",
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            controls,
            text="常用啟停與檢查操作",
            font=ui_font(11),
            text_color=PALETTE["muted"],
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        self._action_button(controls, "啟動角色", self.on_start_profile, row=2, primary=True)
        self._action_button(controls, "停止角色", self.on_stop_profile, row=3)
        self._action_button(controls, "Bridge 開關", self.on_toggle_bridge, row=4)
        self._action_button(controls, "開 Web UI", self.on_open_web_ui, row=5)
        self._action_button(controls, "開 Electron", self.on_open_electron, row=6)
        self._action_button(controls, "Logs", self.on_open_logs_dir, row=7)
        self._configure_sidebar_controls(controls)

        badge_column = ctk.CTkFrame(sidebar, fg_color="transparent")
        badge_column.grid(row=4, column=0, sticky="sew", padx=16, pady=(16, 16))
        badge_column.grid_columnconfigure(0, weight=1)
        self.badges = {
            "Bridge": StatusBadge(badge_column, "Bridge"),
            "TTS": StatusBadge(badge_column, "TTS"),
            "LLM": StatusBadge(badge_column, "LLM"),
        }
        for idx, badge in enumerate(self.badges.values()):
            badge.grid(row=idx, column=0, sticky="ew", pady=(0 if idx == 0 else 8, 0))

        center_panel = ctk.CTkFrame(shell, fg_color="transparent")
        center_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
        center_panel.grid_columnconfigure(0, weight=1)
        center_panel.grid_rowconfigure(0, weight=1)

        selection_card, selection_body = self._build_card(
            center_panel,
            row=0,
            title="角色 / 專案",
            subtitle="選擇目前角色與專案，底下直接看預覽。",
            body_fill="both",
            body_expand=True,
        )
        selection_body.grid_columnconfigure(0, weight=1)
        selection_body.grid_rowconfigure(0, weight=0)
        selection_body.grid_rowconfigure(1, weight=0)
        selection_body.grid_rowconfigure(2, weight=0)
        selection_body.grid_rowconfigure(3, weight=1)

        self.character_frame = self._build_compact_selector_section(
            selection_body,
            row=0,
            title="角色",
            subtitle=_pretty_path(self.cfg.characters_dir, self.cfg.root),
            refresh_cmd=self._refresh_character_list,
            height=86,
        )
        self.project_frame = self._build_compact_selector_section(
            selection_body,
            row=1,
            title="專案",
            subtitle=_pretty_path(self.cfg.projects_dir, self.cfg.root),
            refresh_cmd=self._refresh_project_list,
            height=70,
        )

        self.preview_wrap = ctk.CTkFrame(
            selection_body,
            corner_radius=16,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        self.preview_wrap.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.preview_wrap.grid_columnconfigure(0, weight=1)
        self.preview_wrap.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            self.preview_wrap,
            text="角色預覽",
            font=ui_font(15, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        preview_stage = ctk.CTkFrame(self.preview_wrap, fg_color="transparent")
        preview_stage.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        preview_stage.grid_columnconfigure(0, weight=1)
        preview_stage.grid_rowconfigure(0, weight=1)
        self.preview_image_label = TkLabel(
            preview_stage,
            bg=PALETTE["panel_bg"],
            bd=0,
            highlightthickness=0,
        )
        self.preview_image_label.grid(row=0, column=0, sticky="nsew")
        self.preview_empty_label = ctk.CTkLabel(
            preview_stage,
            text="選取角色後會在這裡顯示預覽",
            text_color=PALETTE["muted"],
            justify="center",
            wraplength=300,
            font=ui_font(12),
        )
        self.preview_empty_label.grid(row=0, column=0, sticky="nsew")

        self.history_wrap = ctk.CTkFrame(
            selection_body,
            corner_radius=16,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        self.history_wrap.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        self.history_wrap.grid_columnconfigure(0, weight=1)
        self.history_wrap.grid_rowconfigure(2, weight=1)

        history_head = ctk.CTkFrame(self.history_wrap, fg_color="transparent")
        history_head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        history_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            history_head,
            text="聊天記錄",
            font=ui_font(15, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w")
        history_actions = ctk.CTkFrame(history_head, fg_color="transparent")
        history_actions.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            history_actions,
            text="套用",
            width=56,
            height=28,
            corner_radius=10,
            command=self.on_apply_history,
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            text_color="#ffffff",
            font=ui_font(11, "bold"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            history_actions,
            text="新增",
            width=56,
            height=28,
            corner_radius=10,
            command=self.on_new_history,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(11, "bold"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            history_actions,
            text="更新",
            width=56,
            height=28,
            corner_radius=10,
            command=self._refresh_history_list,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(11, "bold"),
        ).pack(side="left")

        self.history_status_label = ctk.CTkLabel(
            self.history_wrap,
            text="選擇要延續的聊天，或建立新的對話執行緒。",
            text_color=PALETTE["muted"],
            font=ui_font(11),
            anchor="w",
        )
        self.history_status_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        history_shell = ctk.CTkFrame(
            self.history_wrap,
            corner_radius=14,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        history_shell.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        history_shell.grid_columnconfigure(0, weight=1)
        history_shell.grid_rowconfigure(0, weight=1)

        self.history_frame = ctk.CTkScrollableFrame(
            history_shell,
            fg_color=PALETTE["panel_bg"],
            corner_radius=14,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        self.history_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.history_frame.grid_columnconfigure(0, weight=1)

        right_panel = ctk.CTkFrame(shell, fg_color="transparent")
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=7)
        right_panel.grid_rowconfigure(1, weight=5)
        right_panel.grid_rowconfigure(2, weight=0)

        transcript_card = ctk.CTkFrame(
            right_panel,
            corner_radius=18,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        transcript_card.grid(row=0, column=0, sticky="nsew")
        transcript_card.grid_columnconfigure(0, weight=1)
        transcript_card.grid_rowconfigure(1, weight=1)

        transcript_head = ctk.CTkFrame(transcript_card, fg_color="transparent")
        transcript_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        transcript_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            transcript_head,
            text="對話紀錄（唯讀）",
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            transcript_head,
            text="左邊是她，右邊是你；這裡只顯示，不提供輸入。",
            text_color=PALETTE["muted"],
            font=ui_font(12),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        transcript_shell = ctk.CTkFrame(
            transcript_card,
            corner_radius=14,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
        )
        transcript_shell.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        transcript_shell.grid_columnconfigure(0, weight=1)
        transcript_shell.grid_rowconfigure(0, weight=1)

        self.transcript_frame = ctk.CTkScrollableFrame(
            transcript_shell,
            fg_color=PALETTE["textbox_bg"],
            corner_radius=14,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        self.transcript_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.transcript_frame.grid_columnconfigure(0, weight=1)

        prompt_card = ctk.CTkFrame(
            right_panel,
            corner_radius=18,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        prompt_card.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        prompt_card.grid_columnconfigure(0, weight=1)
        prompt_card.grid_rowconfigure(1, weight=1)

        prompt_head = ctk.CTkFrame(prompt_card, fg_color="transparent")
        prompt_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        prompt_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            prompt_head,
            text="Prompt 預覽",
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w")
        self.prompt_segment = ctk.CTkSegmentedButton(
            prompt_head,
            values=["角色", "專案", "工具", "格式"],
            variable=self.prompt_view_var,
            command=self._on_prompt_segment_changed,
            fg_color=PALETTE["accent_soft"],
            selected_color=PALETTE["accent_blue"],
            selected_hover_color=PALETTE["accent_blue_hover"],
            unselected_color=PALETTE["panel_bg"],
            unselected_hover_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=30,
        )
        self.prompt_segment.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            prompt_head,
            text="人格、專案與工具提示詞可直接比對。",
            text_color=PALETTE["muted"],
            font=ui_font(12),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.prompt_box = ctk.CTkTextbox(
            prompt_card,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=ui_font(12),
        )
        self.prompt_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.prompt_box.configure(state="disabled")

        pet_card = ctk.CTkFrame(
            right_panel,
            corner_radius=18,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        pet_card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        pet_card.grid_columnconfigure(0, weight=1)
        pet_card.grid_columnconfigure(1, weight=1)

        pet_head = ctk.CTkFrame(pet_card, fg_color="transparent")
        pet_head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 8))
        pet_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            pet_head,
            text="桌寵控制",
            font=ui_font(17, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w")
        self.pet_status_label = ctk.CTkLabel(
            pet_head,
            text="桌寵 shell 尚未連線。",
            font=ui_font(12),
            text_color=PALETTE["muted"],
            anchor="e",
        )
        self.pet_status_label.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            pet_card,
            text="Base URL",
            font=ui_font(12, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=1, column=0, sticky="w", padx=14)
        ctk.CTkLabel(
            pet_card,
            text="WebSocket URL",
            font=ui_font(12, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=1, column=1, sticky="w", padx=(8, 14))

        self.pet_base_url_entry = ctk.CTkEntry(
            pet_card,
            textvariable=self.pet_base_url_var,
            fg_color=PALETTE["textbox_bg"],
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=ui_font(12),
        )
        self.pet_base_url_entry.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 10))
        self.pet_ws_url_entry = ctk.CTkEntry(
            pet_card,
            textvariable=self.pet_ws_url_var,
            fg_color=PALETTE["textbox_bg"],
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=ui_font(12),
        )
        self.pet_ws_url_entry.grid(row=2, column=1, sticky="ew", padx=(8, 14), pady=(4, 10))

        pet_button_bar = ctk.CTkFrame(pet_card, fg_color="transparent")
        pet_button_bar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        for idx in range(4):
            pet_button_bar.grid_columnconfigure(idx, weight=1)

        ctk.CTkButton(
            pet_button_bar,
            text="套用端點",
            command=self.on_pet_apply_backend_urls,
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            text_color="#ffffff",
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        ctk.CTkButton(
            pet_button_bar,
            text="刷新狀態",
            command=self.on_pet_refresh_status,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 6))
        ctk.CTkButton(
            pet_button_bar,
            text="麥克風",
            command=self.on_pet_toggle_mic,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=0, column=2, sticky="ew", padx=6, pady=(0, 6))
        ctk.CTkButton(
            pet_button_bar,
            text="打斷",
            command=self.on_pet_interrupt,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=(0, 6))
        ctk.CTkButton(
            pet_button_bar,
            text="攝影機",
            command=self.on_pet_toggle_camera,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            pet_button_bar,
            text="螢幕",
            command=self.on_pet_toggle_screen,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=1, column=1, sticky="ew", padx=6)
        ctk.CTkButton(
            pet_button_bar,
            text="瀏覽器",
            command=self.on_pet_toggle_browser,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=1, column=2, sticky="ew", padx=6)
        ctk.CTkButton(
            pet_button_bar,
            text="字幕框",
            command=self.on_pet_toggle_subtitle,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["accent_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            height=32,
        ).grid(row=1, column=3, sticky="ew", padx=(6, 0))

        self._configure_pet_control_bar(pet_button_bar)

        log_wrap = ctk.CTkFrame(
            shell,
            corner_radius=20,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
            height=148,
        )
        log_wrap.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(14, 0))
        log_wrap.grid_rowconfigure(1, weight=1)
        log_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            log_wrap,
            text="執行紀錄",
            font=ui_font(17, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        self.log_box = ctk.CTkTextbox(
            log_wrap,
            height=112,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=mono_font(11),
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 14))
        self.log_box.configure(state="disabled")

    def _build_selector_panel(
        self,
        parent,
        *,
        row: int,
        column: int,
        title: str,
        subtitle: str,
        refresh_cmd,
    ) -> ctk.CTkScrollableFrame:
        card = ctk.CTkFrame(
            parent,
            corner_radius=20,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        card.grid(row=row, column=column, sticky="nsew", pady=(0 if row == 0 else 12, 0))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        text_block = ctk.CTkFrame(header, fg_color="transparent")
        text_block.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            text_block,
            text=title,
            font=ui_font(20, "bold"),
            text_color=PALETTE["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_block,
            text=subtitle,
            text_color=PALETTE["muted"],
            font=ui_font(12),
        ).pack(anchor="w", pady=(4, 0))
        ctk.CTkButton(
            header,
            text="重新整理",
            width=88,
            height=32,
            corner_radius=10,
            command=refresh_cmd,
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            text_color="#ffffff",
            font=ui_font(12, "bold"),
        ).grid(row=0, column=1, sticky="e")

        scroll = ctk.CTkScrollableFrame(
            card,
            fg_color=PALETTE["panel_soft"],
            corner_radius=16,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        scroll.grid_columnconfigure(0, weight=1)
        return scroll

    def _build_compact_selector_section(
        self,
        parent,
        *,
        row: int,
        title: str,
        subtitle: str,
        refresh_cmd,
        height: int,
    ) -> ctk.CTkScrollableFrame:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 10, 0))
        section.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            section,
            corner_radius=16,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(0, weight=1)
        label_box = ctk.CTkFrame(header, fg_color="transparent")
        label_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            label_box,
            text=title,
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            label_box,
            text=subtitle,
            text_color=PALETTE["muted"],
            font=ui_font(10),
        ).pack(anchor="w", pady=(1, 0))
        ctk.CTkButton(
            header,
            text="更新",
            width=72,
            height=28,
            corner_radius=10,
            command=refresh_cmd,
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            text_color="#ffffff",
            font=ui_font(11, "bold"),
        ).grid(row=0, column=1, sticky="e")

        shell = ctk.CTkFrame(
            card,
            height=height,
            corner_radius=14,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        shell.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        shell.grid_propagate(False)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            shell,
            fg_color=PALETTE["panel_bg"],
            corner_radius=14,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll.grid_columnconfigure(0, weight=1)
        return scroll

    def _build_selector_page(
        self,
        parent,
        *,
        title: str,
        subtitle: str,
        refresh_cmd,
    ) -> tuple[ctk.CTkFrame, ctk.CTkScrollableFrame]:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        label_box = ctk.CTkFrame(header, fg_color="transparent")
        label_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            label_box,
            text=title,
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            label_box,
            text=subtitle,
            text_color=PALETTE["muted"],
            font=ui_font(10),
        ).pack(anchor="w", pady=(1, 0))
        ctk.CTkButton(
            header,
            text="更新",
            width=72,
            height=28,
            corner_radius=10,
            command=refresh_cmd,
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            text_color="#ffffff",
            font=ui_font(11, "bold"),
        ).grid(row=0, column=1, sticky="e")

        shell = ctk.CTkFrame(
            page,
            corner_radius=14,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        shell.grid(row=1, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            shell,
            fg_color=PALETTE["panel_bg"],
            corner_radius=14,
            scrollbar_button_color=PALETTE["accent_soft"],
            scrollbar_button_hover_color=PALETTE["accent_blue"],
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll.grid_columnconfigure(0, weight=1)
        return page, scroll

    def _show_selection_page(self) -> None:
        selected = self.selection_view_var.get() or "角色"
        pages = getattr(self, "selection_pages", {})
        for name, page in pages.items():
            if not page.winfo_manager():
                page.grid(row=0, column=0, sticky="nsew")
            if name == selected:
                page.tkraise()

    def _on_selection_segment_changed(self, _value: str) -> None:
        self._show_selection_page()

    def _refresh_preview_panel(self) -> None:
        mode = self.preview_mode_var.get() or "角色預覽"
        if hasattr(self, "preview_stage") and not self.preview_stage.winfo_manager():
            self.preview_stage.grid(row=1, column=0, sticky="nsew")
        if hasattr(self, "prompt_box") and not self.prompt_box.winfo_manager():
            self.prompt_box.grid(row=1, column=0, sticky="nsew")

        if mode == "角色預覽":
            if hasattr(self, "preview_stage"):
                self.preview_stage.tkraise()
            return

        if hasattr(self, "prompt_box"):
            self.prompt_box.tkraise()
        self.prompt_view_var.set(mode)
        self._refresh_prompt_view()

    def _on_preview_mode_changed(self, _value: str) -> None:
        self._refresh_preview_panel()

    def _build_card(self, parent, *, row: int, title: str, subtitle: str, body_fill="x", body_expand=False):
        card = ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        card.grid(row=row, column=0, sticky="nsew", padx=14, pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        if body_expand:
            card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head,
            text=title,
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head,
            text=subtitle,
            text_color=PALETTE["muted"],
            font=ui_font(12),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        if body_expand:
            body.grid_rowconfigure(0, weight=1)
            body.grid_columnconfigure(0, weight=1)
        return card, body

    def _build_card_textbox(self, parent, *, row: int, title: str, subtitle: str, height: int) -> ctk.CTkTextbox:
        card, body = self._build_card(parent, row=row, title=title, subtitle=subtitle)
        box = ctk.CTkTextbox(
            body,
            height=height,
            fg_color=PALETTE["textbox_bg"],
            border_width=1,
            border_color=PALETTE["textbox_border"],
            text_color=PALETTE["text"],
            font=ui_font(12),
        )
        box.pack(fill="both", expand=True)
        box.configure(state="disabled")
        return box

    def _action_button(self, parent, text: str, command, *, row: int, primary: bool = False) -> None:
        button = ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=40,
            corner_radius=12,
            fg_color=PALETTE["accent_pink"] if primary else PALETTE["panel_bg"],
            hover_color=PALETTE["accent_pink_hover"] if primary else PALETTE["panel_alt"],
            border_width=0 if primary else 1,
            border_color=PALETTE["panel_border"],
            text_color="#ffffff" if primary else PALETTE["text"],
            font=ui_font(12, "bold" if primary else "normal"),
        )
        button.grid(row=row, column=0, sticky="ew", pady=(0, 8))

    def _configure_sidebar_controls(self, controls: ctk.CTkFrame) -> None:
        for widget in controls.grid_slaves(row=0, column=0):
            try:
                widget.configure(text="控制")
            except Exception:
                pass
        for widget in controls.grid_slaves(row=1, column=0):
            try:
                widget.configure(text="常用啟停與檢查操作")
            except Exception:
                pass

        labels_by_row = {
            2: "啟動角色",
            3: "停止角色",
            6: "開 Electron",
            7: "Logs",
        }
        for row, label in labels_by_row.items():
            for widget in controls.grid_slaves(row=row, column=0):
                try:
                    widget.configure(text=label)
                except Exception:
                    pass

        for row in (4, 5):
            for widget in controls.grid_slaves(row=row, column=0):
                widget.grid_remove()

        for source_row, target_row in ((6, 4), (7, 5)):
            for widget in controls.grid_slaves(row=source_row, column=0):
                widget.grid_configure(row=target_row)

    def _pet_control_button(
        self,
        parent,
        text: str,
        command,
        *,
        row: int,
        column: int,
        primary: bool = False,
        padx=(0, 6),
        pady=(0, 8),
    ) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=PALETTE["accent_blue"] if primary else PALETTE["panel_bg"],
            hover_color=PALETTE["accent_blue_hover"] if primary else PALETTE["panel_alt"],
            border_width=0 if primary else 1,
            border_color=PALETTE["panel_border"],
            text_color="#ffffff" if primary else PALETTE["text"],
            font=ui_font(12, "bold"),
            height=34,
            corner_radius=12,
        ).grid(row=row, column=column, sticky="ew", padx=padx, pady=pady)

    def _pet_toggle_switch(
        self,
        parent,
        label: str,
        action: str,
        *,
        row: int,
        column: int,
        padx=(0, 6),
        pady=(0, 8),
    ) -> None:
        var = self.pet_toggle_vars.get(action)
        if var is None:
            var = ctk.StringVar(value="off")
            self.pet_toggle_vars[action] = var

        shell = ctk.CTkFrame(
            parent,
            corner_radius=14,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        shell.grid(row=row, column=column, sticky="ew", padx=padx, pady=pady)
        shell.grid_columnconfigure(0, weight=1)

        state_label = ctk.CTkLabel(
            shell,
            text="ON" if var.get() == "on" else "OFF",
            width=34,
            font=ui_font(11, "bold"),
            text_color=PALETTE["success"] if var.get() == "on" else PALETTE["muted"],
        )
        state_label.grid(row=0, column=1, padx=(4, 10), pady=8)

        def on_change() -> None:
            enabled = var.get() == "on"
            state_label.configure(
                text="ON" if enabled else "OFF",
                text_color=PALETTE["success"] if enabled else PALETTE["muted"],
            )
            mode = "啟用" if enabled else "停止"
            self._run_pet_command(
                action,
                payload={"enabled": enabled},
                success_log=f"{label} 已切換為 {mode}。",
            )

        ctk.CTkSwitch(
            shell,
            text=label,
            variable=var,
            onvalue="on",
            offvalue="off",
            command=on_change,
            progress_color=PALETTE["success"],
            fg_color="#d8dee8",
            button_color=PALETTE["panel_bg"],
            button_hover_color=PALETTE["accent_soft"],
            text_color=PALETTE["text"],
            font=ui_font(12, "bold"),
            switch_width=48,
            switch_height=24,
        ).grid(row=0, column=0, sticky="w", padx=(12, 4), pady=8)

    def _configure_pet_control_bar(self, pet_button_bar: ctk.CTkFrame) -> None:
        for widget in pet_button_bar.winfo_children():
            widget.destroy()
        pet_button_bar.grid_columnconfigure(0, weight=1)

        self._pet_control_button(
            pet_button_bar,
            "停止輸出",
            self.on_pet_interrupt,
            row=0,
            column=0,
            primary=True,
            padx=(0, 0),
        )

        self._pet_toggle_switch(
            pet_button_bar,
            "麥克風",
            "mic-toggle",
            row=1,
            column=0,
            padx=(0, 0),
        )
        self._pet_toggle_switch(
            pet_button_bar,
            "攝影機",
            "toggle-camera",
            row=2,
            column=0,
            padx=(0, 0),
        )
        self._pet_toggle_switch(
            pet_button_bar,
            "螢幕",
            "toggle-screen",
            row=3,
            column=0,
            padx=(0, 0),
        )
        self._pet_toggle_switch(
            pet_button_bar,
            "對話框",
            "set-reader-visible",
            row=4,
            column=0,
            padx=(0, 0),
        )

    def log(self, message: str) -> None:
        try:
            self._log_q.put_nowait(strip_ansi_and_ctrl(str(message)))
        except Exception:
            return
        if threading.get_ident() == self._main_thread_id:
            try:
                self.after_idle(self._drain_log_queue)
            except Exception:
                pass

    def _set_textbox(self, box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("1.0", text)
        box.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        drained = 0
        self.log_box.configure(state="normal")
        while drained < 250:
            try:
                line = self._log_q.get_nowait()
            except Exception:
                break
            self.log_box.insert("end", line + "\n")
            self.log_box.see("end")
            drained += 1
        self.log_box.configure(state="disabled")
        self.after(120, self._drain_log_queue)

    def _tick_status(self) -> None:
        bridge_ok = port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.1)
        tts_ok = port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.1)
        llm_ok = port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.1)
        self.badges["Bridge"].set_status(bridge_ok)
        self.badges["TTS"].set_status(tts_ok)
        self.badges["LLM"].set_status(llm_ok)
        self._refresh_history_transcript()
        self._tick_pet_shell_status()
        self.after(800, self._tick_status)

    def _load_live2d_catalog(self) -> Dict[str, dict]:
        model_dict_path = self.cfg.open_llm_dir / "model_dict.json"
        if not model_dict_path.exists():
            return {}
        try:
            payload = json.loads(model_dict_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        mapping: Dict[str, dict] = {}
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("name"):
                    mapping[str(item["name"])] = item
        return mapping

    def _find_avatar_preview(self, character: CharacterRecord) -> Optional[Path]:
        avatars_dir = self.cfg.open_llm_dir / "avatars"
        if not avatars_dir.exists():
            return None

        exact_names = [
            character.conf_name,
            character.live2d_model_name,
        ]
        for stem in exact_names:
            stem = (stem or "").strip()
            if not stem:
                continue
            for suffix in IMAGE_EXTENSIONS:
                candidate = avatars_dir / f"{stem}{suffix}"
                if candidate.exists():
                    return candidate

        targets = {_normalize_token(character.conf_name), _normalize_token(character.live2d_model_name)}
        for path in sorted(avatars_dir.iterdir()):
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            stem_norm = _normalize_token(path.stem)
            if not stem_norm:
                continue
            for target in targets:
                if target and (
                    stem_norm == target
                    or stem_norm.startswith(target)
                    or target.startswith(stem_norm)
                ):
                    return path
        return None

    def _find_live2d_preview(self, character: CharacterRecord) -> Optional[Path]:
        model_root = self.cfg.open_llm_dir / "live2d-models" / character.live2d_model_name
        if not model_root.exists():
            return None

        preview_names = ("preview", "thumbnail", "poster", "cover")
        files = sorted(p for p in model_root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
        for path in files:
            stem = path.stem.lower()
            if any(name in stem for name in preview_names):
                return path
        for path in files:
            if "texture" not in path.stem.lower():
                return path
        return files[0] if files else None

    def _resolve_preview_asset(self, character: CharacterRecord) -> tuple[Optional[Path], str]:
        avatar = self._find_avatar_preview(character)
        if avatar:
            return avatar, "角色圖預覽"
        live2d = self._find_live2d_preview(character)
        if live2d:
            return live2d, "Live2D 素材預覽"
        return None, "尚未找到可用預覽"

    def _load_preview_photo(self, image_path: Path, max_width: int = 420, max_height: int = 292) -> Optional[PhotoImage]:
        try:
            photo = PhotoImage(file=str(image_path))
        except Exception:
            return None
        scale_x = max(1, math.ceil(photo.width() / max_width))
        scale_y = max(1, math.ceil(photo.height() / max_height))
        scale = max(scale_x, scale_y)
        if scale > 1:
            photo = photo.subsample(scale, scale)
        return photo

    def _update_character_preview(self, character: Optional[CharacterRecord]) -> None:
        if not character:
            self._preview_photo = None
            self.preview_image_label.configure(image="")
            self.preview_image_label.grid_remove()
            self.preview_empty_label.configure(text="選取角色後會在這裡顯示預覽")
            self.preview_empty_label.grid()
            return

        preview_path, _preview_kind = self._resolve_preview_asset(character)
        if preview_path:
            self._preview_photo = self._load_preview_photo(preview_path)
        else:
            self._preview_photo = None

        if self._preview_photo:
            self.preview_empty_label.grid_remove()
            self.preview_image_label.configure(image=self._preview_photo)
            self.preview_image_label.grid()
        else:
            self.preview_image_label.configure(image="")
            self.preview_image_label.grid_remove()
            self.preview_empty_label.configure(text="這個角色目前沒有可直接顯示的預覽圖")
            self.preview_empty_label.grid()

    def _history_dir_for_character(
        self, character: Optional[CharacterRecord]
    ) -> Optional[Path]:
        if not character or not character.conf_uid.strip():
            return None
        return self.cfg.open_llm_dir / "chat_history" / character.conf_uid.strip()

    def _history_file_for_character(
        self, character: Optional[CharacterRecord], history_uid: str
    ) -> Optional[Path]:
        history_dir = self._history_dir_for_character(character)
        history_uid = (history_uid or "").strip()
        if history_dir is None or not history_uid:
            return None
        return history_dir / f"{history_uid}.json"

    def _normalize_history_message_content(self, content) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
            return "\n".join(part.strip() for part in parts if part and part.strip())
        if content is None:
            return ""
        return str(content).strip()

    def _load_history_messages(
        self, character: Optional[CharacterRecord], history_uid: str
    ) -> list[dict]:
        history_path = self._history_file_for_character(character, history_uid)
        if history_path is None or not history_path.exists():
            return []

        try:
            payload = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not isinstance(payload, list):
            return []

        messages: list[dict] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role == "metadata":
                continue
            content = self._normalize_history_message_content(item.get("content"))
            timestamp = str(item.get("timestamp") or "").strip()
            messages.append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                }
            )
        return messages

    def _load_history_records(
        self, character: Optional[CharacterRecord]
    ) -> Dict[str, HistoryRecord]:
        history_dir = self._history_dir_for_character(character)
        if history_dir is None or not history_dir.exists():
            return {}

        items: list[HistoryRecord] = []
        for path in sorted(history_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            if not isinstance(payload, list):
                continue

            metadata = {}
            if payload and isinstance(payload[0], dict) and payload[0].get("role") == "metadata":
                metadata = payload[0]

            messages = [
                msg
                for msg in payload
                if isinstance(msg, dict) and msg.get("role") != "metadata"
            ]
            latest = messages[-1] if messages else None
            first_human = next(
                (
                    msg
                    for msg in messages
                    if msg.get("role") == "human" and isinstance(msg.get("content"), str)
                ),
                None,
            )

            title = str(metadata.get("title") or "").strip()
            if not title:
                seed = ""
                if first_human:
                    seed = str(first_human.get("content") or "")
                elif latest:
                    seed = str(latest.get("content") or "")
                title = _derive_history_title(seed) or "新對話"

            preview = str(metadata.get("last_preview") or "").strip()
            if not preview:
                preview = str(metadata.get("summary_short") or "").strip()
            if not preview and latest:
                preview = _compact_history_text(str(latest.get("content") or ""), 88)

            timestamp = (
                str(metadata.get("updated_at") or "").strip()
                or (str(latest.get("timestamp") or "").strip() if latest else "")
                or str(metadata.get("timestamp") or "").strip()
            )
            items.append(
                HistoryRecord(
                    uid=path.stem,
                    title=title,
                    preview=preview,
                    timestamp=timestamp,
                    is_empty=len(messages) == 0,
                )
            )

        items.sort(key=lambda item: item.timestamp, reverse=True)
        return {item.uid: item for item in items}

    def _selected_history_record(self) -> Optional[HistoryRecord]:
        return self.history_records.get(self.history_var.get().strip())

    def _sync_history_status_label(self) -> None:
        if self._force_new_history_on_start:
            status = "目前設定：下次啟動或套用時建立新的聊天。"
        else:
            record = self._selected_history_record()
            if record:
                preview = f" / {record.preview}" if record.preview else ""
                status = f"目前選擇：{record.title}{preview}"
            elif self.history_records:
                status = "已載入聊天列表，選擇一段對話後可直接套用。"
            else:
                status = "這個角色目前還沒有聊天記錄。"
        self.history_status_label.configure(text=status)

    def _history_transcript_signature_for_current(self) -> str:
        character = self._selected_character()
        if character is None:
            return "no-character"
        if self._force_new_history_on_start:
            return f"new:{character.conf_uid}"

        history_uid = self.history_var.get().strip()
        if not history_uid:
            return f"empty:{character.conf_uid}"

        history_path = self._history_file_for_character(character, history_uid)
        if history_path is None:
            return f"missing:{character.conf_uid}:{history_uid}"
        try:
            stat = history_path.stat()
        except OSError:
            return f"missing:{character.conf_uid}:{history_uid}"
        return f"{character.conf_uid}:{history_uid}:{stat.st_mtime_ns}:{stat.st_size}"

    def _clear_history_transcript(self, placeholder: str) -> None:
        for child in self.transcript_frame.winfo_children():
            child.destroy()
        empty = ctk.CTkLabel(
            self.transcript_frame,
            text=placeholder,
            text_color=PALETTE["muted"],
            justify="left",
            anchor="w",
            wraplength=420,
            font=ui_font(12),
        )
        empty.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 12))

    def _append_history_bubble(
        self,
        *,
        row: int,
        speaker: str,
        content: str,
        timestamp: str,
        is_user: bool,
    ) -> None:
        lane = ctk.CTkFrame(self.transcript_frame, fg_color="transparent")
        lane.grid(row=row, column=0, sticky="ew", padx=10, pady=(10 if row == 0 else 2, 6))
        lane.grid_columnconfigure(0, weight=1)
        lane.grid_columnconfigure(1, weight=1)

        bubble = ctk.CTkFrame(
            lane,
            corner_radius=14,
            fg_color=PALETTE["accent_soft"] if is_user else PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        bubble.grid(
            row=0,
            column=1 if is_user else 0,
            sticky="e" if is_user else "w",
            padx=(40, 0) if is_user else (0, 40),
        )

        ctk.CTkLabel(
            bubble,
            text=speaker,
            font=ui_font(11, "bold"),
            text_color=PALETTE["muted"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            bubble,
            text=content or "(空白訊息)",
            font=ui_font(12),
            text_color=PALETTE["text"],
            justify="left",
            anchor="w",
            wraplength=380,
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))

        if timestamp:
            ctk.CTkLabel(
                bubble,
                text=_format_history_timestamp(timestamp),
                font=ui_font(10),
                text_color=PALETTE["muted"],
                anchor="e" if is_user else "w",
            ).grid(row=2, column=0, sticky="e" if is_user else "w", padx=12, pady=(0, 10))
        else:
            bubble.grid_rowconfigure(2, minsize=8)

    def _refresh_history_transcript(self, *, force: bool = False) -> None:
        if not hasattr(self, "transcript_frame"):
            return

        signature = self._history_transcript_signature_for_current()
        if not force and signature == self._transcript_signature:
            return
        self._transcript_signature = signature

        character = self._selected_character()
        if character is None:
            self._clear_history_transcript("請先選擇角色，這裡才會顯示完整對話。")
            return
        if self._force_new_history_on_start:
            self._clear_history_transcript("新的聊天會在啟動或套用後建立，這裡會顯示新的對話內容。")
            return

        history_uid = self.history_var.get().strip()
        if not history_uid:
            if self.history_records:
                self._clear_history_transcript("請先從聊天列表選一段對話。")
            else:
                self._clear_history_transcript("這個角色目前還沒有聊天內容。")
            return

        messages = self._load_history_messages(character, history_uid)
        if not messages:
            self._clear_history_transcript("這段聊天目前還沒有訊息。")
            return

        for child in self.transcript_frame.winfo_children():
            child.destroy()

        assistant_name = character.conf_name or "她"
        for row, message in enumerate(messages):
            role = str(message.get("role") or "").strip().lower()
            is_user = role in {"human", "user"}
            self._append_history_bubble(
                row=row,
                speaker="你" if is_user else assistant_name,
                content=str(message.get("content") or ""),
                timestamp=str(message.get("timestamp") or ""),
                is_user=is_user,
            )

        try:
            self.transcript_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _on_history_selected(self) -> None:
        self._force_new_history_on_start = False
        self._sync_history_status_label()
        self._refresh_history_transcript(force=True)

    def _after_history_created(self, new_uid: str) -> None:
        self._force_new_history_on_start = False
        if new_uid:
            self.history_var.set(new_uid)
        self._refresh_history_list()

    def _after_history_selected(self) -> None:
        self._force_new_history_on_start = False
        self._sync_history_status_label()
        self._refresh_history_transcript(force=True)

    def _refresh_history_list(self) -> None:
        for child in self.history_frame.winfo_children():
            child.destroy()
        self._history_radio_buttons = []

        character = self._selected_character()
        self.history_records = self._load_history_records(character)
        current = self.history_var.get().strip()

        if self.history_records:
            if self._force_new_history_on_start:
                self.history_var.set("")
            elif current not in self.history_records:
                self.history_var.set(next(iter(self.history_records)))
        else:
            self.history_var.set("")

        if not self.history_records:
            empty = ctk.CTkLabel(
                self.history_frame,
                text="還沒有可接續的聊天，建立新對話後會出現在這裡。",
                text_color=PALETTE["muted"],
                justify="left",
                anchor="w",
                wraplength=300,
                font=ui_font(12),
            )
            empty.grid(sticky="ew", padx=12, pady=(12, 12))
        else:
            for uid, record in self.history_records.items():
                stamp = _format_history_timestamp(record.timestamp)
                label = record.title
                if stamp:
                    label = f"{label}  ·  {stamp}"
                radio = ctk.CTkRadioButton(
                    self.history_frame,
                    text=label,
                    variable=self.history_var,
                    value=uid,
                    command=self._on_history_selected,
                    height=28,
                    radiobutton_width=18,
                    radiobutton_height=18,
                    font=ui_font(12, "bold"),
                    text_color=PALETTE["text"],
                    border_color=PALETTE["panel_border"],
                    hover_color=PALETTE["accent_blue"],
                    fg_color=PALETTE["accent_lavender"],
                )
                radio.grid(sticky="ew", padx=12, pady=(10, 0))
                self._history_radio_buttons.append(radio)

        self._sync_history_status_label()
        self._refresh_history_transcript(force=True)

    def _refresh_character_list(self) -> None:
        self.character_records.clear()
        for button in self._character_radio_buttons:
            button.destroy()
        self._character_radio_buttons.clear()

        yaml_files = sorted(self.cfg.characters_dir.glob("*.yaml"))
        for path in yaml_files:
            data = read_yaml_file(path)
            cc = data.get("character_config") or {}
            record = CharacterRecord(
                yaml_path=path,
                conf_name=str(cc.get("conf_name") or path.stem),
                conf_uid=str(cc.get("conf_uid") or ""),
                live2d_model_name=str(cc.get("live2d_model_name") or ""),
                avatar=str(cc.get("avatar") or ""),
                persona_prompt_path=str(cc.get("persona_prompt_path") or ""),
                default_project_id=str(cc.get("default_project_id") or ""),
            )
            key = str(path)
            self.character_records[key] = record
            radio = ctk.CTkRadioButton(
                self.character_frame,
                text=f"{record.conf_name}  ·  {path.name}",
                variable=self.character_var,
                value=key,
                command=self._on_character_changed,
                height=28,
                radiobutton_width=18,
                radiobutton_height=18,
                font=ui_font(13, "bold"),
                text_color=PALETTE["text"],
                border_color=PALETTE["panel_border"],
                hover_color=PALETTE["accent_blue"],
                fg_color=PALETTE["accent_lavender"],
            )
            radio.grid(sticky="ew", padx=12, pady=(10, 0))
            self._character_radio_buttons.append(radio)

        if self.character_records:
            current = self.character_var.get()
            if current not in self.character_records:
                self.character_var.set(next(iter(self.character_records)))
            self._on_character_changed()
        else:
            self.character_var.set("")
            self.history_records.clear()
            self._refresh_history_list()
            self._update_panels()
        self.log(f"[{log_ts()}] 角色列表已更新，共 {len(self.character_records)} 份設定。")

    def _refresh_project_list(self) -> None:
        self.project_records.clear()
        for button in self._project_radio_buttons:
            button.destroy()
        self._project_radio_buttons.clear()

        projects = list_project_definitions(self.cfg.projects_dir)
        for project in projects:
            key = str(project.path)
            self.project_records[key] = project
            radio = ctk.CTkRadioButton(
                self.project_frame,
                text=f"{project.display_name}  ·  {project.project_id}",
                variable=self.project_var,
                value=key,
                command=self._on_project_changed,
                height=28,
                radiobutton_width=18,
                radiobutton_height=18,
                font=ui_font(13, "bold"),
                text_color=PALETTE["text"],
                border_color=PALETTE["panel_border"],
                hover_color=PALETTE["accent_blue"],
                fg_color=PALETTE["accent_lavender"],
            )
            radio.grid(sticky="ew", padx=12, pady=(10, 0))
            self._project_radio_buttons.append(radio)

        if self.project_records:
            current = self.project_var.get()
            if current not in self.project_records:
                self.project_var.set(next(iter(self.project_records)))
        else:
            self.project_var.set("")
        self._apply_character_default_project()
        self._update_panels()
        self.log(f"[{log_ts()}] 專案列表已更新，共 {len(self.project_records)} 份設定。")

    def _selected_character(self) -> Optional[CharacterRecord]:
        return self.character_records.get(self.character_var.get())

    def _selected_project(self) -> Optional[ProjectDefinition]:
        return self.project_records.get(self.project_var.get())

    def _apply_character_default_project(self) -> None:
        character = self._selected_character()
        if not character or not self.project_records:
            return
        current = self.project_var.get()
        if current in self.project_records:
            return
        if character.default_project_id:
            for key, project in self.project_records.items():
                if project.project_id == character.default_project_id:
                    self.project_var.set(key)
                    return
        self.project_var.set(next(iter(self.project_records)))

    def _on_character_changed(self) -> None:
        self._apply_character_default_project()
        self._force_new_history_on_start = False
        self._refresh_history_list()
        self._update_panels()

    def _on_project_changed(self) -> None:
        self._update_panels()

    def _on_prompt_segment_changed(self, _value: str) -> None:
        self._refresh_prompt_view()

    def _refresh_prompt_view(self) -> None:
        key_map = {
            "角色": "persona",
            "專案": "project",
            "工具": "tool",
            "格式": "contract",
        }
        selected_key = key_map.get(self.prompt_view_var.get(), "persona")
        self._set_textbox(self.prompt_box, self._prompt_texts.get(selected_key, ""))

    def _update_panels(self) -> None:
        character = self._selected_character()
        project = self._selected_project()
        self._update_character_preview(character)

        persona_text = ""
        project_text = ""
        tool_text = ""
        contract_text = _read_text_maybe(
            self.cfg.open_llm_dir / "prompts" / "utils" / "response_contract_prompt.txt"
        )

        if character:
            persona_text = _read_text_maybe(
                _resolve_repo_path(self.cfg.open_llm_dir, character.persona_prompt_path)
            )
        if project:
            project_text = _read_text_maybe(project.project_prompt_path)
            tool_text = _read_text_maybe(project.tool_prompt_path)

        self._prompt_texts = {
            "persona": persona_text,
            "project": project_text,
            "tool": tool_text,
            "contract": contract_text,
        }
        self._refresh_prompt_view()

    def _ensure_bridge_on_start(self) -> None:
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            self.log(f"[{log_ts()}] 注意：目前環境裡沒有 OPENAI_API_KEY。")

        try:
            proc = start_bridge(
                self.cfg,
                self.log,
                logs_root=self.cfg.logs_dir,
                run_id=None,
            )
            if proc is not None:
                self.proc_bridge = proc
        except Exception as exc:
            self.log(f"[{log_ts()}] Bridge 啟動失敗：{exc}")
            return

        for _ in range(40):
            if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.2):
                break
            time.sleep(0.2)

        if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 已上線：{self.cfg.bridge_url}")
        else:
            self.log(f"[{log_ts()}] Bridge 沒有成功上線，請查看 bridge log。")

    def _stop_bridge_impl(self, kill_external: bool = False) -> None:
        if self.proc_bridge:
            try:
                self.proc_bridge.stop()
            except Exception:
                pass
            self.proc_bridge = None

        if kill_external:
            pid = get_listening_pid_windows(self.cfg.bridge_port)
            if pid:
                try:
                    taskkill_tree(pid)
                except Exception:
                    pass

    def _stop_tts_impl(self, kill_external: bool = False) -> None:
        if self.proc_tts:
            try:
                self.proc_tts.stop()
            except Exception:
                pass
            self.proc_tts = None

        if kill_external:
            pid = get_listening_pid_windows(self.cfg.tts_port)
            if pid:
                try:
                    taskkill_tree(pid)
                except Exception:
                    pass

    def _launcher_api_url(self, path: str) -> str:
        return f"{self.cfg.llm_url}{path}"

    def _decode_http_error(
        self, exc: urllib.error.HTTPError
    ) -> tuple[int, dict, str]:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"data": payload}
        return exc.code, payload, raw

    def _recent_process_log_excerpt(
        self,
        proc: Optional[ManagedProc],
        *,
        max_lines: int = 10,
    ) -> str:
        if not proc:
            return ""

        try:
            path = proc.combined_path
        except Exception:
            return ""

        if not path or not Path(path).exists():
            return ""

        try:
            lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return ""

        tail = [line.rstrip() for line in lines[-max_lines:] if line.strip()]
        return "\n".join(tail)

    def _wait_for_port_closed(
        self,
        name: str,
        host: str,
        port: int,
        *,
        timeout_s: float = 15.0,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_s
        last_pid: Optional[int] = None

        while time.time() < deadline:
            pid = get_listening_pid_windows(port)
            if pid:
                last_pid = pid
            if not port_is_open(host, port, 0.2):
                return True, f"{name} port {port} 已釋放"
            time.sleep(0.25)

        pid = get_listening_pid_windows(port) or last_pid
        if pid:
            return False, f"{name} port {port} 仍被占用（PID={pid}）"
        return False, f"{name} port {port} 在 {timeout_s:.0f}s 內沒有釋放"

    def _wait_for_service_ready(
        self,
        name: str,
        host: str,
        port: int,
        proc: Optional[ManagedProc],
        *,
        timeout_s: float,
        previous_pid: Optional[int] = None,
        stable_hits_required: int = 3,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_s
        stable_hits = 0

        while time.time() < deadline:
            if proc and proc.popen and proc.popen.poll() is not None:
                excerpt = self._recent_process_log_excerpt(proc)
                message = f"{name} 程序提前結束，exit code={proc.popen.returncode}"
                if excerpt:
                    message += f"\n最近 log：\n{excerpt}"
                return False, message

            listener_pid = get_listening_pid_windows(port)
            is_open = port_is_open(host, port, 0.2)

            if is_open and listener_pid and previous_pid and listener_pid == previous_pid:
                stable_hits = 0
                time.sleep(0.25)
                continue

            if is_open:
                stable_hits += 1
                if stable_hits >= stable_hits_required:
                    if listener_pid:
                        return True, f"{name} 已上線（PID={listener_pid}）"
                    return True, f"{name} 已上線"
            else:
                stable_hits = 0

            time.sleep(0.25)

        listener_pid = get_listening_pid_windows(port)
        excerpt = self._recent_process_log_excerpt(proc)
        message = f"{name} 在 {timeout_s:.0f}s 內沒有成功上線"
        if listener_pid:
            message += f"（目前 PID={listener_pid}）"
            if previous_pid and listener_pid == previous_pid:
                message += "；看起來還是舊程序占用"
        if excerpt:
            message += f"\n最近 log：\n{excerpt}"
        return False, message

    def _wait_for_tts_smoke_ready(
        self,
        proc: Optional[ManagedProc],
        char_cfg: Dict[str, object],
        *,
        timeout_s: float,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_s
        last_probe_message = ""
        saw_port = False

        while time.time() < deadline:
            if proc and proc.popen and proc.popen.poll() is not None:
                excerpt = self._recent_process_log_excerpt(proc)
                message = f"TTS 啟動後提前結束，exit code={proc.popen.returncode}"
                if excerpt:
                    message += f"\n最近 log：\n{excerpt}"
                return False, message

            if not port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.2):
                time.sleep(0.4)
                continue

            saw_port = True
            ok, message = probe_tts(
                self.cfg,
                char_cfg,
                logs_root=self.cfg.logs_dir,
                run_id=self.current_run_id or "manual",
                request_timeout_s=25.0,
            )
            if ok:
                return True, message

            last_probe_message = message
            time.sleep(1.0)

        excerpt = self._recent_process_log_excerpt(proc)
        if saw_port:
            message = f"TTS port 已開，但 {timeout_s:.0f}s 內 smoke test 沒成功"
        else:
            message = f"TTS 在 {timeout_s:.0f}s 內沒有成功開 port"
        if last_probe_message:
            message += f"：{last_probe_message}"
        if excerpt:
            message += f"\n最近 log：\n{excerpt}"
        return False, message

    def _should_restart_tts_for_switch(
        self,
        status: dict,
        char_cfg: Dict[str, object],
    ) -> bool:
        if not port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.2):
            return True

        desired_conf_uid = str(char_cfg.get("conf_uid") or "").strip()
        desired_conf_name = str(char_cfg.get("conf_name") or "").strip()
        current_conf_uid = str(
            status.get("conf_uid") or status.get("default_conf_uid") or ""
        ).strip()
        current_conf_name = str(
            status.get("conf_name") or status.get("default_conf_name") or ""
        ).strip()

        if desired_conf_uid and current_conf_uid:
            return desired_conf_uid != current_conf_uid
        if desired_conf_name and current_conf_name:
            return desired_conf_name != current_conf_name
        return True

    def _restart_tts_runtime(
        self,
        character: CharacterRecord,
        char_cfg: Dict[str, object],
    ) -> bool:
        previous_pid = get_listening_pid_windows(self.cfg.tts_port)
        self.log(
            f"[{log_ts()}] 偵測到角色語音設定可能改變，重新載入 TTS：{character.yaml_path.stem}"
        )
        self._stop_tts_impl(kill_external=True)

        closed, close_message = self._wait_for_port_closed(
            "TTS",
            self.cfg.tts_host,
            self.cfg.tts_port,
            timeout_s=15.0,
        )
        if not closed:
            self.log(f"[{log_ts()}] TTS 關閉等待失敗：{close_message}")
            return False

        try:
            self.proc_tts = start_tts(
                self.cfg,
                self.log,
                character_name=character.yaml_path.stem,
                logs_root=self.cfg.logs_dir,
                run_id=self.current_run_id or "manual",
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] TTS 重新載入失敗：{exc}")
            return False

        ready, ready_message = self._wait_for_tts_smoke_ready(
            self.proc_tts,
            char_cfg,
            timeout_s=120.0,
        )
        if not ready:
            self.log(f"[{log_ts()}] TTS 重新載入後沒有成功上線：{ready_message}")
            return False

        self.log(f"[{log_ts()}] TTS 熱切換 smoke test：{ready_message}")
        return True

    def _try_hot_switch_profile(
        self,
        runtime_conf: Dict[str, object],
        char_cfg: Dict[str, object],
        character: CharacterRecord,
        project: ProjectDefinition,
    ) -> bool:
        self.log(
            f"[{log_ts()}] 偵測到 LLM 已在執行，嘗試以 idle 熱切換套用 {character.conf_name} / {project.display_name}。"
        )

        try:
            status = http_get_json(
                self._launcher_api_url("/launcher/status"),
                timeout=5.0,
            )
        except urllib.error.HTTPError as exc:
            code, payload, raw = self._decode_http_error(exc)
            if code == 404:
                self.log(
                    f"[{log_ts()}] 目前執行中的後端還沒有熱切換 API；請手動停止一次角色後再重新啟動。"
                )
            else:
                self.log(
                    f"[{log_ts()}] 讀取熱切換狀態失敗：HTTP {code} {payload.get('error') or raw[:240]}"
                )
            return False
        except Exception as exc:
            self.log(f"[{log_ts()}] 讀取熱切換狀態失敗：{exc}")
            return False

        if not bool(status.get("can_hot_switch")):
            self.log(
                f"[{log_ts()}] 目前不能熱切換：{status.get('reason') or 'unknown'}"
            )
            return False

        if self._should_restart_tts_for_switch(status, char_cfg):
            if not self._restart_tts_runtime(character, char_cfg):
                self.log(f"[{log_ts()}] 已取消這次熱切換，因為 TTS 沒有成功切到新角色。")
                return False

        payload = {
            "runtime_config": runtime_conf,
            "target_client_uid": status.get("target_client_uid"),
            "trigger_source": "launcher",
        }

        try:
            result = http_post_json(
                self._launcher_api_url("/launcher/switch-profile"),
                payload,
                timeout=20.0,
            )
        except urllib.error.HTTPError as exc:
            code, payload, raw = self._decode_http_error(exc)
            self.log(
                f"[{log_ts()}] 熱切換請求失敗：HTTP {code} {payload.get('error') or raw[:240]}"
            )
            return False
        except Exception as exc:
            self.log(f"[{log_ts()}] 熱切換請求失敗：{exc}")
            return False

        self.log(f"[{log_ts()}] {result.get('message') or '熱切換完成。'}")
        return True

    def _prepare_runtime_profile(
        self,
        character: CharacterRecord,
        project: ProjectDefinition,
    ) -> tuple[Optional[Dict[str, object]], Optional[Dict[str, object]]]:
        errors, warnings = validate_profile_assets(self.cfg, character.yaml_path)
        for warning in warnings:
            self.log(f"[{log_ts()}] 警告：{warning}")
        if errors:
            self.log(f"[{log_ts()}] 角色設定檢查失敗：{character.yaml_path.name}")
            for error in errors:
                self.log(f"[{log_ts()}]   - {error}")
            return None, None

        self.log(
            f"[{log_ts()}] 準備 runtime conf：{character.conf_name} / {project.display_name}"
        )
        try:
            runtime_conf, char_cfg = build_runtime_conf(
                open_llm_dir=self.cfg.open_llm_dir,
                character_yaml=character.yaml_path,
                project_yaml=project.path,
                llm_host=self.cfg.llm_host,
                llm_port=self.cfg.llm_port,
                bridge_translate_url=self.cfg.bridge_translate_url,
                llm_provider_env=self.cfg.llm_provider_env,
                llm_default_provider=self.cfg.llm_default_provider,
                openai_model_env=self.cfg.openai_model_env,
                openai_default_model=self.cfg.openai_default_model,
                openai_temp_env=self.cfg.openai_temp_env,
                openai_inject_key_env=self.cfg.openai_inject_key_env,
                openai_api_key_env=self.cfg.openai_api_key_env,
                openai_fallback_key_env=self.cfg.openai_fallback_key_env,
            )
            write_runtime_conf(self.cfg.runtime_conf_path, runtime_conf)
            conf_uid = str(char_cfg.get("conf_uid") or "").strip()
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.current_run_id = f"{ts}_{conf_uid or character.yaml_path.stem}"
            self.log(f"[{log_ts()}] runtime conf: {self.cfg.runtime_conf_path}")
            self.log(
                f"[{log_ts()}] active_project_id: {char_cfg.get('active_project_id', '')}"
            )
            self.log(
                f"[{log_ts()}] persona_prompt_path: {char_cfg.get('persona_prompt_path', '')}"
            )
            self.log(
                f"[{log_ts()}] project_prompt_path: {char_cfg.get('project_prompt_path', '')}"
            )
            self.log(
                f"[{log_ts()}] tool_prompt_path: {char_cfg.get('tool_prompt_path', '')}"
            )
            return runtime_conf, char_cfg
        except Exception as exc:
            self.log(f"[{log_ts()}] 準備 runtime conf 失敗：{exc}")
            return None, None

    def _wait_for_launcher_target(self, timeout: float = 15.0) -> Optional[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = http_get_json(
                    self._launcher_api_url("/launcher/status"),
                    timeout=5.0,
                )
            except Exception:
                time.sleep(0.25)
                continue

            if status.get("target_client_uid"):
                return status
            time.sleep(0.25)
        return None

    def _apply_history_choice(
        self,
        *,
        wait_for_client: bool,
        selected_character: CharacterRecord,
        desired_history_uid: str,
        force_new: bool,
    ) -> bool:
        if not force_new and not desired_history_uid:
            return True

        try:
            status = (
                self._wait_for_launcher_target()
                if wait_for_client
                else http_get_json(
                    self._launcher_api_url("/launcher/status"), timeout=5.0
                )
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] 讀取聊天狀態失敗：{exc}")
            return False
        if not status or not status.get("target_client_uid"):
            self.log(f"[{log_ts()}] 前端尚未連線，聊天選擇暫時無法套用。")
            return False

        active_conf_uid = str(status.get("conf_uid") or status.get("default_conf_uid") or "").strip()
        if selected_character.conf_uid and active_conf_uid and selected_character.conf_uid != active_conf_uid:
            self.log(
                f"[{log_ts()}] 目前執行中的角色與聊天列表角色不同，請先套用角色後再切換聊天。"
            )
            return False

        endpoint = "/launcher/create-history" if force_new else "/launcher/select-history"
        payload = {
            "target_client_uid": status.get("target_client_uid"),
            "trigger_source": "launcher",
        }
        if desired_history_uid:
            payload["history_uid"] = desired_history_uid

        try:
            result = http_post_json(
                self._launcher_api_url(endpoint),
                payload,
                timeout=20.0,
            )
        except urllib.error.HTTPError as exc:
            code, payload, raw = self._decode_http_error(exc)
            self.log(
                f"[{log_ts()}] 聊天切換失敗：HTTP {code} {payload.get('error') or raw[:240]}"
            )
            return False
        except Exception as exc:
            self.log(f"[{log_ts()}] 聊天切換失敗：{exc}")
            return False

        if force_new:
            new_uid = str(result.get("history_uid") or "").strip()
            self.after(0, lambda uid=new_uid: self._after_history_created(uid))
        else:
            self.after(0, self._after_history_selected)

        self.log(f"[{log_ts()}] {result.get('message') or '聊天已切換。'}")
        return True

    def on_apply_history(self) -> None:
        selected_character = self._selected_character()
        if not selected_character:
            messagebox.showinfo("聊天記錄", "請先選擇角色。")
            return

        desired_history_uid = self.history_var.get().strip()
        force_new = self._force_new_history_on_start

        if force_new:
            mode_text = "新增聊天"
        elif not desired_history_uid:
            messagebox.showinfo("聊天記錄", "請先選擇要套用的聊天。")
            return
        else:
            mode_text = "切換聊天"

        if not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            self.log(f"[{log_ts()}] 後端尚未啟動，會在啟動角色時套用{mode_text}。")
            self._sync_history_status_label()
            return

        threading.Thread(
            target=lambda: self._apply_history_choice(
                wait_for_client=True,
                selected_character=selected_character,
                desired_history_uid=desired_history_uid,
                force_new=force_new,
            ),
            daemon=True,
        ).start()

    def on_new_history(self) -> None:
        selected_character = self._selected_character()
        if not selected_character:
            messagebox.showinfo("聊天記錄", "請先選擇角色後再新增聊天。")
            return

        self._force_new_history_on_start = True
        self.history_var.set("")
        self._sync_history_status_label()
        self._refresh_history_transcript(force=True)

        if not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            self.log(f"[{log_ts()}] 已標記為新增聊天，會在啟動角色時建立。")
            return

        threading.Thread(
            target=lambda: self._apply_history_choice(
                wait_for_client=True,
                selected_character=selected_character,
                desired_history_uid="",
                force_new=True,
            ),
            daemon=True,
        ).start()

    def on_toggle_bridge(self) -> None:
        threading.Thread(target=self._toggle_bridge_flow, daemon=True).start()

    def _toggle_bridge_flow(self) -> None:
        if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] 正在停止 Bridge...")
            self._stop_bridge_impl(kill_external=True)
        else:
            self.log(f"[{log_ts()}] 正在啟動 Bridge...")
            self._ensure_bridge_on_start()

    def on_restart_bridge(self) -> None:
        threading.Thread(target=self._restart_bridge_flow, daemon=True).start()

    def _restart_bridge_flow(self) -> None:
        self.log(f"[{log_ts()}] 正在重啟 Bridge...")
        self._stop_bridge_impl(kill_external=True)
        for _ in range(10):
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.2):
                break
            time.sleep(0.2)
        self._ensure_bridge_on_start()

    def on_start_profile(self) -> None:
        character = self._selected_character()
        project = self._selected_project()
        desired_history_uid = self.history_var.get().strip()
        force_new_history = self._force_new_history_on_start
        if not character:
            messagebox.showinfo("啟動角色", "請先選擇角色。")
            return
        if not project:
            messagebox.showinfo("啟動角色", "請先選擇專案。")
            return
        threading.Thread(
            target=self._start_profile_flow,
            args=(character, project, desired_history_uid, force_new_history),
            daemon=True,
        ).start()

    def _start_profile_flow(
        self,
        character: CharacterRecord,
        project: ProjectDefinition,
        desired_history_uid: str,
        force_new_history: bool,
    ) -> None:
        if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 尚未啟動，先補啟動。")
            self._ensure_bridge_on_start()
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                self.log(f"[{log_ts()}] Bridge 仍未成功上線，先中止角色啟動。")
                return

        if port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            runtime_conf, char_cfg = self._prepare_runtime_profile(character, project)
            if runtime_conf is None or char_cfg is None:
                return
            switched = self._try_hot_switch_profile(
                runtime_conf, char_cfg, character, project
            )
            if switched:
                self._launch_pet_electron()
                self._apply_history_choice(
                    wait_for_client=False,
                    selected_character=character,
                    desired_history_uid=desired_history_uid,
                    force_new=force_new_history,
                )
            return

        previous_tts_pid = get_listening_pid_windows(self.cfg.tts_port)
        previous_llm_pid = get_listening_pid_windows(self.cfg.llm_port)
        self.on_stop_profile(silent=True, stop_bridge=False)

        tts_closed, tts_close_message = self._wait_for_port_closed(
            "TTS",
            self.cfg.tts_host,
            self.cfg.tts_port,
            timeout_s=15.0,
        )
        if not tts_closed:
            self.log(f"[{log_ts()}] 啟動前無法清乾淨舊 TTS：{tts_close_message}")
            return

        llm_closed, llm_close_message = self._wait_for_port_closed(
            "LLM",
            self.cfg.llm_host,
            self.cfg.llm_port,
            timeout_s=15.0,
        )
        if not llm_closed:
            self.log(f"[{log_ts()}] 啟動前無法清乾淨舊 LLM：{llm_close_message}")
            return

        errors, warnings = validate_profile_assets(self.cfg, character.yaml_path)
        for warning in warnings:
            self.log(f"[{log_ts()}] 警告：{warning}")
        if errors:
            self.log(f"[{log_ts()}] 角色檢查失敗：{character.yaml_path.name}")
            for error in errors:
                self.log(f"[{log_ts()}]   - {error}")
            return

        self.log(
            f"[{log_ts()}] 建立 runtime conf：角色={character.conf_name}，專案={project.display_name}"
        )
        try:
            runtime_conf, char_cfg = build_runtime_conf(
                open_llm_dir=self.cfg.open_llm_dir,
                character_yaml=character.yaml_path,
                project_yaml=project.path,
                llm_host=self.cfg.llm_host,
                llm_port=self.cfg.llm_port,
                bridge_translate_url=self.cfg.bridge_translate_url,
                llm_provider_env=self.cfg.llm_provider_env,
                llm_default_provider=self.cfg.llm_default_provider,
                openai_model_env=self.cfg.openai_model_env,
                openai_default_model=self.cfg.openai_default_model,
                openai_temp_env=self.cfg.openai_temp_env,
                openai_inject_key_env=self.cfg.openai_inject_key_env,
                openai_api_key_env=self.cfg.openai_api_key_env,
                openai_fallback_key_env=self.cfg.openai_fallback_key_env,
            )
            write_runtime_conf(self.cfg.runtime_conf_path, runtime_conf)
            conf_uid = (char_cfg.get("conf_uid") or "").strip()
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.current_run_id = f"{ts}_{conf_uid or character.yaml_path.stem}"
            self.log(f"[{log_ts()}] runtime conf: {self.cfg.runtime_conf_path}")
            self.log(f"[{log_ts()}] active_project_id: {char_cfg.get('active_project_id', '')}")
            self.log(f"[{log_ts()}] persona_prompt_path: {char_cfg.get('persona_prompt_path', '')}")
            self.log(f"[{log_ts()}] project_prompt_path: {char_cfg.get('project_prompt_path', '')}")
            self.log(f"[{log_ts()}] tool_prompt_path: {char_cfg.get('tool_prompt_path', '')}")
        except Exception as exc:
            self.log(f"[{log_ts()}] 建立 runtime conf 失敗：{exc}")
            return

        try:
            self.proc_tts = start_tts(
                self.cfg,
                self.log,
                character_name=character.yaml_path.stem,
                logs_root=self.cfg.logs_dir,
                run_id=self.current_run_id or "manual",
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] TTS 啟動失敗：{exc}")
            return

        self.log(f"[{log_ts()}] TTS 已啟動，等待 smoke test 成功...")
        tts_ready, tts_ready_message = self._wait_for_tts_smoke_ready(
            self.proc_tts,
            char_cfg,
            timeout_s=120.0,
        )
        if not tts_ready:
            self.log(f"[{log_ts()}] TTS smoke test 失敗：{tts_ready_message}")
            self.on_stop_profile(silent=True)
            return
        self.log(f"[{log_ts()}] TTS smoke test：{tts_ready_message}")

        try:
            self.proc_llm = start_llm(
                self.cfg,
                self.log,
                logs_root=self.cfg.logs_dir,
                run_id=self.current_run_id or "manual",
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] LLM 啟動失敗：{exc}")
            return

        llm_ready, llm_ready_message = self._wait_for_service_ready(
            "LLM",
            self.cfg.llm_host,
            self.cfg.llm_port,
            self.proc_llm,
            timeout_s=35.0,
            previous_pid=previous_llm_pid,
        )
        if llm_ready:
            self.log(f"[{log_ts()}] {llm_ready_message}：{self.cfg.llm_url}")
            self.on_open_electron()
            self._apply_history_choice(
                wait_for_client=True,
                selected_character=character,
                desired_history_uid=desired_history_uid,
                force_new=force_new_history,
            )
        else:
            self.log(f"[{log_ts()}] LLM 沒有成功上線：{llm_ready_message}")

    def on_stop_profile(self, silent: bool = False, stop_bridge: bool = True) -> None:
        self._stop_pet_electron(silent=silent)

        if self.proc_llm:
            try:
                self.proc_llm.stop()
                if not silent:
                    self.log(f"[{log_ts()}] 已停止 LLM。")
            except Exception:
                pass
            self.proc_llm = None

        if self.proc_tts:
            try:
                self.proc_tts.stop()
                if not silent:
                    self.log(f"[{log_ts()}] 已停止 TTS。")
            except Exception:
                pass
            self.proc_tts = None

        for port, name in [
            (self.cfg.llm_port, "LLM"),
            (self.cfg.tts_port, "TTS"),
        ]:
            pid = get_listening_pid_windows(port)
            if pid:
                try:
                    taskkill_tree(pid)
                    if not silent:
                        self.log(f"[{log_ts()}] 已清理 {name} PID={pid}")
                except Exception:
                    pass

        if stop_bridge:
            bridge_was_running = bool(self.proc_bridge) or port_is_open(
                self.cfg.bridge_host, self.cfg.bridge_port, 0.1
            )
            self._stop_bridge_impl(kill_external=True)
            if bridge_was_running and not silent:
                self.log(f"[{log_ts()}] 已停止 Bridge。")

    def on_translate_debug(self) -> None:
        def runner():
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                self.log(f"[{log_ts()}] Bridge 尚未啟動，無法測試 translate debug。")
                return
            try:
                response = http_post_json(
                    self.cfg.bridge_debug_url,
                    {"text": "你好，這是一個 translate debug 測試。"},
                    timeout=12.0,
                )
                self.log(f"[{log_ts()}] translate_debug => {response}")
            except Exception as exc:
                self.log(f"[{log_ts()}] translate_debug 失敗：{exc}")

        threading.Thread(target=runner, daemon=True).start()

    def _pet_control_endpoint(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.cfg.pet_control_url}{path}"

    def _set_pet_status_label(self, text: str) -> None:
        if hasattr(self, "pet_status_label"):
            self.pet_status_label.configure(text=text)

    def _set_pet_shell_online(self, online: bool, text: Optional[str] = None) -> None:
        self._pet_shell_online = online
        if text is not None:
            self._set_pet_status_label(text)

    def _sync_pet_url_entries(self, base_url: str, ws_url: str) -> None:
        focused = self.focus_get()
        if getattr(self, "pet_base_url_entry", None) is not None and focused != self.pet_base_url_entry:
            self.pet_base_url_var.set(base_url)
        if getattr(self, "pet_ws_url_entry", None) is not None and focused != self.pet_ws_url_entry:
            self.pet_ws_url_var.set(ws_url)

    def _sync_pet_toggle_states(self, renderer: dict) -> None:
        state_map = {
            "mic-toggle": "micEnabled",
            "toggle-camera": "cameraEnabled",
            "toggle-screen": "screenEnabled",
            "set-reader-visible": "readerVisible",
        }
        for action, key in state_map.items():
            if key not in renderer:
                continue
            var = self.pet_toggle_vars.get(action)
            if var is not None:
                var.set("on" if bool(renderer.get(key)) else "off")

    def _sync_runtime_history_selection(self, renderer: dict) -> None:
        history_uid = str(
            renderer.get("currentHistoryUid")
            or renderer.get("current_history_uid")
            or ""
        ).strip()
        if not history_uid or self._force_new_history_on_start:
            return
        self._runtime_history_uid = history_uid

        character = self._selected_character()
        if character is None:
            return

        runtime_conf_uid = str(renderer.get("confUid") or renderer.get("conf_uid") or "").strip()
        if runtime_conf_uid and character.conf_uid and runtime_conf_uid != character.conf_uid:
            return

        current = self.history_var.get().strip()
        if current == history_uid:
            self._refresh_history_transcript()
            return

        if current and current in self.history_records:
            self._refresh_history_transcript()
            return

        if history_uid not in self.history_records:
            refreshed_records = self._load_history_records(character)
            if current and current in refreshed_records:
                self.history_records = refreshed_records
                self._sync_history_status_label()
                self._refresh_history_transcript(force=True)
                return
            if history_uid not in refreshed_records:
                return
            self.history_records = refreshed_records

        self.history_var.set(history_uid)
        self._refresh_history_list()

    def _tick_pet_shell_status(self) -> None:
        if not hasattr(self, "pet_status_label"):
            return
        try:
            status = http_get_json(self._pet_control_endpoint("/status"), timeout=0.35)
        except Exception:
            self._set_pet_shell_online(False, "桌寵 shell 離線")
            return

        renderer = status.get("renderer") or {}
        base_url = str(renderer.get("baseUrl") or self.pet_base_url_var.get() or "").strip()
        ws_url = str(renderer.get("wsUrl") or self.pet_ws_url_var.get() or "").strip()
        self._sync_pet_url_entries(base_url, ws_url)
        self._sync_pet_toggle_states(renderer)
        self._sync_runtime_history_selection(renderer)

        ws_badge = str(renderer.get("wsBadge") or "").strip()
        ai_state = str(renderer.get("aiState") or "").strip()
        mode = str(status.get("mode") or "pet").strip()
        summary = f"shell: {mode}"
        if ws_badge:
            summary += f" / {ws_badge}"
        if ai_state:
            summary += f" / {ai_state}"
        self._set_pet_shell_online(True, summary)

    def _run_pet_command(
        self,
        action: str,
        *,
        payload: Optional[dict] = None,
        success_log: Optional[str] = None,
    ) -> None:
        def runner():
            try:
                body = {"action": action}
                if payload:
                    body.update(payload)
                result = http_post_json(
                    self._pet_control_endpoint("/command"),
                    body,
                    timeout=5.0,
                )
            except Exception as exc:
                self.log(f"[{log_ts()}] pet shell 指令失敗（{action}）：{exc}")
                self.after(0, lambda: self._set_pet_shell_online(False, "桌寵 shell 離線"))
                return

            renderer = result.get("renderer") or {}
            base_url = str(renderer.get("baseUrl") or self.pet_base_url_var.get() or "").strip()
            ws_url = str(renderer.get("wsUrl") or self.pet_ws_url_var.get() or "").strip()
            self.after(0, lambda: self._sync_pet_url_entries(base_url, ws_url))
            self.after(0, lambda r=renderer: self._sync_pet_toggle_states(r))
            self.after(0, self._tick_pet_shell_status)
            self.log(f"[{log_ts()}] {success_log or result.get('message') or f'已送出 {action}'}")

        threading.Thread(target=runner, daemon=True).start()

    def on_pet_refresh_status(self) -> None:
        def runner():
            try:
                status = http_get_json(self._pet_control_endpoint("/status"), timeout=5.0)
            except Exception as exc:
                self.log(f"[{log_ts()}] 讀取桌寵 shell 狀態失敗：{exc}")
                self.after(0, lambda: self._set_pet_shell_online(False, "桌寵 shell 離線"))
                return

            renderer = status.get("renderer") or {}
            base_url = str(renderer.get("baseUrl") or self.pet_base_url_var.get() or "").strip()
            ws_url = str(renderer.get("wsUrl") or self.pet_ws_url_var.get() or "").strip()
            button_texts = renderer.get("buttonTexts") or []
            ws_badge = str(renderer.get("wsBadge") or "").strip()
            ai_state = str(renderer.get("aiState") or "").strip()

            self.after(0, lambda: self._sync_pet_url_entries(base_url, ws_url))
            self.after(0, lambda r=renderer: self._sync_pet_toggle_states(r))
            self.after(0, lambda r=renderer: self._sync_runtime_history_selection(r))
            self.after(0, self._tick_pet_shell_status)
            self.log(
                f"[{log_ts()}] pet shell 狀態：mode={status.get('mode')} ws={ws_badge or '-'} ai={ai_state or '-'} buttons={button_texts}"
            )

        threading.Thread(target=runner, daemon=True).start()

    def on_pet_apply_backend_urls(self) -> None:
        base_url = self.pet_base_url_var.get().strip()
        ws_url = self.pet_ws_url_var.get().strip()
        if not base_url or not ws_url:
            messagebox.showinfo("桌寵控制", "請先填入 Base URL 和 WebSocket URL。")
            return

        def runner():
            try:
                result = http_post_json(
                    self._pet_control_endpoint("/backend-config"),
                    {
                        "baseUrl": base_url,
                        "wsUrl": ws_url,
                        "reload": True,
                    },
                    timeout=8.0,
                )
            except Exception as exc:
                self.log(f"[{log_ts()}] 套用桌寵端點失敗：{exc}")
                self.after(0, lambda: self._set_pet_shell_online(False, "桌寵 shell 離線"))
                return

            self.after(0, lambda: self._sync_pet_url_entries(base_url, ws_url))
            self.after(0, self._tick_pet_shell_status)
            self.log(f"[{log_ts()}] {result.get('message') or '已套用桌寵端點並重新載入前端。'}")

        threading.Thread(target=runner, daemon=True).start()

    def on_pet_toggle_mic(self) -> None:
        self._run_pet_command("mic-toggle", success_log="已送出桌寵麥克風切換。")

    def on_pet_interrupt(self) -> None:
        self._run_pet_command("interrupt", success_log="已送出桌寵打斷指令。")

    def on_pet_toggle_camera(self) -> None:
        self._run_pet_command("toggle-camera", success_log="已送出攝影機切換。")

    def on_pet_toggle_screen(self) -> None:
        self._run_pet_command("toggle-screen", success_log="已送出螢幕分享切換。")

    def on_pet_toggle_browser(self) -> None:
        self._run_pet_command("toggle-browser", success_log="已送出瀏覽器面板切換。")

    def on_pet_toggle_subtitle(self) -> None:
        self._run_pet_command("toggle-subtitle", success_log="已送出字幕框切換。")

    def on_open_web_ui(self) -> None:
        webbrowser.open(self.cfg.llm_url)
        self.log(f"[{log_ts()}] 已開啟 Web UI：{self.cfg.llm_url}")

    def _pet_electron_runtime(self) -> tuple[Optional[Path], Optional[str]]:
        pet_dir = self.cfg.pet_electron_dir
        if not pet_dir.exists():
            return None, "找不到 pet-electron 專案資料夾。"

        electron_exe = pet_dir / "node_modules" / "electron" / "dist" / "electron.exe"
        if electron_exe.exists():
            return electron_exe, None

        package_json = pet_dir / "package.json"
        if package_json.exists():
            return None, f"pet-electron 尚未安裝依賴，請先在 {pet_dir} 執行 npm install。"

        return None, "pet-electron 缺少 package.json。"

    def _launch_pet_electron(self) -> bool:
        if self.proc_pet_electron and self.proc_pet_electron.poll() is None:
            self.log(f"[{log_ts()}] 自製桌寵殼已在執行中。")
            return True
        if port_is_open(self.cfg.pet_control_host, self.cfg.pet_control_port, 0.2):
            self.log(f"[{log_ts()}] 自製桌寵殼控制端已在線。")
            return True

        runtime_exe, reason = self._pet_electron_runtime()
        if runtime_exe is None:
            if reason:
                self.log(f"[{log_ts()}] 新桌寵殼未啟動：{reason}")
            return False

        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )

        env = os.environ.copy()
        env["KURO_BACKEND_BASE_URL"] = self.cfg.llm_url
        env["KURO_BACKEND_WS_URL"] = f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws"
        env["KURO_PET_CONTROL_HOST"] = self.cfg.pet_control_host
        env["KURO_PET_CONTROL_PORT"] = str(self.cfg.pet_control_port)

        self.proc_pet_electron = subprocess.Popen(
            [str(runtime_exe), "."],
            cwd=str(self.cfg.pet_electron_dir),
            creationflags=creationflags,
            close_fds=True,
            env=env,
        )
        self.log(f"[{log_ts()}] 已開啟自製桌寵殼：{self.cfg.pet_electron_dir}")
        return True

    def _stop_pet_electron(self, silent: bool = False) -> None:
        stopped = False
        if self.proc_pet_electron and self.proc_pet_electron.poll() is None:
            try:
                taskkill_tree(self.proc_pet_electron.pid)
                stopped = True
            except Exception:
                try:
                    self.proc_pet_electron.terminate()
                    stopped = True
                except Exception:
                    pass
        self.proc_pet_electron = None

        pid = get_listening_pid_windows(self.cfg.pet_control_port)
        if pid:
            try:
                taskkill_tree(pid)
                stopped = True
            except Exception:
                pass

        if stopped and not silent:
            self.log(f"[{log_ts()}] 已停止自製桌寵殼。")

    def on_open_electron(self) -> None:
        try:
            if self.cfg.pet_electron_preferred and self._launch_pet_electron():
                return

            if self.cfg.electron_lnk.exists():
                os.startfile(str(self.cfg.electron_lnk))
                self.log(f"[{log_ts()}] 已開啟舊版 Electron：{self.cfg.electron_lnk}")
            else:
                self.log(f"[{log_ts()}] 找不到 Electron 執行檔。")
                self.log(f"[{log_ts()}] 找不到 Electron 執行檔，未開啟 Web UI。")
        except Exception as exc:
            self.log(f"[{log_ts()}] 開啟 Electron 失敗：{exc}")

    def on_open_logs_dir(self) -> None:
        try:
            self.cfg.logs_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self.cfg.logs_dir))
        except Exception:
            self.log(f"[{log_ts()}] 無法直接打開 logs，路徑：{self.cfg.logs_dir}")

    def on_close(self) -> None:
        try:
            self.on_stop_profile(silent=True)
        except Exception:
            pass
        self.destroy()


def main() -> None:
    here = BASE_DIR
    cfg_path = here / "kuro_launcher.settings.yaml"

    print(f"[launcher] start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[launcher] cwd  : {Path.cwd()}")
    print(f"[launcher] here : {here}")
    print(f"[launcher] cfg  : {cfg_path}")

    for env_path in (here / ".env", here / ".env.local"):
        try:
            loaded = load_env_file(env_path, override=True)
            if loaded:
                print(f"[launcher] env  : loaded {env_path.name} ({loaded} vars)")
        except Exception as exc:
            print(f"[launcher][WARN] failed to load {env_path.name}: {exc}")

    if os.environ.get("OPENAI_LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_LLM_API_KEY"]
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_LLM_API_KEY"):
        os.environ["OPENAI_LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]

    if not cfg_path.exists():
        messagebox.showerror("缺少設定", f"找不到設定檔：{cfg_path}")
        return

    cfg = load_config(cfg_path)
    log_dir = build_logs_dir(cfg.logs_dir, "launcher", run_id=None, aggregate_daily=True)
    log_path = _setup_runtime_logging(log_dir)
    print(f"[launcher] log  : {log_path}")
    print(f"[launcher] root : {cfg.root}")
    print(f"[launcher] provider env: {cfg.llm_provider_env}={os.environ.get(cfg.llm_provider_env, '')}")

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = LauncherApp(cfg)
    print("[launcher] UI ready.")
    app.mainloop()


if __name__ == "__main__":
    main()
