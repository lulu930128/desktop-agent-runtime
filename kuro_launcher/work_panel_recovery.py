"""A modeless recovery surface independent of the hidden legacy console."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox


class WorkPanelRecoveryDialog(QMessageBox):
    def __init__(self, retry):
        super().__init__(None)
        self.setWindowTitle("Kuro 工作面板恢復")
        self.setIcon(QMessageBox.Icon.Warning)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.retry_button = self.addButton("重試開啟", QMessageBox.ButtonRole.ActionRole)
        self.addButton("關閉提示", QMessageBox.ButtonRole.RejectRole)
        self.retry_button.clicked.connect(lambda: (self.hide(), retry()))

    def reveal(self, reason: str, *, allow_retry: bool = True) -> None:
        self.setText("Kuro 工作面板啟動未完成。" if allow_retry else "Kuro 背景服務啟動未完成。")
        self.setInformativeText(f"{reason.splitlines()[0][:300] if reason else '原因尚未取得。'}\n可查看 launcher_logs 的啟動紀錄。工作資料會保留。")
        self.setDetailedText(reason)
        self.retry_button.setVisible(allow_retry)
        self.showNormal()
        self.raise_()
        self.activateWindow()
