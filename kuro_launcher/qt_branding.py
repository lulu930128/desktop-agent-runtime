"""One existing Kuro asset for the Qt application, window and tray."""
import logging
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

ICON_PATH = Path(__file__).resolve().parents[1] / "pet-electron/src/assets/favicon.ico"


def load_kuro_icon(path: Path = ICON_PATH) -> QIcon:
    icon = QIcon(str(path)) if path.is_file() else QIcon()
    # Some icon engines accept the filename but cannot decode any pixels.
    if not icon.isNull() and not icon.pixmap(32, 32).isNull():
        return icon
    logging.getLogger(__name__).warning("Kuro icon unavailable; using Qt fallback")
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
