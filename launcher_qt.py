import datetime
import os
import sys
import time
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
WORK_PANEL_ARG = "--work-panel"
WINDOWS_INSTANCE_MUTEX_NAME = "Local\\KuroDesktopAgentLauncher"
WINDOWS_INSTANCE_ACTIVATE_EVENT_NAME = "Local\\KuroDesktopAgentLauncherActivate"
WINDOWS_ERROR_ALREADY_EXISTS = 183
WINDOWS_EVENT_MODIFY_STATE = 0x0002
WINDOWS_WAIT_OBJECT_0 = 0x00000000
_instance_mutex_handle = None
_instance_activate_event_handle = None


def _consume_work_panel_arg(argv: list[str]) -> tuple[bool, list[str]]:
    work_panel_mode = WORK_PANEL_ARG in argv[1:]
    qt_argv = [arg for arg in argv if arg != WORK_PANEL_ARG]
    return work_panel_mode, qt_argv


def _acquire_launcher_instance() -> bool:
    global _instance_mutex_handle
    if os.name != "nt":
        return True

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateMutexW(None, False, WINDOWS_INSTANCE_MUTEX_NAME)
    if not handle:
        print("[launcher-qt][WARN] unable to create the launcher instance mutex.", flush=True)
        return True
    if ctypes.get_last_error() == WINDOWS_ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False

    _instance_mutex_handle = handle
    return True


def _create_launcher_activation_event() -> bool:
    global _instance_activate_event_handle
    if os.name != "nt":
        return False

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.argtypes = (
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    )
    kernel32.CreateEventW.restype = wintypes.HANDLE

    handle = kernel32.CreateEventW(
        None,
        False,
        False,
        WINDOWS_INSTANCE_ACTIVATE_EVENT_NAME,
    )
    if not handle:
        print("[launcher-qt][WARN] unable to create the launcher activation event.", flush=True)
        return False
    _instance_activate_event_handle = handle
    return True


def _signal_existing_launcher_console() -> bool:
    if os.name != "nt":
        return False

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenEventW(
        WINDOWS_EVENT_MODIFY_STATE,
        False,
        WINDOWS_INSTANCE_ACTIVATE_EVENT_NAME,
    )
    if not handle:
        print("[launcher-qt][WARN] existing launcher activation event is unavailable.", flush=True)
        return False
    try:
        if not kernel32.SetEvent(handle):
            print("[launcher-qt][WARN] unable to signal the existing launcher console.", flush=True)
            return False
    finally:
        kernel32.CloseHandle(handle)
    print("[launcher-qt] existing launcher console reveal requested.", flush=True)
    return True


def _consume_launcher_activation_event() -> bool:
    handle = _instance_activate_event_handle
    if os.name != "nt" or not handle:
        return False

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    return kernel32.WaitForSingleObject(handle, 0) == WINDOWS_WAIT_OBJECT_0


def _close_launcher_activation_event() -> None:
    global _instance_activate_event_handle
    handle = _instance_activate_event_handle
    _instance_activate_event_handle = None
    if os.name != "nt" or not handle:
        return

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def _reveal_existing_work_panel(cfg) -> bool:
    from kuro_launcher.utils import http_post_json

    endpoint = f"http://{cfg.pet_control_host}:{cfg.pet_control_port}/command"
    last_error = "pet control server is not ready"
    for _attempt in range(10):
        try:
            result = http_post_json(
                endpoint,
                {"action": "set-briefing-visible", "enabled": True},
                timeout=1.0,
            )
            if result.get("ok", True):
                print("[launcher-qt] existing work panel reveal requested.", flush=True)
                return True
            last_error = str(result.get("message") or result.get("error") or last_error)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)

    print(f"[launcher-qt][WARN] existing work panel reveal failed: {last_error}", flush=True)
    return False


def _activate_existing_launcher(cfg, *, work_panel_mode: bool) -> bool:
    if work_panel_mode:
        # Product entrypoints must never fall back to the legacy Qt console.
        # If the Electron work panel cannot be revealed, fail closed and let
        # the user start a clean instance after the existing owner exits.
        return _reveal_existing_work_panel(cfg)
    return _signal_existing_launcher_console()


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
    work_panel_mode, qt_argv = _consume_work_panel_arg(sys.argv)

    cfg_path = BASE_DIR / "kuro_launcher.settings.yaml"
    print(f"[launcher-qt] start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[launcher-qt] cwd  : {Path.cwd()}")
    print(f"[launcher-qt] here : {BASE_DIR}")
    print(f"[launcher-qt] cfg  : {cfg_path}")

    if not cfg_path.exists():
        print(f"[launcher-qt][ERROR] missing config: {cfg_path}")
        return 2

    try:
        from PySide6.QtCore import QTimer
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
    from kuro_launcher.work_panel_api import WorkPanelControlServer

    cfg = load_config(cfg_path)
    log_dir = build_logs_dir(cfg.logs_dir, "launcher-qt", run_id=None, aggregate_daily=True)
    log_path = setup_runtime_logging(log_dir)
    print(f"[launcher-qt] log  : {log_path}")
    print(f"[launcher-qt] root : {cfg.root}")

    if not _acquire_launcher_instance():
        print("[launcher-qt] an existing launcher instance is already running.", flush=True)
        _activate_existing_launcher(cfg, work_panel_mode=work_panel_mode)
        return 0

    _create_launcher_activation_event()

    app = QApplication(qt_argv)
    app.setApplicationName("Kuro")
    app.setApplicationDisplayName("Kuro Desktop Console")
    app.setOrganizationName("Kuro")

    try:
        print("[launcher-qt] window: constructing", flush=True)
        open_work_panel_on_start = bool(work_panel_mode and cfg.startup_auto_start)
        if work_panel_mode and not open_work_panel_on_start:
            message = "新版工作面板需要 startup_profile.auto_start=true；已停止啟動，不會開啟舊控制台。"
            print(f"[launcher-qt][ERROR] {message}", flush=True)
            QMessageBox.critical(None, "Kuro 工作面板", message)
            _close_launcher_activation_event()
            return 2
        window = KuroQtLauncherWindow(
            cfg,
            open_work_panel_on_start=open_work_panel_on_start,
        )
        print("[launcher-qt] window: constructed", flush=True)
    except Exception as exc:
        print(f"[launcher-qt][ERROR] window construction failed: {exc}", flush=True)
        QMessageBox.critical(None, "Kuro Desktop Console", f"啟動 Qt launcher 失敗：\n{exc}")
        _close_launcher_activation_event()
        return 1

    activation_timer = QTimer(window)
    activation_timer.setInterval(250)

    def reveal_console_if_requested() -> None:
        if not _consume_launcher_activation_event():
            return
        print("[launcher-qt] existing launcher console reveal handled.", flush=True)
        window.showNormal()
        window.raise_()
        window.activateWindow()

    activation_timer.timeout.connect(reveal_console_if_requested)
    activation_timer.start()

    launcher_control = WorkPanelControlServer(
        window.controller,
        host=cfg.launcher_control_host,
        port=cfg.launcher_control_port,
        log=lambda message: window.log_signal.emit(message),
    )
    window.controller.work_panel_control_token = launcher_control.token
    if not launcher_control.start():
        print(
            f"[launcher-qt][WARN] launcher control API unavailable: {launcher_control.last_error}",
            flush=True,
        )
    app.aboutToQuit.connect(launcher_control.stop)
    app.aboutToQuit.connect(_close_launcher_activation_event)

    if open_work_panel_on_start:
        window.hide()
    else:
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
