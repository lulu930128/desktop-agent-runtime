"""Wait for the old Launcher to exit before starting the same checkout."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys


def main():
    parent = int(sys.argv[1])
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, parent)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 60000) != 0:
                raise RuntimeError('Old Launcher did not exit; refusing a duplicate')
        finally:
            kernel.CloseHandle(handle)
    elif ctypes.get_last_error() != 87:  # ERROR_INVALID_PARAMETER: process already exited.
        raise RuntimeError('Cannot verify old Launcher exit')
    root = Path(__file__).resolve().parents[1]
    subprocess.Popen([sys.executable, str(root / 'launcher_qt.py')], cwd=root,
                     creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    main()
