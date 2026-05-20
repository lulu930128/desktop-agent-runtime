from pathlib import Path
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from open_llm_vtuber.character_memory_manager import (
    add_character_memory,
    compact_character_memories,
    delete_character_memory,
    list_character_memories,
    update_character_memory_status,
)

from .memory_support import (
    MEMORY_STATUS_LABELS,
    classify_memory_text,
    ensure_character_memory_root,
    memory_record_is_active,
    memory_status_from_entry,
)
from .records import CharacterRecord, MemoryRecord
from .text_helpers import compact_history_text
from .ui_theme import PALETTE, ui_font
from .utils import log_ts


class MemoryPanelMixin:
    def _memory_path_for_character(
        self, character: Optional[CharacterRecord] = None
    ) -> Optional[Path]:
        character = character or self._selected_character()
        if not character or not character.conf_uid:
            return None
        return (
            self.cfg.open_llm_dir
            / "memories"
            / "characters"
            / character.conf_uid
            / "long_term.json"
        )

    def _selected_memory_record(self) -> Optional[MemoryRecord]:
        return self.memory_records.get(self.memory_var.get().strip())

    def _refresh_memory_list(self) -> None:
        if not hasattr(self, "memory_frame"):
            return
        for child in self.memory_frame.winfo_children():
            child.destroy()
        self._memory_radio_buttons = []
        self.memory_records = {}

        character = self._selected_character()
        if not character:
            self.memory_var.set("")
            ctk.CTkLabel(
                self.memory_frame,
                text="請先選擇角色，這裡才會顯示角色長期記憶。",
                text_color=PALETTE["muted"],
                anchor="w",
                justify="left",
                wraplength=300,
                font=ui_font(12),
            ).grid(sticky="ew", padx=12, pady=(12, 12))
            self.memory_status_label.configure(text="尚未選擇角色。")
            return

        ensure_character_memory_root(self.cfg.open_llm_dir)
        try:
            entries = list_character_memories(
                character.conf_uid,
                enabled_only=False,
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] 角色記憶讀取失敗：{exc}")
            entries = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id") or "").strip()
            content = str(entry.get("content") or "").strip()
            if not entry_id or not content:
                continue
            record = MemoryRecord(
                entry_id=entry_id,
                content=content,
                memory_type=str(entry.get("memory_type") or "fact"),
                enabled=bool(entry.get("enabled", True)),
                status=memory_status_from_entry(entry),
                scope_level=str(entry.get("scope_level") or entry.get("scope") or "character"),
                source=str(entry.get("source") or "unknown"),
                updated_at=str(entry.get("updated_at") or ""),
            )
            self.memory_records[entry_id] = record

        current = self.memory_var.get().strip()
        if self.memory_records:
            if current not in self.memory_records:
                self.memory_var.set(next(iter(self.memory_records)))
        else:
            self.memory_var.set("")

        if not self.memory_records:
            ctk.CTkLabel(
                self.memory_frame,
                text="目前沒有角色長期記憶。對話中說「請記住...」或手動新增後會出現在這裡。",
                text_color=PALETTE["muted"],
                anchor="w",
                justify="left",
                wraplength=300,
                font=ui_font(12),
            ).grid(sticky="ew", padx=12, pady=(12, 12))
        else:
            for entry_id, record in self.memory_records.items():
                status = MEMORY_STATUS_LABELS.get(record.status, record.status or "未知")
                label = (
                    f"[{status}] ({record.memory_type}) "
                    f"{compact_history_text(record.content, max_len=96)}"
                )
                is_active = memory_record_is_active(record)
                is_pending = record.status in {"pending_confirmation", "pending_delete"}
                radio = ctk.CTkRadioButton(
                    self.memory_frame,
                    text=label,
                    variable=self.memory_var,
                    value=entry_id,
                    command=self._on_memory_selected,
                    height=28,
                    radiobutton_width=18,
                    radiobutton_height=18,
                    font=ui_font(12, "bold"),
                    text_color=PALETTE["text"] if is_active else PALETTE["muted"],
                    border_color=PALETTE["panel_border"],
                    hover_color=PALETTE["accent_blue"],
                    fg_color=(
                        PALETTE["accent_lavender"]
                        if is_active
                        else PALETTE["warning"]
                        if is_pending
                        else PALETTE["panel_border"]
                    ),
                )
                radio.grid(sticky="ew", padx=12, pady=(10, 0))
                self._memory_radio_buttons.append(radio)

        enabled_count = sum(
            1 for item in self.memory_records.values() if memory_record_is_active(item)
        )
        pending_count = sum(
            1
            for item in self.memory_records.values()
            if item.status == "pending_confirmation"
        )
        self.memory_status_label.configure(
            text=(
                f"目前角色：{character.conf_name}，共 {len(self.memory_records)} 條，"
                f"啟用 {enabled_count} 條，待確認 {pending_count} 條。"
            )
        )

    def _on_memory_selected(self) -> None:
        record = self._selected_memory_record()
        if record:
            status = MEMORY_STATUS_LABELS.get(record.status, record.status or "未知")
            self.memory_status_label.configure(
                text=(
                    f"已選擇：{status} / {record.scope_level} / {record.source}，"
                    f"{compact_history_text(record.content, max_len=120)}"
                )
            )

    def on_add_memory(self) -> None:
        character = self._selected_character()
        if not character:
            messagebox.showinfo("角色記憶", "請先選擇角色。")
            return
        dialog = ctk.CTkInputDialog(
            text="輸入要加入目前角色的長期記憶：",
            title="新增角色記憶",
        )
        content = (dialog.get_input() or "").strip()
        if not content:
            return
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = add_character_memory(
            character.conf_uid,
            content,
            memory_type=classify_memory_text(content),
        )
        self._refresh_memory_list()
        self._schedule_panel_update()
        if changed:
            self._notify_memory_prompt_refresh()
            self.log(f"[{log_ts()}] 已新增角色記憶：{compact_history_text(content, 48)}")
        else:
            self.log(f"[{log_ts()}] 角色記憶未新增，可能是重複內容或包含敏感資料。")

    def on_toggle_memory(self) -> None:
        character = self._selected_character()
        record = self._selected_memory_record()
        if not character or not record:
            messagebox.showinfo("角色記憶", "請先選擇一條記憶。")
            return
        ensure_character_memory_root(self.cfg.open_llm_dir)
        next_status = "disabled" if memory_record_is_active(record) else "active"
        changed = update_character_memory_status(
            character.conf_uid,
            record.entry_id,
            next_status,
        )
        self._refresh_memory_list()
        self._schedule_panel_update()
        if changed:
            self._notify_memory_prompt_refresh()

    def on_approve_memory(self) -> None:
        character = self._selected_character()
        record = self._selected_memory_record()
        if not character or not record:
            messagebox.showinfo("角色記憶", "請先選擇一條記憶。")
            return
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = update_character_memory_status(
            character.conf_uid,
            record.entry_id,
            "active",
        )
        self._refresh_memory_list()
        self._schedule_panel_update()
        if changed:
            self._notify_memory_prompt_refresh()
            self.log(f"[{log_ts()}] 已批准角色記憶。")

    def on_reject_memory(self) -> None:
        character = self._selected_character()
        record = self._selected_memory_record()
        if not character or not record:
            messagebox.showinfo("角色記憶", "請先選擇一條記憶。")
            return
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = update_character_memory_status(
            character.conf_uid,
            record.entry_id,
            "disabled",
        )
        self._refresh_memory_list()
        self._schedule_panel_update()
        if changed:
            self._notify_memory_prompt_refresh()
            self.log(f"[{log_ts()}] 已拒絕並停用角色記憶。")

    def on_delete_memory(self) -> None:
        character = self._selected_character()
        record = self._selected_memory_record()
        if not character or not record:
            messagebox.showinfo("角色記憶", "請先選擇一條記憶。")
            return
        if not messagebox.askyesno(
            "刪除角色記憶",
            f"確定要刪除這條記憶嗎？\n\n{record.content}",
        ):
            return
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = delete_character_memory(character.conf_uid, record.entry_id)
        self._refresh_memory_list()
        self._schedule_panel_update()
        if changed:
            self._notify_memory_prompt_refresh()
            self.log(f"[{log_ts()}] 已刪除角色記憶。")

    def on_compact_memory(self) -> None:
        character = self._selected_character()
        if not character:
            messagebox.showinfo("角色記憶", "請先選擇角色。")
            return
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed, removed_count = compact_character_memories(character.conf_uid)
        self._refresh_memory_list()
        self._schedule_panel_update()
        if changed:
            self._notify_memory_prompt_refresh()
        self.log(f"[{log_ts()}] 角色記憶已整理，合併/移除 {removed_count} 條。")
