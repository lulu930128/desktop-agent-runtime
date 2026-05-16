import datetime
import json
import math
import os
import queue
import sys
import threading
import time
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


class LauncherApp(ctk.CTk):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self.live2d_catalog = self._load_live2d_catalog()

        self.proc_bridge: Optional[ManagedProc] = None
        self.proc_tts: Optional[ManagedProc] = None
        self.proc_llm: Optional[ManagedProc] = None
        self.current_run_id: Optional[str] = None

        self._log_q: queue.Queue[str] = queue.Queue()
        self._main_thread_id = threading.get_ident()

        self.character_records: Dict[str, CharacterRecord] = {}
        self.project_records: Dict[str, ProjectDefinition] = {}
        self.character_var = ctk.StringVar(value="")
        self.project_var = ctk.StringVar(value="")

        self._prompt_texts: Dict[str, str] = {}
        self.prompt_view_var = ctk.StringVar(value="角色")
        self._character_radio_buttons: list[ctk.CTkRadioButton] = []
        self._project_radio_buttons: list[ctk.CTkRadioButton] = []
        self._preview_photo: Optional[PhotoImage] = None

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
        selection_body.grid_rowconfigure(2, weight=1)

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

        right_panel = ctk.CTkFrame(shell, fg_color="transparent")
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)

        prompt_card = ctk.CTkFrame(
            right_panel,
            corner_radius=18,
            fg_color=PALETTE["panel_soft"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        prompt_card.grid(row=0, column=0, sticky="nsew")
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
        if not character:
            messagebox.showinfo("未選角色", "請先選一個角色。")
            return
        if not project:
            messagebox.showinfo("未選專案", "請先選一個專案。")
            return
        threading.Thread(
            target=self._start_profile_flow,
            args=(character, project),
            daemon=True,
        ).start()

    def _start_profile_flow(
        self,
        character: CharacterRecord,
        project: ProjectDefinition,
    ) -> None:
        if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 尚未啟動，先補啟動。")
            self._ensure_bridge_on_start()
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                self.log(f"[{log_ts()}] Bridge 仍未成功上線，先中止角色啟動。")
                return

        self.on_stop_profile(silent=True)

        for _ in range(20):
            if (
                not port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.1)
                and not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.1)
            ):
                break
            time.sleep(0.2)

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

        for _ in range(50):
            if port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.2):
                break
            time.sleep(0.2)

        if not port_is_open(self.cfg.tts_host, self.cfg.tts_port):
            self.log(f"[{log_ts()}] TTS 沒有成功上線，請查看 tts log。")
            return

        self.log(f"[{log_ts()}] TTS 已上線，開始 smoke test...")
        ok, message = probe_tts(
            self.cfg,
            char_cfg,
            logs_root=self.cfg.logs_dir,
            run_id=self.current_run_id or "manual",
        )
        if not ok:
            self.log(f"[{log_ts()}] TTS smoke test 失敗：{message}")
            self.on_stop_profile(silent=True)
            return
        self.log(f"[{log_ts()}] TTS smoke test：{message}")

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

        for _ in range(70):
            if port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
                break
            time.sleep(0.25)

        if port_is_open(self.cfg.llm_host, self.cfg.llm_port):
            self.log(f"[{log_ts()}] LLM 已上線：{self.cfg.llm_url}")
            self.on_open_electron()
        else:
            self.log(f"[{log_ts()}] LLM 沒有成功上線，請查看 llm log。")

    def on_stop_profile(self, silent: bool = False) -> None:
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

    def on_open_web_ui(self) -> None:
        webbrowser.open(self.cfg.llm_url)
        self.log(f"[{log_ts()}] 已開啟 Web UI：{self.cfg.llm_url}")

    def on_open_electron(self) -> None:
        try:
            if self.cfg.electron_lnk.exists():
                os.startfile(str(self.cfg.electron_lnk))
                self.log(f"[{log_ts()}] 已開啟 Electron：{self.cfg.electron_lnk}")
            else:
                self.log(f"[{log_ts()}] 找不到 Electron 捷徑，改開 Web UI。")
                webbrowser.open(self.cfg.llm_url)
        except Exception as exc:
            self.log(f"[{log_ts()}] 開啟 Electron 失敗：{exc}")
            webbrowser.open(self.cfg.llm_url)

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
