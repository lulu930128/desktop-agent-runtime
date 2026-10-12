"""Isolated production-window fixture. Never load user config or start services."""
from contextlib import ExitStack
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Open-LLM-VTuber/src"), str(ROOT / "Open-LLM-VTuber")]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
from kuro_launcher.qt_app import KuroQtLauncherWindow
from kuro_launcher.qt_controller import QtLauncherController, PromptPreview

APP = QApplication.instance() or QApplication([])
if os.name == "nt" and "Microsoft JhengHei" not in QFontDatabase.families():
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("msjh.ttc", "msjhbd.ttc", "segoeui.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont(str(fonts / filename))


class ProductionWindowFixture:
    def __init__(self):
        self.patches = ExitStack()
        self.exceptions = []
        self.patches.enter_context(patch("sys.excepthook", side_effect=lambda *args: self.exceptions.append(args)))
        self.controller = Mock(spec=QtLauncherController)
        self.controller.character_records = {}
        self.controller.project_records = {}
        self.controller.selected_character_key = ""
        self.controller.selected_project_key = ""
        self.controller.selected_character.return_value = None
        self.controller.selected_project.return_value = None
        self.controller.expression_options.return_value = [("neutral", "一般")]
        self.controller.outfit_id = "normal"
        self.controller.thinking_power = "normal"
        self.controller.llm_model = "fixture-model"
        self.controller.read_prompt_preview.return_value = PromptPreview("fixture", "SYNTHETIC", "")
        self.controller.read_memory_records.return_value = ()
        self.controller._normalize_history_message_content.side_effect = MethodType(
            QtLauncherController._normalize_history_message_content, self.controller)
        self.cfg = SimpleNamespace(root=Path("SYNTHETIC"), open_llm_dir=Path("SYNTHETIC"),
            pet_electron_dir=Path("SYNTHETIC"), logs_dir=Path("SYNTHETIC"),
            bridge_url="SYNTHETIC", llm_url="SYNTHETIC", pet_control_url="SYNTHETIC",
            llm_host="127.0.0.1", llm_port=1, startup_auto_start=False,
            openai_models=["fixture-model"], openai_default_model="fixture-model")
        prefs = Mock()
        prefs.value.return_value = False
        prefs.status.return_value = QSettings.Status.NoError
        self.patches.enter_context(patch("kuro_launcher.qt_app.QSettings", return_value=prefs,
            Format=QSettings.Format, Scope=QSettings.Scope, Status=QSettings.Status))
        self.patches.enter_context(patch("kuro_launcher.qt_app.QtLauncherController", return_value=self.controller))
        self.patches.enter_context(patch("kuro_launcher.qt_app.QtScheduleDelivery"))
        self.patches.enter_context(patch("kuro_launcher.qt_app.QTimer.singleShot"))
        self.patches.enter_context(patch.object(KuroQtLauncherWindow, "_create_tray"))
        self.tasks = self.patches.enter_context(patch.object(KuroQtLauncherWindow, "_run_task"))
        self.patches.enter_context(patch("kuro_launcher.qt_app.TodayPage.refresh"))
        # ALL production page builders, history slots and client signals are real.
        self.window = KuroQtLauncherWindow(self.cfg)
        self.window.status_timer.stop()
        self.window.runtime_timer.stop()
        self.window.show()
        APP.processEvents()

    def close(self):
        self.window.explicit_quitting = True
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.patches.close()
        if self.exceptions:
            raise AssertionError(f"Unhandled Qt callback: {self.exceptions}")
