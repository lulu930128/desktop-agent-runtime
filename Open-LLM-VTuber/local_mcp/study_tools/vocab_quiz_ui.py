from __future__ import annotations

import importlib.util
import os
import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any


CURRENT_DIR = Path(__file__).resolve().parent
DEFAULT_OPEN_LLM_ROOT = CURRENT_DIR.parent.parent
KURO_OPEN_LLM_ROOT = Path(
    os.getenv("KURO_OPEN_LLM_ROOT", str(DEFAULT_OPEN_LLM_ROOT))
).resolve()
TRACKER_PATH = Path(
    os.getenv(
        "KURO_STUDY_TRACKER_PATH",
        str(KURO_OPEN_LLM_ROOT / "local_mcp" / "study_tools" / "vocab_tracker.py"),
    )
).resolve()
DEFAULT_STATE_DIR = Path(
    os.getenv("KURO_STUDY_STATE_DIR", str(KURO_OPEN_LLM_ROOT / "private" / "study"))
).resolve()

DIRECTION_LABELS = {
    "jp_to_zh": "日文 → 中文",
    "zh_to_jp": "中文 → 日文",
}

POOL_LABELS = {
    "today": "今日計畫",
    "due": "到期複習",
    "new": "新單字",
    "mistakes": "錯題",
    "all": "全部單字",
}

RESULT_LABELS = {
    "correct": "答對",
    "wrong": "答錯",
    "easy": "太簡單",
}


def load_tracker_module() -> Any:
    if not TRACKER_PATH.exists():
        raise FileNotFoundError(f"找不到 vocab_tracker.py：{TRACKER_PATH}")
    spec = importlib.util.spec_from_file_location("kuro_vocab_tracker", TRACKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 tracker：{TRACKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["kuro_vocab_tracker"] = module
    spec.loader.exec_module(module)
    return module


class VocabQuizApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Kuro 隨機單字考試")
        self.geometry("860x680")
        self.minsize(760, 580)

        self.tracker = load_tracker_module()
        self.state_dir = DEFAULT_STATE_DIR
        self.progress_path = self.state_dir / self.tracker.PROGRESS_FILE
        self.progress: dict[str, Any] = {}
        self.records: dict[str, dict[str, Any]] = {}
        self.level_vars: dict[str, tk.BooleanVar] = {}
        self.level_buttons: dict[str, tk.Button] = {}
        self.current_record: dict[str, Any] | None = None
        self.current_answer_visible = False
        self.used_word_ids: set[str] = set()
        self.session_counts = {
            "correct": 0,
            "wrong": 0,
            "easy": 0,
            "skipped": 0,
            "total": 0,
        }

        self.direction_var = tk.StringVar(value="jp_to_zh")
        self.pool_var = tk.StringVar(value="today")
        self.status_var = tk.StringVar(value="")
        self.session_var = tk.StringVar(value="")
        self.question_var = tk.StringVar(value="按「開始 / 下一題」抽一題。")
        self.detail_var = tk.StringVar(value="")
        self.answer_var = tk.StringVar(value="")

        self.configure(bg="#11151c")
        self._build_ui()
        self._load_progress()
        self._refresh_level_filters()
        self._update_status()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#11151c")
        style.configure("Panel.TFrame", background="#1d2330")
        style.configure("TLabel", background="#11151c", foreground="#eaf0ff", font=("Microsoft JhengHei UI", 11))
        style.configure("Muted.TLabel", background="#11151c", foreground="#9aa6bd", font=("Microsoft JhengHei UI", 10))
        style.configure("Panel.TLabel", background="#1d2330", foreground="#eaf0ff", font=("Microsoft JhengHei UI", 11))
        style.configure("Title.TLabel", background="#11151c", foreground="#ffffff", font=("Microsoft JhengHei UI", 20, "bold"))
        style.configure("Question.TLabel", background="#1d2330", foreground="#ffffff", font=("Microsoft JhengHei UI", 24, "bold"))
        style.configure("Answer.TLabel", background="#1d2330", foreground="#73d6cf", font=("Microsoft JhengHei UI", 16))
        style.configure("TButton", font=("Microsoft JhengHei UI", 11), padding=(10, 6))
        style.configure("Accent.TButton", font=("Microsoft JhengHei UI", 11, "bold"), padding=(12, 7))
        style.configure("TCheckbutton", background="#11151c", foreground="#eaf0ff", font=("Microsoft JhengHei UI", 10))
        style.map("TCheckbutton", background=[("active", "#11151c")], foreground=[("active", "#ffffff")])
        style.configure("TCombobox", font=("Microsoft JhengHei UI", 10), fieldbackground="#252c3a")

        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Kuro 隨機單字考試", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(18, 12))

        ttk.Label(controls, text="範圍").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.level_frame = ttk.Frame(controls)
        self.level_frame.grid(row=0, column=1, sticky="w")

        ttk.Label(controls, text="題型").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        direction_box = ttk.Combobox(
            controls,
            width=16,
            state="readonly",
            textvariable=self.direction_var,
            values=list(DIRECTION_LABELS.values()),
        )
        direction_box.grid(row=1, column=1, sticky="w", pady=(10, 0))
        self._format_combobox_text(direction_box, DIRECTION_LABELS)

        ttk.Label(controls, text="抽題").grid(row=1, column=2, sticky="w", padx=(24, 10), pady=(10, 0))
        pool_box = ttk.Combobox(
            controls,
            width=16,
            state="readonly",
            textvariable=self.pool_var,
            values=list(POOL_LABELS.values()),
        )
        pool_box.grid(row=1, column=3, sticky="w", pady=(10, 0))
        self._format_combobox_text(pool_box, POOL_LABELS)

        button_bar = ttk.Frame(root)
        button_bar.pack(fill="x", pady=(2, 12))
        ttk.Button(button_bar, text="開始 / 下一題", style="Accent.TButton", command=self.next_question).pack(side="left")
        ttk.Button(button_bar, text="顯示答案", command=self.show_answer).pack(side="left", padx=(8, 0))
        ttk.Button(button_bar, text="重新讀取進度", command=self.reload_progress).pack(side="right")

        panel = ttk.Frame(root, style="Panel.TFrame", padding=22)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, textvariable=self.question_var, style="Question.TLabel", wraplength=760, justify="left").pack(fill="x")
        ttk.Label(panel, textvariable=self.detail_var, style="Panel.TLabel", wraplength=760, justify="left").pack(fill="x", pady=(10, 0))
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=18)
        ttk.Label(panel, textvariable=self.answer_var, style="Answer.TLabel", wraplength=760, justify="left").pack(fill="x")

        result_bar = ttk.Frame(root)
        result_bar.pack(fill="x", pady=(14, 0))
        ttk.Button(result_bar, text="答對", command=lambda: self.record_result("correct")).pack(side="left")
        ttk.Button(result_bar, text="答錯", command=lambda: self.record_result("wrong")).pack(side="left", padx=(8, 0))
        ttk.Button(result_bar, text="太簡單", command=lambda: self.record_result("easy")).pack(side="left", padx=(8, 0))
        ttk.Button(result_bar, text="跳過", command=self.skip_question).pack(side="left", padx=(8, 0))
        ttk.Label(result_bar, textvariable=self.session_var, style="Muted.TLabel").pack(side="right")

    def _format_combobox_text(self, combo: ttk.Combobox, labels: dict[str, str]) -> None:
        value = combo.get()
        if value in labels:
            combo.set(labels[value])

    def _combobox_key(self, value: str, labels: dict[str, str]) -> str:
        for key, label in labels.items():
            if value == key or value == label:
                return key
        return next(iter(labels))

    def _load_progress(self) -> None:
        self.progress = self.tracker.read_json(self.progress_path, None)
        if not isinstance(self.progress, dict):
            raise FileNotFoundError(f"找不到單字進度檔，請先執行 scan：{self.progress_path}")
        records = self.progress.get("records")
        if not isinstance(records, dict):
            raise ValueError(f"單字進度檔格式不正確：{self.progress_path}")
        self.records = {
            word_id: record
            for word_id, record in records.items()
            if isinstance(record, dict) and not record.get("missingFromSource")
        }

    def reload_progress(self) -> None:
        try:
            self._load_progress()
            self._refresh_level_filters()
            self.used_word_ids.clear()
            self._update_status()
            messagebox.showinfo("已重新讀取", "單字進度已重新讀取。")
        except Exception as exc:
            messagebox.showerror("讀取失敗", str(exc))

    def _refresh_level_filters(self) -> None:
        for child in self.level_frame.winfo_children():
            child.destroy()
        levels = sorted({
            self.tracker.clean_text((record.get("word") or {}).get("level"))
            for record in self.records.values()
            if self.tracker.clean_text((record.get("word") or {}).get("level"))
        })
        preferred = [level for level in ["N3", "N2", "N4-5", "N1", "日本常用", "資工用語"] if level in levels]
        levels = preferred + [level for level in levels if level not in preferred]
        self.level_vars = {}
        self.level_buttons = {}
        for index, level in enumerate(levels):
            var = tk.BooleanVar(value=True)
            self.level_vars[level] = var
            button = tk.Button(
                self.level_frame,
                text=self._level_button_text(level),
                command=lambda item=level: self._toggle_level(item),
                anchor="w",
                bd=0,
                highlightthickness=0,
                padx=0,
                pady=0,
                bg="#11151c",
                activebackground="#11151c",
                fg="#eaf0ff",
                activeforeground="#ffffff",
                font=("Microsoft JhengHei UI", 10),
                cursor="hand2",
            )
            self.level_buttons[level] = button
            button.grid(
                row=index // 6,
                column=index % 6,
                sticky="w",
                padx=(0, 10),
            )

    def _level_button_text(self, level: str) -> str:
        checked = self.level_vars[level].get()
        return f"{'✓' if checked else '□'} {level}"

    def _toggle_level(self, level: str) -> None:
        self.level_vars[level].set(not self.level_vars[level].get())
        button = self.level_buttons.get(level)
        if button:
            button.configure(text=self._level_button_text(level))
        self._reset_pool_usage()

    def _selected_levels(self) -> set[str]:
        selected = {level for level, var in self.level_vars.items() if var.get()}
        return selected or set(self.level_vars)

    def _reset_pool_usage(self) -> None:
        self.used_word_ids.clear()
        self._update_status()

    def _record_matches_level(self, record: dict[str, Any]) -> bool:
        level = self.tracker.clean_text((record.get("word") or {}).get("level"))
        return level in self._selected_levels()

    def _pool_records(self) -> list[dict[str, Any]]:
        pool = self._combobox_key(self.pool_var.get(), POOL_LABELS)
        candidates = [
            record for record in self.records.values()
            if self._record_matches_level(record) and not record.get("suspended")
        ]
        if pool == "all":
            return candidates
        if pool == "new":
            return [record for record in candidates if record.get("status") == "new"]
        if pool == "mistakes":
            return [record for record in candidates if int(record.get("wrong_count") or 0) > 0]
        if pool == "due":
            return [record for record in candidates if self.tracker.is_due(record)]
        if pool == "today":
            chosen = self.tracker.choose_today_words(
                self.progress,
                review_count=50,
                new_count=50,
                focus_count=50,
                level_order=list(self._selected_levels()),
            )
            ids = {
                word["word_id"]
                for group in chosen.values()
                for word in group
            }
            return [record for record in candidates if record.get("word_id") in ids]
        return candidates

    def _pick_record(self) -> dict[str, Any] | None:
        candidates = self._pool_records()
        if not candidates:
            return None
        fresh = [record for record in candidates if record.get("word_id") not in self.used_word_ids]
        if not fresh:
            self.used_word_ids.clear()
            fresh = candidates
        return random.choice(fresh)

    def next_question(self) -> None:
        record = self._pick_record()
        if not record:
            self.current_record = None
            self.question_var.set("目前範圍沒有可抽的單字。")
            self.detail_var.set("可以換範圍、改成全部單字，或先執行 scan 更新資料。")
            self.answer_var.set("")
            return
        self.current_record = record
        self.current_answer_visible = False
        self.used_word_ids.add(str(record.get("word_id") or ""))
        self._render_question(show_answer=False)

    def _render_question(self, *, show_answer: bool) -> None:
        if not self.current_record:
            return
        word = self.current_record.get("word") or {}
        direction = self._combobox_key(self.direction_var.get(), DIRECTION_LABELS)
        level = self.tracker.clean_text(word.get("level"))
        pos = self.tracker.clean_text(word.get("pos"))
        seen = int(self.current_record.get("seen_count") or 0)
        wrong = int(self.current_record.get("wrong_count") or 0)

        if direction == "zh_to_jp":
            self.question_var.set(self.tracker.clean_text(word.get("meaning")) or "(沒有中文)")
            self.detail_var.set(f"{level} / {pos} / 已看 {seen} 次 / 錯 {wrong} 次")
            answer = "\n".join([
                f"日文：{self.tracker.clean_text(word.get('kanji'))}",
                f"讀音：{self.tracker.clean_text(word.get('reading'))}",
                f"例句：{self.tracker.clean_text(word.get('sentence'))}",
                f"例句中文：{self.tracker.clean_text(word.get('sentenceMeaning'))}",
            ])
        else:
            kanji = self.tracker.clean_text(word.get("kanji"))
            reading = self.tracker.clean_text(word.get("reading"))
            self.question_var.set(kanji or reading or "(沒有日文)")
            self.detail_var.set(f"{level} / {pos} / 已看 {seen} 次 / 錯 {wrong} 次")
            answer = "\n".join([
                f"讀音：{reading}",
                f"中文：{self.tracker.clean_text(word.get('meaning'))}",
                f"例句：{self.tracker.clean_text(word.get('sentence'))}",
                f"例句中文：{self.tracker.clean_text(word.get('sentenceMeaning'))}",
            ])

        self.answer_var.set(answer if show_answer else "答案已隱藏。")

    def show_answer(self) -> None:
        if not self.current_record:
            messagebox.showinfo("尚未開始", "請先按「開始 / 下一題」。")
            return
        self.current_answer_visible = True
        self._render_question(show_answer=True)

    def skip_question(self) -> None:
        if not self.current_record:
            return
        self.session_counts["skipped"] += 1
        self._update_status()
        self.next_question()

    def record_result(self, result: str) -> None:
        if not self.current_record:
            messagebox.showinfo("尚未開始", "請先按「開始 / 下一題」。")
            return
        try:
            word_id = str(self.current_record.get("word_id") or "")
            before = self.records[word_id]
            after = self.tracker.mark_record(before, result)
            self.records[word_id] = after
            self.progress["records"][word_id] = after
            self.progress["updatedAt"] = self.tracker.now_iso()
            self.tracker.write_json(self.state_dir / self.tracker.PROGRESS_FILE, self.progress)
            self.tracker.append_jsonl(self.state_dir / self.tracker.EVENTS_FILE, {
                "time": self.tracker.now_iso(),
                "word_id": word_id,
                "mode": "quiz",
                "direction": self._combobox_key(self.direction_var.get(), DIRECTION_LABELS),
                "result": result,
                "source": "vocab_quiz_ui",
                "before": self._event_state(before),
                "after": self._event_state(after),
            })
            self._write_snapshot()
            self.session_counts[result] += 1
            self.session_counts["total"] += 1
            self.current_record = after
            self._update_status()
            self.next_question()
        except Exception as exc:
            messagebox.showerror("記錄失敗", str(exc))

    def _write_snapshot(self) -> None:
        snapshot = self.tracker.build_snapshot(
            self.progress,
            review_count=20,
            new_count=10,
            focus_count=8,
            level_order=self.tracker.DEFAULT_LEVEL_ORDER,
        )
        self.tracker.write_json(self.state_dir / self.tracker.SNAPSHOT_FILE, snapshot)

    def _event_state(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": record.get("status"),
            "seen_count": record.get("seen_count"),
            "correct_count": record.get("correct_count"),
            "wrong_count": record.get("wrong_count"),
            "next_review": record.get("next_review"),
        }

    def _update_status(self) -> None:
        stats = self.tracker.progress_stats(self.progress) if self.progress else {}
        self.status_var.set(
            f"單字 {stats.get('total', 0)} / 到期 {stats.get('due', 0)} / 錯題 {stats.get('withMistakes', 0)}"
        )
        self.session_var.set(
            "本次："
            f"答對 {self.session_counts['correct']} / "
            f"答錯 {self.session_counts['wrong']} / "
            f"簡單 {self.session_counts['easy']} / "
            f"跳過 {self.session_counts['skipped']}"
        )


def main() -> int:
    try:
        app = VocabQuizApp()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Kuro 隨機單字考試啟動失敗", str(exc))
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
