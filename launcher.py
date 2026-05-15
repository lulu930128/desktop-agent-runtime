import datetime
import os
import queue
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from tkinter import messagebox

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
    persona_prompt_path: str
    default_project_id: str


class StatusBadge(ctk.CTkFrame):
    def __init__(self, master, name: str):
        super().__init__(
            master,
            corner_radius=18,
            fg_color="#161d2a",
            border_width=1,
            border_color="#283245",
        )
        self.grid_columnconfigure(1, weight=1)
        self._name = name
        self.dot = ctk.CTkLabel(self, text="●", text_color="#f59e0b", width=18)
        self.dot.grid(row=0, column=0, padx=(12, 6), pady=8)
        self.label = ctk.CTkLabel(
            self,
            text=f"{name} · Offline",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self.label.grid(row=0, column=1, padx=(0, 12), sticky="w")

    def set_status(self, online: bool) -> None:
        self.dot.configure(text_color="#34d399" if online else "#f59e0b")
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


class LauncherApp(ctk.CTk):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg

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

        self._prompt_boxes: Dict[str, ctk.CTkTextbox] = {}
        self._character_radio_buttons: list[ctk.CTkRadioButton] = []
        self._project_radio_buttons: list[ctk.CTkRadioButton] = []

        self.title("Kuro Launcher")
        self.geometry("1560x980")
        self.minsize(1340, 860)
        self.configure(fg_color="#0f1724")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self._refresh_character_list()
        self._refresh_project_list()
        self.after(120, self._drain_log_queue)
        self.after(600, self._tick_status)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text="Kuro Launcher",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block,
            text="Character + project runtime, prompt layering, and service control",
            text_color="#94a3b8",
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", pady=(4, 0))

        badge_row = ctk.CTkFrame(header, fg_color="transparent")
        badge_row.grid(row=0, column=1, sticky="e")
        self.badges = {
            "Bridge": StatusBadge(badge_row, "Bridge"),
            "TTS": StatusBadge(badge_row, "TTS"),
            "LLM": StatusBadge(badge_row, "LLM"),
        }
        for idx, badge in enumerate(self.badges.values()):
            badge.grid(row=0, column=idx, padx=(10 if idx else 0, 0), sticky="ew")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=2)
        content.grid_columnconfigure(2, weight=3)
        content.grid_rowconfigure(0, weight=1)

        self.character_frame = self._build_selector_panel(
            content,
            column=0,
            title="角色",
            subtitle=str(self.cfg.characters_dir),
            refresh_cmd=self._refresh_character_list,
        )
        self.project_frame = self._build_selector_panel(
            content,
            column=1,
            title="專案",
            subtitle=str(self.cfg.projects_dir),
            refresh_cmd=self._refresh_project_list,
        )

        right_panel = ctk.CTkFrame(
            content,
            corner_radius=20,
            fg_color="#111827",
            border_width=1,
            border_color="#1f2937",
        )
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)

        self.summary_box = self._build_card_textbox(
            right_panel,
            row=0,
            title="目前組合",
            subtitle="這裡會顯示目前角色、專案與 prompt 指向。",
            height=210,
        )

        actions_card = self._build_card(right_panel, row=1, title="服務控制", subtitle="啟動、停止與診斷。")
        actions_body = actions_card[1]
        actions_body.grid_columnconfigure(0, weight=1)
        actions_body.grid_columnconfigure(1, weight=1)
        self._action_button(actions_body, "啟動角色", self.on_start_profile, row=0, column=0, primary=True)
        self._action_button(actions_body, "停止角色", self.on_stop_profile, row=0, column=1)
        self._action_button(actions_body, "啟動 / 停止 Bridge", self.on_toggle_bridge, row=1, column=0)
        self._action_button(actions_body, "重啟 Bridge", self.on_restart_bridge, row=1, column=1)
        self._action_button(actions_body, "打開 Web UI", self.on_open_web_ui, row=2, column=0)
        self._action_button(actions_body, "打開 Electron", self.on_open_electron, row=2, column=1)
        self._action_button(actions_body, "Translate Debug", self.on_translate_debug, row=3, column=0)
        self._action_button(actions_body, "打開 Logs", self.on_open_logs_dir, row=3, column=1)

        prompt_card = self._build_card(
            right_panel,
            row=2,
            title="Prompt 預覽",
            subtitle="人格、專案、工具 prompt 目前都已獨立成檔。",
            body_fill="both",
            body_expand=True,
        )
        prompt_body = prompt_card[1]
        prompt_body.grid_rowconfigure(0, weight=1)
        prompt_body.grid_columnconfigure(0, weight=1)
        self.prompt_tabs = ctk.CTkTabview(prompt_body, fg_color="#0b1220")
        self.prompt_tabs.grid(row=0, column=0, sticky="nsew")
        for key, title in [
            ("persona", "角色"),
            ("project", "專案"),
            ("tool", "工具"),
            ("contract", "格式"),
        ]:
            tab = self.prompt_tabs.add(title)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            box = ctk.CTkTextbox(
                tab,
                fg_color="#020617",
                border_width=1,
                border_color="#1e293b",
                font=ctk.CTkFont(size=13),
            )
            box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
            box.configure(state="disabled")
            self._prompt_boxes[key] = box

        log_wrap = ctk.CTkFrame(
            self,
            corner_radius=20,
            fg_color="#111827",
            border_width=1,
            border_color="#1f2937",
        )
        log_wrap.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 18))
        log_wrap.grid_rowconfigure(1, weight=1)
        log_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            log_wrap,
            text="執行紀錄",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))
        self.log_box = ctk.CTkTextbox(
            log_wrap,
            fg_color="#020617",
            border_width=1,
            border_color="#1e293b",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self.log_box.configure(state="disabled")

    def _build_selector_panel(
        self,
        parent,
        *,
        column: int,
        title: str,
        subtitle: str,
        refresh_cmd,
    ) -> ctk.CTkScrollableFrame:
        card = ctk.CTkFrame(
            parent,
            corner_radius=20,
            fg_color="#111827",
            border_width=1,
            border_color="#1f2937",
        )
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
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
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_block,
            text=subtitle,
            text_color="#94a3b8",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(4, 0))
        ctk.CTkButton(
            header,
            text="重新整理",
            width=96,
            command=refresh_cmd,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
        ).grid(row=0, column=1, sticky="e")

        scroll = ctk.CTkScrollableFrame(
            card,
            fg_color="#0b1220",
            corner_radius=16,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        scroll.grid_columnconfigure(0, weight=1)
        return scroll

    def _build_card(self, parent, *, row: int, title: str, subtitle: str, body_fill="x", body_expand=False):
        card = ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color="#0b1220",
            border_width=1,
            border_color="#1e293b",
        )
        card.grid(row=row, column=0, sticky="nsew", padx=14, pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        if body_expand:
            card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text=title, font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head,
            text=subtitle,
            text_color="#94a3b8",
            font=ctk.CTkFont(size=12),
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
            fg_color="#020617",
            border_width=1,
            border_color="#1e293b",
            font=ctk.CTkFont(size=13),
        )
        box.pack(fill="both", expand=True)
        box.configure(state="disabled")
        return box

    def _action_button(self, parent, text: str, command, *, row: int, column: int, primary: bool = False) -> None:
        button = ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=40,
            fg_color="#7c3aed" if primary else "#1f2937",
            hover_color="#6d28d9" if primary else "#334155",
        )
        button.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0), pady=(0, 8))

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
                persona_prompt_path=str(cc.get("persona_prompt_path") or ""),
                default_project_id=str(cc.get("default_project_id") or ""),
            )
            key = str(path)
            self.character_records[key] = record
            radio = ctk.CTkRadioButton(
                self.character_frame,
                text=f"{record.conf_name}\n{path.name}",
                variable=self.character_var,
                value=key,
                command=self._on_character_changed,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#e2e8f0",
                hover_color="#1d4ed8",
                fg_color="#7c3aed",
            )
            radio.grid(sticky="ew", padx=10, pady=(10, 0))
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
                text=f"{project.display_name}\n{project.project_id}",
                variable=self.project_var,
                value=key,
                command=self._on_project_changed,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#e2e8f0",
                hover_color="#1d4ed8",
                fg_color="#7c3aed",
            )
            radio.grid(sticky="ew", padx=10, pady=(10, 0))
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

    def _update_panels(self) -> None:
        character = self._selected_character()
        project = self._selected_project()

        summary_lines = []
        if character:
            summary_lines.extend(
                [
                    f"角色: {character.conf_name}",
                    f"conf_uid: {character.conf_uid or '(未設定)'}",
                    f"Live2D: {character.live2d_model_name or '(未設定)'}",
                    f"角色設定檔: {character.yaml_path}",
                ]
            )
            persona_path = _resolve_repo_path(
                self.cfg.open_llm_dir,
                character.persona_prompt_path,
            )
            summary_lines.append(f"角色 prompt: {persona_path or '(未設定)'}")
        else:
            summary_lines.append("角色: 尚未選擇")

        summary_lines.append("")
        if project:
            summary_lines.extend(
                [
                    f"專案: {project.display_name}",
                    f"project_id: {project.project_id}",
                    f"專案設定檔: {project.path}",
                    f"專案根目錄: {project.project_root}",
                    f"project prompt: {project.project_prompt_path}",
                    f"tool prompt: {project.tool_prompt_path}",
                ]
            )
        else:
            summary_lines.append("專案: 尚未選擇")

        summary_lines.extend(
            [
                "",
                f"runtime conf: {self.cfg.runtime_conf_path}",
                "記憶模式: 依角色 conf_uid 保留，不因專案切換分離。",
            ]
        )
        self._set_textbox(self.summary_box, "\n".join(summary_lines))

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

        self._set_textbox(self._prompt_boxes["persona"], persona_text)
        self._set_textbox(self._prompt_boxes["project"], project_text)
        self._set_textbox(self._prompt_boxes["tool"], tool_text)
        self._set_textbox(self._prompt_boxes["contract"], contract_text)

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

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = LauncherApp(cfg)
    print("[launcher] UI ready.")
    app.mainloop()


if __name__ == "__main__":
    main()
