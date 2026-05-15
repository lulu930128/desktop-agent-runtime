import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, TextIO

from .utils import taskkill_tree, build_logs_dir, strip_ansi_and_ctrl


def _win_creationflags() -> int:
    """Windows creationflags to avoid popping a console window for child processes."""
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def _no_color_env(base: Dict[str, str]) -> Dict[str, str]:
    """Best-effort to disable colored logs / rich progress bars."""
    env = dict(base)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("LOGURU_COLORIZE", "0")
    env.setdefault("RICH_DISABLE", "1")
    env.setdefault("CLICOLOR", "0")
    env.setdefault("FORCE_COLOR", "0")
    return env


@dataclass
class ManagedProc:
    name: str
    popen: subprocess.Popen
    out_path: Path
    err_path: Path
    combined_path: Path

    def stop(self):
        if self.popen and self.popen.poll() is None:
            taskkill_tree(self.popen.pid)


def _pump_stream(stream, out_f: TextIO, combined_f: TextIO, prefix: str):
    """Read lines from stream and write sanitized lines to out_f and combined_f."""
    try:
        for raw in iter(stream.readline, ""):
            if raw == "":
                break
            line = strip_ansi_and_ctrl(raw)
            if not line:
                continue
            try:
                out_f.write(line)
                out_f.flush()
            except Exception:
                pass
            try:
                combined_f.write(f"[{prefix}] {line}")
                combined_f.flush()
            except Exception:
                pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def spawn_process(
    name: str,
    cmd: List[str],
    cwd: Path,
    logs_root: Path,
    env: Optional[Dict[str, str]] = None,
    *,
    run_id: Optional[str] = None,
    aggregate_daily: bool = False,
) -> ManagedProc:
    """Spawn a child process and tee stdout/stderr into out/err/combined logs.

    Logging dir:
      - aggregate_daily=True  => logs_root/name/YYYY/MM/DD
      - aggregate_daily=False => logs_root/name/YYYY/MM/DD/run_id (run_id required)
    """
    log_dir = build_logs_dir(Path(logs_root), name, run_id=run_id, aggregate_daily=aggregate_daily)
    log_dir.mkdir(parents=True, exist_ok=True)

    out_path = log_dir / f"{name}.out.log"
    err_path = log_dir / f"{name}.err.log"
    combined_path = log_dir / f"{name}.combined.log"

    out_f = out_path.open("a", encoding="utf-8", buffering=1, errors="replace")
    err_f = err_path.open("a", encoding="utf-8", buffering=1, errors="replace")
    combined_f = combined_path.open("a", encoding="utf-8", buffering=1, errors="replace")

    env_final = _no_color_env(env or os.environ.copy())

    p = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env_final,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        universal_newlines=True,
        creationflags=_win_creationflags(),
    )

    if p.stdout is not None:
        threading.Thread(target=_pump_stream, args=(p.stdout, out_f, combined_f, "STDOUT"), daemon=True).start()
    if p.stderr is not None:
        threading.Thread(target=_pump_stream, args=(p.stderr, err_f, combined_f, "STDERR"), daemon=True).start()

    return ManagedProc(name=name, popen=p, out_path=out_path, err_path=err_path, combined_path=combined_path)
