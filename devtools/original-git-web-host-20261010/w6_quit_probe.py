"""Bounded synthetic Windows Qt WM_QUIT probe; never posts to an existing process."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
FORMAL = HERE.parents[1] / 'envs/kuro-llm310/python.exe'
USER = ctypes.WinDLL('user32', use_last_error=True)
KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
USER.EnumWindows.argtypes = [CALLBACK, wintypes.LPARAM]
USER.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER.GetWindowThreadProcessId.restype = wintypes.DWORD
USER.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER.IsWindowVisible.argtypes = [wintypes.HWND]
USER.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
USER.PostThreadMessageW.restype = wintypes.BOOL
KERNEL.GetCurrentThreadId.restype = wintypes.DWORD


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def windows(pid):
    rows = []
    @CALLBACK
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        thread = USER.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title, kind = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(256)
            USER.GetWindowTextW(hwnd, title, len(title))
            USER.GetClassNameW(hwnd, kind, len(kind))
            rows.append(dict(hwnd=int(hwnd), pid=pid, thread=thread,
                             title=title.value, windowClass=kind.value,
                             visible=bool(USER.IsWindowVisible(hwnd))))
        return True
    ctypes.set_last_error(0)
    if not USER.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return rows


def child(output):
    from PySide6.QtCore import QTimer, qVersion
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if app.platformName() != 'windows':
        raise RuntimeError('Native Windows platform required')
    window = QMainWindow()
    window.setWindowTitle('SYNTHETIC W6 WM_QUIT lifecycle probe')
    window.resize(420, 100)
    window.show()
    events = []
    timed_out = False

    def cleanup():
        events.append('aboutToQuit')
        # Only a synthetic callback, no production controller or Core is imported.
        events.append('synthetic_controller_close_called')

    def ready():
        write(output / 'Ready.json', dict(pid=os.getpid(), thread=KERNEL.GetCurrentThreadId(),
              hwnd=int(window.winId()), executable=sys.executable, qt=qVersion(),
              platform=app.platformName(), utc=datetime.now(timezone.utc).isoformat()))

    def watchdog():
        nonlocal timed_out
        timed_out = True
        app.quit()

    app.aboutToQuit.connect(cleanup)
    QTimer.singleShot(150, ready)
    QTimer.singleShot(6000, watchdog)
    code = app.exec()
    events.append('exec_returned')
    write(output / 'ChildResult.json', dict(events=events, execExit=code,
          watchdogFired=timed_out, productionControllerInvoked=False,
          productionAdoption=False))
    return 0 if not timed_out and events == ['aboutToQuit', 'synthetic_controller_close_called', 'exec_returned'] else 2


def run(output):
    if Path(sys.executable).resolve() != FORMAL.resolve():
        raise RuntimeError('Exact formal interpreter required')
    if any(os.environ.get(k) for k in ('QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH')):
        raise RuntimeError('No Qt overrides allowed')
    command = [str(FORMAL), '-I', '-B', str(Path(__file__).resolve()), '--child', '--output', str(output)]
    started = time.monotonic()
    with (output / 'child.stdout.log').open('x') as out, (output / 'child.stderr.log').open('x') as err:
        process = subprocess.Popen(command, cwd=HERE.parents[1], stdout=out, stderr=err,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        receipt = dict(argv=command, cwd=str(HERE.parents[1]), childPid=process.pid,
                       actualKuroMessageSent=False, postAttempted=False)
        try:
            while not (output / 'Ready.json').exists() and process.poll() is None and time.monotonic()-started < 4:
                time.sleep(.05)
            if not (output / 'Ready.json').exists():
                raise RuntimeError('Synthetic native child did not become ready')
            ready = json.loads((output / 'Ready.json').read_text())
            observed = windows(process.pid)
            receipt['windows'] = observed
            matched = [w for w in observed if w['hwnd'] == ready['hwnd'] and w['thread'] == ready['thread']]
            if process.poll() is not None or ready['pid'] != process.pid or len(matched) != 1:
                raise RuntimeError('Synthetic process/window/thread binding failed')
            # The only post in this program is to the newly owned child, never --survey-pid.
            receipt['postAttempted'] = True
            receipt['postAccepted'] = bool(USER.PostThreadMessageW(ready['thread'], 0x12, 0, 0))
            receipt['postWinError'] = ctypes.get_last_error() if not receipt['postAccepted'] else 0
            receipt['exit'] = process.wait(timeout=8)
            result = json.loads((output / 'ChildResult.json').read_text())
            receipt['result'] = result
            receipt['status'] = 'SYNTHETIC_CALLBACK_PASS' if receipt['postAccepted'] and receipt['exit'] == 0 else 'BLOCKED'
        except Exception as exc:
            receipt.update(status='BLOCKED', errorType=type(exc).__name__, error=str(exc))
        finally:
            if process.poll() is None:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.terminate()  # Only our disposable child handle; never Kuro/Core.
                    process.wait(timeout=3)
                    receipt['syntheticChildTerminated'] = True
            receipt['exit'] = process.returncode
            receipt['elapsedSeconds'] = round(time.monotonic()-started, 3)
            write(output / 'Receipt.json', receipt)
    print(json.dumps(receipt))
    return 0 if receipt['status'] == 'SYNTHETIC_CALLBACK_PASS' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--survey-pid', type=int)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE / '.runtime'):
        parser.error('Task-local output required')
    if args.survey_pid:
        result = dict(pid=args.survey_pid, operation='READ_ONLY_ENUM_WINDOWS', actualKuroMessageSent=False)
        try:
            result.update(windows=windows(args.survey_pid), status='OBSERVED')
        except OSError as exc:
            result.update(status='BLOCKED', windows=[], winError=exc.winerror, errorType=type(exc).__name__)
        write(output, result)
        print(json.dumps(result))
        return 0 if result['status'] == 'OBSERVED' else 2
    if args.child:
        return child(output)
    output.mkdir(parents=True, exist_ok=False)
    return run(output)


if __name__ == '__main__':
    raise SystemExit(main())
