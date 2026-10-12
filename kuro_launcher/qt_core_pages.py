"""Qt Core consumers. Formatting and explicit user commands only; no domain IO."""
from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)


MAIN_NAV_KEYS = ("chat", "today", "schedule")
SETTINGS_LABELS = {
    "general": "助理", "conversation": "對話與記憶", "perception": "語音與感知",
    "tools": "工具與權限", "appearance": "桌寵與外觀", "advanced": "進階診斷",
}


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def text_box():
    box = QPlainTextEdit()
    box.setReadOnly(True)
    box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    return box


def label(text):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def button(text, callback, layout):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    layout.addWidget(widget)
    return widget


class CorePage(QWidget):
    """One in-flight operation per page; all widget changes stay on the Qt thread."""
    completed = Signal(object, object)

    def __init__(self, controller, title, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.busy = False
        self._success = None
        self._failure = None
        self.completed.connect(self._finish)
        outer = QVBoxLayout(self)
        outer.addWidget(label(title))
        self.status = label("尚未讀取 Core。")
        outer.addWidget(self.status)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        outer.addWidget(self.body, 1)

    def run(self, operation, success, failure=None):
        if self.busy:
            return
        self.busy = True
        self.body.setEnabled(False)
        self.status.setText("正在讀取／提交 Core…")
        self._success, self._failure = success, failure

        def worker():
            try:
                result, error = operation(), None
            except Exception as exc:
                result, error = None, str(exc)
            try:
                self.completed.emit(result, error)
            except RuntimeError:
                # The parent window may have closed while the bounded request ran.
                return

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, result, error):
        self.busy = False
        self.body.setEnabled(True)
        if error is not None:
            self.status.setText(f"Core 操作失敗：{error}\n未確認成功；請重新讀取。")
            if self._failure:
                self._failure(error)
        else:
            self.status.setText("Core 已回應。")
            try:
                self._success(result)
            except (KeyError, TypeError, ValueError) as exc:
                self.status.setText(f"Core 回應格式無效：{exc}")
                if self._failure:
                    self._failure(str(exc))


def today_text(payload):
    """Render Core's supplied decisions without inferring health or reclassifying."""
    if (payload.get("contract") != "kuro.core.today.v1"
            or type(payload.get("complete")) is not bool
            or not all(isinstance(payload.get(key), list) for key in ("items", "sections", "sourceStates"))):
        raise ValueError("Today contract/complete/items/sections/sourceStates")
    complete = payload["complete"]
    heading = "來源證據健康" if complete else "來源不完整"
    empty = ("目前提供的來源證據中沒有待處理項目。" if complete
             else "尚無可呈現項目；來源不完整，不能解讀為沒有工作。")
    lines = [heading, "complete 僅表示已提供的來源／證據健康，不代表真實世界工作覆蓋完整。"]
    lines.extend(f"{key}: {payload.get(key, '—')}" for key in
                 ("generatedAt", "asOf", "localDate", "timezone", "complete"))
    lines.append(f"suppressed: {payload.get('counts', {}).get('suppressed', '—')}")
    lines.append("limitations: " + pretty(payload.get("limitations", [])))
    if not payload["items"]:
        lines.append(empty)
    return "\n".join(lines)


class TodayPage(CorePage):
    summary_changed = Signal(str)
    context_requested = Signal(dict)
    schedule_requested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(controller, "Today", parent)
        self._payload = None
        self._fresh = False
        actions = QHBoxLayout()
        button("重新讀取 Today", self.refresh, actions)
        button("查看行程", self.schedule_requested.emit, actions)
        self.layout.addLayout(actions)
        self.meta = text_box()
        self.meta.setMaximumHeight(94)
        self.layout.addWidget(self.meta)
        self.layout.addWidget(label("今日重點 · Core 排序前五筆"))
        self.priority = QListWidget()
        self.priority.setMaximumHeight(140)
        self.priority.itemClicked.connect(lambda item: self.select_work(item.data(Qt.ItemDataRole.UserRole)))
        self.layout.addWidget(self.priority)
        self.source_filter = QComboBox()
        self.source_filter.addItem("所有來源", "")
        self.source_filter.currentIndexChanged.connect(self._render_items)
        self.layout.addWidget(self.source_filter)
        split = QSplitter()
        self.items = QListWidget()
        self.detail = text_box()
        self.items.currentItemChanged.connect(self.show_detail)
        split.addWidget(self.items)
        split.addWidget(self.detail)
        self.layout.addWidget(split, 1)
        self.context_button = button("帶入普通對話草稿", self.use_context, self.layout)
        self.context_button.setEnabled(False)
        self.sources = text_box()
        self.sources.setMaximumHeight(84)
        self.layout.addWidget(label("來源狀態（Mail / Study 與其他 Core 已配置來源）"))
        self.layout.addWidget(self.sources)
        self.layout.addWidget(label("Mail／Study 狀態依 Core 顯示。舊的郵件內文、手動 provider 刷新與課程跳轉未恢復：沒有正式 action owner。"))

    def refresh(self):
        self.run(self.controller.read_today, self.apply, self.clear_failed)

    def clear_failed(self, _error):
        self._fresh = False
        self.context_button.setEnabled(False)
        self.status.setText(f"Today 讀取失敗：{_error}。以下若有內容是上次投影，尚未更新。")
        self.summary_changed.emit("Today 無法讀取；完整度未知。")

    def apply(self, payload):
        meta = today_text(payload)
        by_id = {item["workId"]: item for item in payload["items"]}
        if any(item_id not in by_id for section in payload["sections"] for item_id in section["itemIds"]):
            raise ValueError("Today section references missing work")
        self._payload = copy.deepcopy(payload)
        self._fresh = True
        self.meta.setPlainText(meta)
        self.sources.setPlainText("\n".join(
            f"{state.get('integrationId', state.get('source', '未提供'))} · "
            f"{state.get('availability', '未提供')} · {state.get('freshness', '未提供')} · {state.get('connection', '未提供')}\n"
            f"觀察：{state.get('observedAt') or '未提供'} · 有效至：{state.get('validUntil') or '未提供'} · 限制：{state.get('limitationCount', '未提供')}"
            for state in payload["sourceStates"]) or "Core 尚未提供來源狀態；不能解讀為來源正常。")
        selected_source = self.source_filter.currentData()
        sources = sorted({str(item.get("source") or "") for item in payload["items"]}
                         | {str(state.get("integrationId") or state.get("source") or "") for state in payload["sourceStates"]})
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("所有來源", "")
        for source in sources:
            if source:
                self.source_filter.addItem(source, source)
        self.source_filter.setCurrentIndex(max(0, self.source_filter.findData(selected_source)))
        self.source_filter.blockSignals(False)
        self.priority.clear()
        for item in payload["items"][:5]:
            row = QListWidgetItem(f"{item['title']} · {item['source']} · {item['level']}")
            row.setData(Qt.ItemDataRole.UserRole, item["workId"])
            self.priority.addItem(row)
        if not payload["items"]:
            row = QListWidgetItem("目前沒有可呈現重點；來源限制請見上方。")
            row.setFlags(Qt.ItemFlag.NoItemFlags)
            self.priority.addItem(row)
        self.priority.setFixedHeight(min(134, max(40, self.priority.count() * 25 + 8)))
        self._render_items()
        self.status.setText("來源證據健康" if payload["complete"] else "來源不完整")
        self.summary_changed.emit(self.status.text())

    def _render_items(self, *_args):
        if self._payload is None:
            return
        previous = self.items.currentItem()
        previous_data = previous.data(Qt.ItemDataRole.UserRole) if previous else None
        selected_id = previous_data.get("workId") if previous_data else None
        scroll = self.items.verticalScrollBar().value()
        selected_row = None
        self.items.blockSignals(True)
        self.items.clear()
        by_id = {item["workId"]: item for item in self._payload["items"]}
        source = self.source_filter.currentData()
        titles = {"immediate": "立即處理", "focus": "今日專注", "watch": "持續留意", "normal": "其他工作"}
        for section in self._payload["sections"]:
            members = [by_id[uid] for uid in section["itemIds"] if not source or by_id[uid]["source"] == source]
            if not members:
                continue
            header = QListWidgetItem(f"{titles.get(section['kind'], section['kind'])} · {len(members)}")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.items.addItem(header)
            for item in members:
                row = QListWidgetItem(f"{item['title']}\n{item['source']} · {item['level']} · {item.get('dueAt') or '—'}")
                row.setData(Qt.ItemDataRole.UserRole, item)
                self.items.addItem(row)
                if item["workId"] == selected_id:
                    selected_row = row
        if selected_row is not None:
            self.items.setCurrentItem(selected_row)
        self.items.blockSignals(False)
        self.items.verticalScrollBar().setValue(scroll)
        self.show_detail(selected_row)

    def show_detail(self, current, _previous=None):
        item = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.context_button.setEnabled(bool(item) and self._fresh)
        detail = self.detail_text(item) if item else "選擇工作項目查看詳情；排序與狀態由 Core 提供。"
        if detail != self.detail.toPlainText():
            scroll = self.detail.verticalScrollBar().value()
            self.detail.setPlainText(detail)
            self.detail.verticalScrollBar().setValue(scroll)

    def detail_text(self, item):
        payload = self._payload or {}
        return "\n".join((str(item.get("title") or "未命名"), str(item.get("summary") or ""), "",
            f"來源：{item.get('source')} · 項目：{item.get('workId')}",
            f"優先層級：{item.get('level')} · 截止：{item.get('dueAt') or '未提供'}",
            f"原因：{', '.join(item.get('reasonCodes') or [])}",
            f"下一步類型：{item.get('actionKind') or '未提供'}",
            f"證據：{item.get('evidenceRef') or '未提供'}",
            f"stale：{item.get('stale', '未提供')} · partial：{item.get('partial', '未提供')}",
            f"投影時間：{payload.get('asOf') or '未提供'} · 時區：{payload.get('timezone') or '未提供'}",
            f"限制：{', '.join(payload.get('limitations') or []) or 'Core 未列出限制'}"))

    def select_work(self, uid):
        self.source_filter.setCurrentIndex(0)
        for index in range(self.items.count()):
            row = self.items.item(index)
            item = row.data(Qt.ItemDataRole.UserRole)
            if item and item["workId"] == uid:
                self.items.setCurrentItem(row)
                return

    def use_context(self):
        current = self.items.currentItem()
        item = current.data(Qt.ItemDataRole.UserRole) if current else None
        if item and self.context_button.isEnabled():
            self.context_requested.emit({"workId": item["workId"], "title": item.get("title"),
                                         "source": item.get("source"), "text": self.detail_text(item)})


class CoreHealthPage(CorePage):
    def __init__(self, controller, parent=None):
        super().__init__(controller, "Core／來源狀態", parent)
        self.layout.addWidget(label("查看 Core capabilities 與來源健康。提醒設定在 Schedule 表單；此頁不啟動來源刷新。"))
        button("重新讀取 Core / Sources", self.refresh, self.layout)
        self.capabilities = text_box()
        self.sources = text_box()
        self.layout.addWidget(label("Core capabilities"))
        self.layout.addWidget(self.capabilities, 1)
        self.layout.addWidget(label("Source health / limitations"))
        self.layout.addWidget(self.sources, 1)

    def refresh(self):
        def read():
            # Independent failures retain useful capability evidence.
            result = {}
            for key, operation in (("status", self.controller.read_core_status), ("today", self.controller.read_today)):
                try:
                    result[key] = operation()
                except Exception as exc:
                    result[key] = {"error": str(exc)}
            return result
        self.run(read, self.apply)

    def apply(self, result):
        self.capabilities.setPlainText(pretty(result["status"].get("capabilities", result["status"])))
        today = result["today"]
        self.sources.setPlainText(pretty({key: today[key] for key in
            ("error", "complete", "asOf", "sourceStates", "limitations") if key in today}))
        self.status.setText("Core / Sources 讀取失敗" if any("error" in v for v in result.values())
                            else "來源證據健康" if today.get("complete") is True else "來源不完整")


class ScheduleEditor(QDialog):
    """Form serialization only. Core prepare owns wall time and rule validation."""
    def __init__(self, controller, item, command, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule — 新增" if command["action"] == "create" else "Schedule — 編輯")
        self.resize(650, 720)
        self.command = copy.deepcopy(command)
        self.last_payload = None
        self.last_result = None
        outer = QVBoxLayout(self)
        self.page = CorePage(controller, "儲存前由 Core 驗證；儲存即確認此次本機操作。")
        outer.addWidget(self.page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_body = QWidget()
        form = QFormLayout(form_body)
        scroll.setWidget(form_body)
        self.page.layout.addWidget(scroll)
        self.fields = {}
        for key, title in (("title", "標題"), ("notes", "備註"), ("timezone", "IANA 時區"),
                           ("start", "開始"), ("end", "結束（全天為不含此日）"), ("due", "截止")):
            field = QLineEdit(str(item.get(key, "")))
            self.fields[key] = field
            form.addRow(title, field)
        self.kind = QComboBox()
        self.kind.addItems(["event", "study", "deadline"])
        self.kind.setCurrentText(item.get("kind", "event"))
        form.insertRow(1, "類型", self.kind)
        self.all_day = QCheckBox("全天（YYYY-MM-DD）；非全天使用 YYYY-MM-DDTHH:MM")
        self.all_day.setChecked(item.get("allDay", False))
        form.addRow(self.all_day)
        self.track = QCheckBox("追蹤完成狀態")
        self.track.setChecked(item.get("trackCompletion", item.get("kind") != "event"))
        form.addRow(self.track)
        rule = item.get("recurrence") or {}
        self.frequency = QComboBox()
        self.frequency.addItems(["none", "daily", "weekly", "monthly"])
        self.frequency.setCurrentText(rule.get("frequency", "none"))
        self.frequency.setEnabled(command.get("scope") != "this")
        self.interval = QSpinBox()
        self.interval.setRange(1, 120)
        self.interval.setValue(rule.get("interval", 1))
        form.addRow("重複", self.frequency)
        form.addRow("間隔", self.interval)
        weekdays = QWidget()
        week_layout = QHBoxLayout(weekdays)
        self.weekdays = []
        for index, title in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            check = QCheckBox(title)
            check.setChecked(index in rule.get("weekdays", []))
            self.weekdays.append(check)
            week_layout.addWidget(check)
        form.addRow("每週日期", weekdays)
        self.ending = QComboBox()
        self.ending.addItems(["none", "count", "until"])
        self.ending.setCurrentText("count" if "count" in rule else "until" if "until" in rule else "none")
        self.count = QSpinBox()
        self.count.setRange(1, 100000)
        self.count.setValue(rule.get("count", 1))
        self.until = QLineEdit(rule.get("until", ""))
        self.until.setPlaceholderText("YYYY-MM-DD")
        form.addRow("重複結束條件", self.ending)
        form.addRow("次數", self.count)
        form.addRow("最後日期", self.until)
        notification = item.get("notification") or {}
        self.notify = QCheckBox("啟用提醒")
        self.notify.setChecked(notification.get("enabled", False))
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 10080)
        self.minutes.setValue(notification.get("minutesBefore", 10))
        self.clock = QLineEdit(notification.get("allDayTime", "09:00"))
        self.channel = QComboBox()
        self.channel.addItems(["panel", "desktop"])
        self.channel.setCurrentText(notification.get("channel", "panel"))
        form.addRow(self.notify)
        form.addRow("提前分鐘", self.minutes)
        form.addRow("全天提醒時間 HH:MM", self.clock)
        form.addRow("通知管道", self.channel)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.page.layout.addWidget(self.buttons)
        self.kind.currentTextChanged.connect(self.sync_fields)
        self.frequency.currentTextChanged.connect(self.sync_fields)
        self.ending.currentTextChanged.connect(self.sync_fields)
        self.sync_fields()

    def sync_fields(self, *_args):
        deadline = self.kind.currentText() == "deadline"
        for key in ("start", "end"):
            self.fields[key].setEnabled(not deadline)
        self.fields["due"].setEnabled(deadline)
        recurring = self.frequency.currentText() != "none"
        self.interval.setEnabled(recurring)
        self.ending.setEnabled(recurring)
        self.count.setEnabled(recurring and self.ending.currentText() == "count")
        self.until.setEnabled(recurring and self.ending.currentText() == "until")
        for check in self.weekdays:
            check.setEnabled(self.frequency.currentText() == "weekly")

    def item_payload(self):
        keys = ("title", "notes", "timezone") + (("due",) if self.kind.currentText() == "deadline" else ("start", "end"))
        item = {key: self.fields[key].text().strip() for key in keys}
        item.update(kind=self.kind.currentText(), allDay=self.all_day.isChecked(), trackCompletion=self.track.isChecked())
        rule = None
        if self.frequency.currentText() != "none":
            rule = {"frequency": self.frequency.currentText(), "interval": self.interval.value()}
            if rule["frequency"] == "weekly":
                rule["weekdays"] = [i for i, check in enumerate(self.weekdays) if check.isChecked()]
            if self.ending.currentText() == "count":
                rule["count"] = self.count.value()
            elif self.ending.currentText() == "until":
                rule["until"] = self.until.text().strip()
        item["recurrence"] = rule
        item["notification"] = dict(enabled=self.notify.isChecked(), minutesBefore=self.minutes.value(),
                                    allDayTime=self.clock.text().strip(), channel=self.channel.currentText())
        return item

    def save(self):
        item = self.item_payload()
        # Retrying identical input retains the idempotency key after a lost response.
        if self.last_payload != item:
            self.command["idempotencyKey"] = uuid.uuid4().hex
            self.last_payload = copy.deepcopy(item)
        command = dict(self.command, confirmed=True)
        controller = self.page.controller

        def submit():
            prepared = controller.prepare_schedule(item)
            return controller.mutate_schedule(dict(command, item=prepared["item"]))

        self.page.run(submit, self.saved)

    def saved(self, result):
        self.last_result = result
        self.accept()

    def reject(self):
        if not self.page.busy:
            super().reject()


class SchedulePage(CorePage):
    def __init__(self, controller, parent=None):
        super().__init__(controller, "Schedule", parent)
        self.next_offset = None
        self.loaded_query = None
        self.core_timezone = None
        self.rows = []
        controls = QHBoxLayout()
        self.day = QDateEdit(QDate.currentDate())
        self.day.setDisplayFormat("yyyy-MM-dd")
        self.day.setCalendarPopup(True)
        self.span = QComboBox()
        self.span.addItem("單日", 1)
        self.span.addItem("7 日", 7)
        controls.addWidget(self.day)
        controls.addWidget(self.span)
        button("讀取", self.refresh, controls)
        self.add_button = button("新增", self.add, controls)
        self.add_button.setEnabled(False)
        self.layout.addLayout(controls)
        self.meta = text_box()
        self.meta.setMaximumHeight(130)
        self.layout.addWidget(self.meta)
        tabs = QTabWidget()
        events = QWidget()
        event_layout = QVBoxLayout(events)
        split = QSplitter()
        self.items = QListWidget()
        self.detail = text_box()
        self.items.currentItemChanged.connect(self.show_detail)
        split.addWidget(self.items)
        split.addWidget(self.detail)
        event_layout.addWidget(split, 1)
        actions = QGridLayout()
        self.action_buttons = []
        for index, (title, callback) in enumerate((
            ("編輯", self.edit), ("完成", lambda: self.mutate("complete")),
            ("重新開啟", lambda: self.mutate("reopen")), ("略過", lambda: self.mutate("skip")),
            ("取消行程", lambda: self.mutate("cancel")),
        )):
            control = QPushButton(title)
            control.clicked.connect(callback)
            actions.addWidget(control, 0, index)
            self.action_buttons.append(control)
        event_layout.addLayout(actions)
        self.more = button("載入更多", self.load_more, event_layout)
        self.more.setEnabled(False)
        self.materialize = button("請 Core 補齊此範圍", self.advance, event_layout)
        self.materialize.setEnabled(False)
        tabs.addTab(events, "行程")
        reminders = QWidget()
        reminder_layout = QVBoxLayout(reminders)
        self.reminders = QListWidget()
        reminder_layout.addWidget(self.reminders, 1)
        self.reminder_meta = text_box()
        self.reminder_meta.setMaximumHeight(140)
        reminder_layout.addWidget(self.reminder_meta)
        reminder_actions = QHBoxLayout()
        button("Dismiss", lambda: self.reminder_action("dismiss"), reminder_actions)
        button("Snooze", lambda: self.reminder_action("snooze"), reminder_actions)
        reminder_layout.addLayout(reminder_actions)
        tabs.addTab(reminders, "提醒紀錄")
        self.layout.addWidget(tabs, 1)
        self.day.dateChanged.connect(self.invalidate_query)
        self.span.currentIndexChanged.connect(self.invalidate_query)
        self.show_detail(None)

    def invalidate_query(self, *_args):
        self.loaded_query = None
        self.next_offset = None
        self.more.setEnabled(False)
        self.materialize.setEnabled(False)
        self.items.clear()
        self.detail.clear()
        self.status.setText("日期範圍已變更，請讀取。")

    def refresh(self):
        first = self.core_timezone is None
        chosen = self.day.date().toString("yyyy-MM-dd")
        span = self.span.currentData()
        controller = self.controller

        def read():
            status = controller.read_core_status()["capabilities"]["schedule"]
            start = status["today"] if first else chosen
            end = (date.fromisoformat(start) + timedelta(days=span)).isoformat()
            query = dict(start=start, end=end, timezone=status["timezone"])
            view = controller.read_schedule_view(**query)
            try:
                reminders = controller.read_schedule_notifications()
            except Exception as exc:
                reminders = {"error": str(exc)}
            return status, query, view, reminders

        self.run(read, self.apply, self.clear_failed)

    def clear_failed(self, _error):
        self.invalidate_query()
        self.status.setText(f"Core 無法讀取：{_error}；不可視為空行程。")
        self.meta.clear()
        self.reminders.clear()
        self.reminder_meta.clear()
        self.add_button.setEnabled(False)

    def apply(self, result):
        status, query, view, reminders = result
        if view.get("contract") != "kuro.core.schedule.v1":
            raise ValueError("Schedule contract")
        previous = self.selected()
        selected_key = (previous.get("scheduleId"), previous.get("occurrenceDate")) if previous else None
        scroll = self.items.verticalScrollBar().value()
        self.core_timezone = status["timezone"]
        self.day.blockSignals(True)
        self.day.setDate(QDate.fromString(query["start"], "yyyy-MM-dd"))
        self.day.blockSignals(False)
        self.loaded_query = query
        self.items.blockSignals(True)
        self.items.clear()
        self.rows = []
        self.append_view(view)
        selected = None
        for index in range(self.items.count()):
            row = self.items.item(index)
            record = row.data(Qt.ItemDataRole.UserRole)
            if (record.get("scheduleId"), record.get("occurrenceDate")) == selected_key:
                selected = row
                self.items.setCurrentItem(row)
                break
        self.items.blockSignals(False)
        self.items.verticalScrollBar().setValue(scroll)
        self.show_detail(selected)
        self.meta.setPlainText(pretty({"status": status, **{key: value for key, value in view.items() if key != "items"}}))
        self.reminders.clear()
        for record in reminders.get("items", []):
            row = QListWidgetItem(f"{record['title']} · {record['state']}\n{record['dueAt']} · {record['channel']}")
            row.setData(Qt.ItemDataRole.UserRole, record)
            self.reminders.addItem(row)
        self.reminder_meta.setPlainText(pretty({key: value for key, value in reminders.items() if key != "items"}))
        self.add_button.setEnabled(True)
        self.materialize.setEnabled(view.get("coverage") != "complete")

    def append_view(self, view):
        if view.get("contract") != "kuro.core.schedule.v1":
            raise ValueError("Schedule contract")
        self.rows.extend(view["items"])
        for record in view["items"]:
            item = record["item"]
            row = QListWidgetItem(f"{item['title']} · {item['kind']} · {record['state']}\n"
                                 f"{item.get('due') or item.get('start')} · {record['timeState']}"
                                 + (" · overdue" if record.get("overdue") else ""))
            row.setData(Qt.ItemDataRole.UserRole, record)
            self.items.addItem(row)
        self.next_offset = view.get("nextOffset") if view.get("hasMore") else None
        self.more.setEnabled(self.next_offset is not None)
        self.status.setText(f"coverage: {view['coverage']} · 已載入 {len(self.rows)} 筆 · limitations: {pretty(view.get('limitations', []))}")

    def load_more(self):
        if self.loaded_query is not None and self.next_offset is not None:
            query = dict(self.loaded_query, offset=self.next_offset)
            self.run(lambda: self.controller.read_schedule_view(**query), self.append_view)

    def selected(self):
        row = self.items.currentItem()
        return row.data(Qt.ItemDataRole.UserRole) if row else None

    def show_detail(self, current, _previous=None):
        record = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.detail.setPlainText(pretty(record) if record else "")
        for control in self.action_buttons:
            control.setEnabled(record is not None)

    def choose_scope(self, record):
        if not record.get("recurring"):
            return "all"
        scope, ok = QInputDialog.getItem(self, "操作範圍", "this：本次 / future：本次起 / all：全部", ["this", "future", "all"], 0, False)
        return scope if ok else None

    def command(self, action, record, scope):
        result = dict(action=action, id=record["scheduleId"], expectedRevision=record["revision"],
                      scope=scope, confirmed=True, idempotencyKey=uuid.uuid4().hex)
        if scope != "all":
            result["occurrenceDate"] = record["occurrenceDate"]
        return result

    def open_editor(self, item, command):
        dialog = ScheduleEditor(self.controller, item, command, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def add(self):
        if not self.core_timezone:
            return
        chosen = self.day.date().toString("yyyy-MM-dd")
        item = dict(title="", kind="event", timezone=self.core_timezone, allDay=False,
                    start=chosen + "T09:00", end=chosen + "T10:00", due=chosen + "T17:00")
        self.open_editor(item, {"action": "create"})

    def edit(self):
        record = self.selected()
        if not record:
            return
        scope = self.choose_scope(record)
        if scope is None:
            return
        command = self.command("update", record, scope)

        def open_result(canonical):
            if canonical["revision"] != record["revision"]:
                self.status.setText("Core conflict：行程已變更，請重新讀取後編輯。")
                return
            item = copy.deepcopy(canonical["item"] if scope == "all" else record["item"])
            if scope == "future":
                item["recurrence"] = canonical["item"].get("recurrence")
            self.open_editor(item, command)

        self.run(lambda: self.controller.read_schedule_item(record["scheduleId"]), open_result)

    def mutate(self, action):
        record = self.selected()
        if not record:
            return
        scope = self.choose_scope(record) if action == "cancel" else "this"
        if scope is None or QMessageBox.question(self, "確認 Schedule 操作",
                f"{action} / {scope}\n{record['item']['title']}\n{record['scheduleId']} · revision {record['revision']}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        command = self.command(action, record, scope)
        self.run(lambda: self.controller.mutate_schedule(command), lambda _result: self.refresh())

    def advance(self):
        if self.loaded_query:
            through = self.loaded_query["end"]
            if QMessageBox.question(self, "補齊行程實例", f"請 Core 補齊至 {through} 的本機行程實例？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.run(lambda: self.controller.materialize_schedule(through), lambda _result: self.refresh())

    def reminder_action(self, action):
        row = self.reminders.currentItem()
        if row is None:
            return
        record = row.data(Qt.ItemDataRole.UserRole)
        payload = dict(action=action, id=record["id"], confirmed=True)
        if action == "snooze":
            until, ok = QInputDialog.getText(self, "Snooze", "延後至（ISO 時間含時區，例如 2026-10-09T15:30:00+08:00）")
            if not ok:
                return
            payload["until"] = until.strip()
        if QMessageBox.question(self, "確認提醒操作", f"{action}\n{record['title']}\n{payload.get('until', '')}") != QMessageBox.StandardButton.Yes:
            return
        self.run(lambda: self.controller.schedule_notification_action(payload), lambda _result: self.refresh())
