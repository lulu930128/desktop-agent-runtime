"""Launcher lifecycle owner for one exact Mail poller child; no provider imports."""
import os
import subprocess
import threading

from .mail_environment import clear_mail_handoffs, mail_enabled, mail_handoff_environment
from .services import _env_python
from .utils import windows_hidden_subprocess_kwargs


class MailPollerRuntime:
    def __init__(self, cfg, log):
        self.cfg, self.log = cfg, log
        self.proc = None
        self.lock = threading.RLock()

    def child_environment(self):
        # Always suppress the Electron owner, including when Mail is disabled.
        return {"KURO_MAIL_POLLER_OWNER": "launcher", **mail_handoff_environment(self.cfg)}

    def start(self):
        with self.lock:
            if not mail_enabled(self.cfg):
                return False
            if self.proc and self.proc.poll() is None:
                return True
            env = os.environ.copy()
            clear_mail_handoffs(env)
            env.pop("KURO_MAIL_POLLER_OWNER", None)
            env.update(self.child_environment())
            env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", LOGURU_LEVEL="ERROR")
            script = self.cfg.open_llm_dir / "local_mcp" / "mail_poller.py"
            self.proc = subprocess.Popen([_env_python(self.cfg.env_llm), "-B", str(script)],
                cwd=self.cfg.root, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **windows_hidden_subprocess_kwargs())
            self.log(f"Mail poller child started: pid={self.proc.pid}")
            return True

    def stop(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=4)
            self.proc = None
