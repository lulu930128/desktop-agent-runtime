# kuro_launcher/utils.py
# Unified helpers for Kuro Launcher (logs / process / yaml / networking)
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# -------------------------
# Text cleanup
# -------------------------
# ANSI escape sequences (colors etc.)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Control chars except \n and \t
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def strip_ansi_and_ctrl(s: str) -> str:
    """Remove ANSI color codes and control characters; normalize CR to LF-friendly."""
    if not s:
        return s
    s = s.replace("\r", "")          # progress bars, carriage returns
    s = _ANSI_RE.sub("", s)          # colors
    s = _CTRL_RE.sub("", s)          # stray control chars
    return s


def sanitize_ascii(s: str) -> str:
    """Keep only safe printable ASCII (avoid Unicode surprises for env/filenames)."""
    if not s:
        return ""
    out = []
    for ch in s:
        o = ord(ch)
        # printable ASCII excluding DEL
        if 32 <= o < 127:
            out.append(ch)
    return "".join(out).strip()


def load_env_file(path: Path, override: bool = False) -> int:
    """Load simple KEY=VALUE pairs from a local env file without logging secrets."""
    path = Path(path)
    if not path.exists():
        return 0

    loaded = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if not override and key in os.environ:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value
        loaded += 1

    return loaded


def log_ts() -> str:
    """HH:MM:SS (local time)."""
    return datetime.now().strftime("%H:%M:%S")


# -------------------------
# Networking
# -------------------------
def port_is_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def get_listening_pid_windows(port: int) -> Optional[int]:
    """Best-effort: find PID listening on tcp:<port> (Windows only)."""
    if os.name != "nt":
        return None
    try:
        # netstat output:  TCP  127.0.0.1:1188  0.0.0.0:0  LISTENING  1234
        out = subprocess.check_output(["netstat", "-ano"], text=True, encoding="utf-8", errors="ignore")
        needle = f":{int(port)}"
        for line in out.splitlines():
            if "LISTENING" not in line:
                continue
            if needle not in line:
                continue
            parts = line.split()
            if len(parts) >= 5 and parts[-1].isdigit():
                return int(parts[-1])
    except Exception:
        return None
    return None



# -------------------------
# HTTP helpers
# -------------------------
import json
import urllib.request
import urllib.error

def http_post_json(url: str, payload: dict, timeout: float = 5.0) -> dict:
    """
    POST JSON and return parsed JSON dict.
    Designed for bridge healthchecks/debug endpoints.
    Raises exception on HTTP errors / JSON parse errors.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(raw) if raw else {}
    if not isinstance(obj, dict):
        return {"data": obj}
    return obj

# -------------------------
# Process control
# -------------------------
def taskkill_tree(pid: int) -> None:
    """Kill a process tree on Windows (taskkill /T /F). No-op best-effort on other OS."""
    try:
        pid = int(pid)
    except Exception:
        return

    if os.name == "nt":
        # /T = terminate child processes, /F = force
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        # best-effort on *nix
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def conda_exe() -> str:
    """Return conda executable path if available (best-effort)."""
    # Common env var in conda shells
    c = os.environ.get("CONDA_EXE")
    if c and Path(c).exists():
        return c
    # Fallback: look near sys.executable
    try:
        p = Path(sys.executable).resolve()
        # .../envs/<name>/python.exe -> .../Scripts/conda.exe
        cand = p.parent.parent / "Scripts" / ("conda.exe" if os.name == "nt" else "conda")
        if cand.exists():
            return str(cand)
    except Exception:
        pass
    return "conda"


# -------------------------
# YAML + deep merge
# -------------------------
def read_yaml_file(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        # Keep launcher robust: normalize non-dict to empty dict
        return {}
    return data


def write_yaml_file(path: Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge dict b into a (returns new dict; does not mutate inputs)."""
    out: Dict[str, Any] = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)  # type: ignore[arg-type]
        else:
            out[k] = v
    return out


# -------------------------
# Log directory layout (B mode)
# -------------------------
def build_logs_dir(
    logs_root: Optional[Path],
    service: str,
    run_id: Optional[str] = None,
    aggregate_daily: bool = False,
) -> Path:
    """
    Folder layout (user decision: B mode)
      logs_root/<service>/<YYYY>/<M>/<DD>            (aggregate_daily=True)
      logs_root/<service>/<YYYY>/<M>/<DD>/<run_id>   (aggregate_daily=False)

    Month folder: NOT zero-padded (e.g., 2 not 02)
    Day folder:   zero-padded (e.g., 06)
    """
    root = Path(logs_root) if logs_root is not None else (Path.cwd() / "launcher_logs")
    now = datetime.now()
    year_month_dir = f"{now.year}_{now.month}"   # 2026_2
    day_dir = f"{now.day:02d}"          # 06, 15...

    base = root / service / year_month_dir / day_dir

    if aggregate_daily:
        base.mkdir(parents=True, exist_ok=True)
        return base

    if not run_id:
        run_id = now.strftime("%Y-%m-%d_%H-%M-%S")

    p = base / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p
