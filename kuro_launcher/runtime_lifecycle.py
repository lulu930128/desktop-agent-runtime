"""Launcher-owned capability state and bounded recovery, independent of the UI."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid


def source_revision(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root / 'launcher_qt.py', *(root / 'kuro_launcher').glob('*.py'),
             *(root / 'Open-LLM-VTuber/src/open_llm_vtuber').rglob('*.py'),
             *(root / 'pet-electron/src').rglob('*.js'),
             *(root / 'pet-electron/renderer-dist/assets').glob('*.js')]
    config = root / 'kuro_launcher.settings.yaml'
    if config.is_file():
        paths.append(config)
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


class RuntimeLifecycle:
    def __init__(self, root: Path, log):
        self.lock = threading.RLock()
        self.root, self.log = root, log
        self.boot_id = uuid.uuid4().hex
        self.revision = source_revision(root)
        self.disk_revision = self.revision
        self.desired_running = False
        self.phase = 'stopped'
        self.reason = ''
        self.attempts = 0
        self.retry_at = 0.0
        self.checked_at = 0.0
        self.voice = {'state': 'unknown', 'reason': '尚未檢查語音服務'}

    def record(self, phase, reason=''):
        self.phase, self.reason = phase, reason
        event = {'event': 'runtime-state', 'boot_id': self.boot_id,
                 'phase': phase, 'reason': reason, 'attempts': self.attempts,
                 'time': time.time()}
        line = '[runtime] ' + json.dumps(event, ensure_ascii=False)
        print(line, flush=True)
        self.log(line)

    def start(self, operation, *, automatic=False):
        if not self.lock.acquire(blocking=False):
            return {'ok': True, 'pending': True, 'mode': 'already-starting'}
        try:
            if automatic and (not self.desired_running or self.attempts >= 2 or time.monotonic() < self.retry_at):
                return {'ok': False, 'skipped': True}
            if not automatic:
                self.desired_running = True
                self.attempts = 0
            else:
                self.attempts += 1
            self.record('starting')
            try:
                result = operation()
            except Exception as exc:
                self.retry_at = time.monotonic() + (15 if self.attempts == 0 else 60)
                self.record('failed', str(exc)[:800])
                raise
            self.record('ready')
            # Do not reset the automatic restart budget on short-lived success.
            return result
        finally:
            self.lock.release()

    def snapshot(self):
        return {'contractVersion': 1, 'pid': os.getpid(), 'bootId': self.boot_id,
                'sourceRevision': self.revision, 'diskRevision': self.disk_revision,
                'restartRequired': self.revision != self.disk_revision,
                'desiredRunning': self.desired_running, 'phase': self.phase,
                'reason': self.reason, 'recoveryAttempts': self.attempts,
                'recoveryExhausted': self.attempts >= 2,
                'checkedAt': self.checked_at, 'voice': dict(self.voice)}
