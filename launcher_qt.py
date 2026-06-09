import datetime
import os
import sys
from pathlib import Path


def _bootstrap_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(getattr(sys, "_MEIPASS")).resolve()
    else:
        base_dir = Path(__file__).parent.resolve()

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    return base_dir


BASE_DIR = _bootstrap_base_dir()
OPEN_LLM_SRC = BASE_DIR / "Open-LLM-VTuber" / "src"
if OPEN_LLM_SRC.exists() and str(OPEN_LLM_SRC) not in sys.path:
    sys.path.insert(0, str(OPEN_LLM_SRC))

WINDOWS_APP_USER_MODEL_ID = "kuro.desktop-agent"


def _set_windows_app_user_model_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except Exception:
        pass


def _load_env() -> None:
    from kuro_launcher.utils import load_env_file

    for env_path in (BASE_DIR / ".env", BASE_DIR / ".env.local"):
        try:
            loaded = load_env_file(env_path, override=True)
            if loaded:
                print(f"[launcher-qt] env  : loaded {env_path.name} ({loaded} vars)")
        except Exception as exc:
            print(f"[launcher-qt][WARN] failed to load {env_path.name}: {exc}")

    if os.environ.get("OPENAI_LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_LLM_API_KEY"]
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_LLM_API_KEY"):
        os.environ["OPENAI_LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]


def main() -> int:
    _set_windows_app_user_model_id()
    _load_env()

    cfg_path = BASE_DIR / "kuro_launcher.settings.yaml"
    print(f"[launcher-qt] start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[launcher-qt] cwd  : {Path.cwd()}")
    print(f"[launcher-qt] here : {BASE_DIR}")
    print(f"[launcher-qt] cfg  : {cfg_path}")

    if not cfg_path.exists():
        print(f"[launcher-qt][ERROR] missing config: {cfg_path}")
        return 2

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as exc:
        print("[launcher-qt][ERROR] PySide6 is not installed in this environment.")
        print("[launcher-qt] install example: python -m pip install -r requirements-qt.txt")
        print(f"[launcher-qt] import error: {exc}")
        return 2

    from kuro_launcher.config import load_config
    from kuro_launcher.qt_app import KuroQtLauncherWindow
    from kuro_launcher.runtime_logging import setup_runtime_logging
    from kuro_launcher.utils import build_logs_dir

    cfg = load_config(cfg_path)
    log_dir = build_logs_dir(cfg.logs_dir, "launcher-qt", run_id=None, aggregate_daily=True)
    log_path = setup_runtime_logging(log_dir)
    print(f"[launcher-qt] log  : {log_path}")
    print(f"[launcher-qt] root : {cfg.root}")

    app = QApplication(sys.argv)
    app.setApplicationName("Kuro")
    app.setApplicationDisplayName("Kuro Desktop Console")
    app.setOrganizationName("Kuro")

    try:
        print("[launcher-qt] window: constructing", flush=True)
        window = KuroQtLauncherWindow(cfg)
        print("[launcher-qt] window: constructed", flush=True)
    except Exception as exc:
        print(f"[launcher-qt][ERROR] window construction failed: {exc}", flush=True)
        QMessageBox.critical(None, "Kuro Desktop Console", f"啟動 Qt launcher 失敗：\n{exc}")
        return 1

    window.show()
    window.showNormal()
    window.raise_()
    window.activateWindow()
    print(
        f"[launcher-qt] window: shown visible={window.isVisible()} minimized={window.isMinimized()}",
        flush=True,
    )
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
