"""The single Work Companion surface; all data and actions come from its host."""
from __future__ import annotations
import html
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget)
from .qt_work_companion_theme import TOKENS, work_companion_qss


class HistoryDrawer(QFrame):
    """Git main.ts renderHistoryDrawer/historyRow, with owner-supplied records."""
    selected = Signal(str)
    delete_requested = Signal(str)
    create_requested = Signal()
    refresh_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryDrawer")
        self.records = []
        self.active_uid = ""
        self.ready = False
        self.pending = False
        self.error = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        heading = QHBoxLayout()
        heading.addWidget(label("對話紀錄", "sectionTitle"), 1)
        close = QPushButton("×")
        close.setAccessibleName("關閉對話紀錄")
        close.clicked.connect(self.close_requested)
        heading.addWidget(close)
        layout.addLayout(heading)
        self.create = QPushButton("＋ 新對話")
        self.create.setObjectName("CreateHistory")
        self.create.clicked.connect(self.create_requested)
        layout.addWidget(self.create)
        self.search = QLineEdit()
        self.search.setObjectName("HistorySearch")
        self.search.setPlaceholderText("搜尋對話")
        self.search.setAccessibleName("搜尋對話紀錄")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.status = label("對話服務尚未連線", "muted", wrap=True)
        layout.addWidget(self.status)
        self.list = QListWidget()
        self.list.setObjectName("HistoryList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemActivated.connect(lambda item: self.selected.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.list, 1)
        self.refresh = QPushButton("重新讀取")
        self.refresh.clicked.connect(self.refresh_requested)
        layout.addWidget(self.refresh)
        self.set_state(ready=False)

    def set_records(self, records, active_uid):
        self.records = list(records)
        self.active_uid = active_uid
        self._filter()

    def set_state(self, *, ready, pending=False, error=""):
        self.ready, self.pending = bool(ready), bool(pending)
        self.error = error
        self.create.setEnabled(self.ready and not self.pending)
        self.list.setEnabled(self.ready and not self.pending)
        self.refresh.setEnabled(self.ready and not self.pending)
        self.status.setText(error or ("正在處理對話紀錄…" if pending else "" if ready else "對話服務尚未就緒"))
        if not error and ready and not pending:
            self._empty_status()

    def _empty_status(self):
        if self.error:
            self.status.setText(self.error)
            return
        self.status.setText("" if self.list.count() else
                            "找不到符合的對話" if self.search.text().strip() else "目前沒有對話紀錄；可建立新對話。")

    def _filter(self, _query=""):
        scroll = self.list.verticalScrollBar().value()
        self.list.clear()
        query = self.search.text().strip().casefold()
        for record in self.records:
            if query and query not in f"{record.title} {record.preview}".casefold():
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record.uid)
            item.setSizeHint(QSize(0, 88))
            self.list.addItem(item)
            row = QWidget()
            row.setProperty("active", record.uid == self.active_uid)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(2, 4, 2, 4)
            title = record.title or "新對話"
            preview = record.preview or ("尚未開始" if record.is_empty else "沒有預覽")
            meta = record.timestamp or "時間未提供"
            open_button = QPushButton(f"{title[:42]}\n{preview[:46]}\n{meta}{' · 目前' if record.uid == self.active_uid else ''}")
            open_button.setObjectName("HistoryOpen")
            open_button.setCheckable(True)
            open_button.setChecked(record.uid == self.active_uid)
            open_button.setToolTip(f"{title}\n{preview}\n{record.uid}")
            open_button.clicked.connect(lambda _checked=False, uid=record.uid: self.selected.emit(uid))
            remove = QPushButton("×")
            remove.setObjectName("DeleteHistory")
            remove.setAccessibleName(f"刪除 {title}")
            remove.setFixedWidth(30)
            remove.clicked.connect(lambda _checked=False, uid=record.uid: self.delete_requested.emit(uid))
            layout.addWidget(open_button, 1)
            layout.addWidget(remove)
            self.list.setItemWidget(item, row)
        self.list.verticalScrollBar().setValue(scroll)
        if self.ready and not self.pending:
            self._empty_status()


def transcript_html(messages, *, compact=False):
    """Render plain Git message-copy semantics, preserving whitespace and escaping HTML."""
    rows = []
    for role, timestamp, content in messages:
        role_label = {"User": "YOU", "human": "YOU", "user": "YOU", "Kuro": "KURO",
                      "assistant": "KURO", "ai": "KURO"}.get(role, "EVENT")
        color = "#65b3a6" if role_label == "KURO" else "#929bad"
        text = html.escape(str(content)).replace("\n", "<br>")
        rows.append(f'<tr><td width="68" valign="top" style="color:{color};font-size:11px">{role_label}</td>'
                    f'<td style="padding-bottom:{9 if compact else 18}px"><div style="white-space:pre-wrap">{text}</div>'
                    f'<div style="font-size:10px;color:#929bad">{html.escape(str(timestamp))}</div></td></tr>')
    return '<table width="100%" cellspacing="0" cellpadding="8">' + ''.join(rows) + '</table>'


def label(text: str, role: str = "", *, wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setProperty("role", role)
    result.setWordWrap(wrap)
    result.setMinimumWidth(0)
    return result


def icon(name: str, color: str = TOKENS.muted) -> QIcon:
    """Small local vector strokes, rendered at 2x; no assets or remote fonts."""
    pixmap = QPixmap(40, 40)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.35, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    path = QPainterPath()
    if name == "chat":
        path.moveTo(4, 4); path.lineTo(16, 4); path.lineTo(16, 13)
        path.lineTo(9, 13); path.lineTo(5, 17); path.lineTo(5, 13); path.lineTo(4, 13)
        path.closeSubpath()
    elif name == "today":
        painter.drawRoundedRect(QRectF(3, 5, 14, 12), 1, 1)
        painter.drawLine(3, 9, 17, 9)
        painter.drawLine(7, 3, 7, 7); painter.drawLine(13, 3, 13, 7)
        painter.drawLine(7, 12, 9, 12); painter.drawLine(11, 12, 13, 12)
    elif name == "settings":
        for x, y in ((5, 7), (10, 13), (15, 8)):
            painter.drawLine(x, 3, x, 17)
            painter.drawEllipse(QRectF(x - 2, y - 2, 4, 4))
    elif name == "history":
        painter.drawArc(QRectF(3, 3, 14, 14), -60 * 16, 300 * 16)
        painter.drawLine(3, 3, 3, 8); painter.drawLine(3, 8, 7, 8)
        painter.drawLine(10, 6, 10, 10); painter.drawLine(10, 10, 13, 12)
    elif name == "attach":
        path.moveTo(7, 14); path.lineTo(13, 8)
        path.cubicTo(15, 5, 12, 3, 10, 5); path.lineTo(4, 11)
        path.cubicTo(0, 16, 6, 20, 10, 16); path.lineTo(16, 10)
    elif name == "close":
        painter.drawLine(5, 5, 15, 15); painter.drawLine(15, 5, 5, 15)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class ComposerEdit(QPlainTextEdit):
    submit_requested = Signal()

    def __init__(self):
        super().__init__()
        self._composing = False
        self.setAccessibleName("對話訊息輸入")
        self.setPlaceholderText("問 Kuro，或從今天的項目延伸討論…")
        self.setMinimumHeight(44)
        self.setMaximumHeight(92)
        self.setTabChangesFocus(True)
        self.textChanged.connect(self._fit_height)
        self._fit_height()

    def _fit_height(self):
        lines = self.document().documentLayout().documentSize().height()
        self.setFixedHeight(min(92, max(44, round(lines * self.fontMetrics().lineSpacing() + 12))))

    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                and not self._composing):
            if not event.isAutoRepeat():
                self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class WorkCompanionView(QWidget):
    """Single production shell, including its one History drawer.

    Pages are real controller consumers supplied by KuroQtLauncherWindow. The
    shell never creates fixtures, performs IO, or owns conversation state.
    """
    page_changed = Signal(str)

    def __init__(self, *, chat: QWidget, today: QWidget, schedule: QWidget,
                 settings: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkCompanionView")
        self.setStyleSheet(work_companion_qss())
        self.pages = {"chat": chat, "today": today, "schedule": schedule, "settings": settings}
        self.page = "chat"
        self.return_focus = None
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.rail = QFrame()
        self.rail.setObjectName("Rail")
        rail = QVBoxLayout(self.rail)
        rail.setContentsMargins(12, 20, 12, 16)
        rail.setSpacing(12)
        self.brand = label("Kuro", "brand")
        rail.addWidget(self.brand)
        self.brand_subtitle = label("Work Companion", "muted", wrap=True)
        rail.addWidget(self.brand_subtitle)
        rail.addSpacing(20)
        self.nav_buttons = {}
        self.nav_labels = {"chat": "對話", "today": "今天", "schedule": "行程", "settings": "設定"}
        for key, title in self.nav_labels.items():
            if key == "settings":
                rail.addStretch()
            control = QPushButton(title)
            control.setObjectName("CompanionNav")
            control.setProperty("page", key)
            control.setCheckable(True)
            control.setAccessibleName(title)
            control.setToolTip(title)
            control.setIcon(icon("today" if key == "schedule" else key))
            control.clicked.connect(lambda _checked=False, key=key: self.page_changed.emit(key))
            self.nav_buttons[key] = control
            rail.addWidget(control)
        outer.addWidget(self.rail)
        self.stage = QWidget()
        stage_layout = QVBoxLayout(self.stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)
        chrome = QFrame()
        chrome.setObjectName("Chrome")
        chrome_layout = QHBoxLayout(chrome)
        chrome_layout.setContentsMargins(24, 12, 24, 12)
        chrome_layout.addWidget(label("WORK COMPANION", "caption"))
        chrome_layout.addStretch()
        self.runtime_status = label("對話尚未連線", "muted")
        chrome_layout.addWidget(self.runtime_status)
        stage_layout.addWidget(chrome)
        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)
        stage_layout.addWidget(self.stack, 1)
        self.privacy_status = label("麥克風／鏡頭／畫面狀態尚未取得", "muted", wrap=True)
        self.privacy_status.setContentsMargins(24, 6, 24, 8)
        stage_layout.addWidget(self.privacy_status)
        outer.addWidget(self.stage, 1)

        self.scrim = QPushButton(self.stage)
        self.scrim.setObjectName("HistoryScrim")
        self.scrim.setAccessibleName("關閉對話紀錄")
        self.scrim.clicked.connect(lambda: self.show_history(False))
        self.history_drawer = HistoryDrawer(self.stage)
        self.history_drawer.close_requested.connect(lambda: self.show_history(False))
        self.escape = QShortcut(QKeySequence("Escape"), self)
        self.escape.activated.connect(lambda: self.show_history(False))
        self.show_history(False)
        self.set_page("chat")

    def set_page(self, key: str):
        if key not in self.pages:
            return
        if key != "chat":
            self.show_history(False)
        self.page = key
        self.stack.setCurrentWidget(self.pages[key])
        compact = key != "chat"
        self.setProperty("mode", "settings" if compact else "chat")
        self.rail.setFixedWidth(TOKENS.settings_rail if compact else TOKENS.chat_rail)
        self.brand.setText("K" if compact else "Kuro")
        self.brand_subtitle.setVisible(not compact)
        for name, control in self.nav_buttons.items():
            control.setText("" if compact else self.nav_labels[name])
            control.setChecked(name == key)
        self.style().unpolish(self)
        self.style().polish(self)

    def show_history(self, visible: bool):
        visible = bool(visible and self.page == "chat")
        self.scrim.setVisible(visible)
        self.history_drawer.setVisible(visible)
        if visible:
            self._position_drawer()
            self.scrim.raise_()
            self.history_drawer.raise_()
            self.history_drawer.search.setFocus()
        elif self.return_focus is not None and self.page == "chat":
            self.return_focus.setFocus()

    def _position_drawer(self):
        self.scrim.setGeometry(self.stage.rect())
        self.history_drawer.setGeometry(0, 0, min(360, self.stage.width()), self.stage.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_drawer()
