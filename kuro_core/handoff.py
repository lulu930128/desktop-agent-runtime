"""Domain-neutral bounded JSON handoff reader; never includes paths in errors."""
import errno
import json
import time
from pathlib import Path


class HandoffReadError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_json_handoff(file_path, *, max_bytes):
    path = Path(file_path)
    deadline = time.monotonic() + 0.5
    while True:
        try:
            if path.stat().st_size > max_bytes:
                raise HandoffReadError("too_large")
            with path.open("rb") as handle:
                raw = handle.read(max_bytes + 1)
            break
        except FileNotFoundError:
            raise HandoffReadError("missing") from None
        except OSError as exc:
            retryable = (exc.errno in (errno.EACCES, errno.EBUSY, errno.EPERM)
                         or getattr(exc, "winerror", None) in (5, 32, 33))
            remaining = deadline - time.monotonic()
            if not retryable or remaining <= 0:
                raise HandoffReadError("read_failed") from None
            time.sleep(min(0.01, remaining))
    if len(raw) > max_bytes:
        raise HandoffReadError("too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HandoffReadError("invalid_utf8") from None
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        raise HandoffReadError("invalid_json") from None
    if not isinstance(payload, dict):
        raise HandoffReadError("invalid_shape")
    return payload
