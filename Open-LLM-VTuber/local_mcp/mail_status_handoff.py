"""Private status writer for explicit refresh only; never imports Gmail or Core."""
import errno
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 65536
COUNT_FIELDS = {
    "resultSizeEstimate": "resultEstimate", "fetched": "fetchedCount",
    "unread": "unreadCount", "requiredEvents": "requiredEventCount",
    "highPriority": "highPriorityCount", "mediumPriority": "mediumPriorityCount",
    "muted": "mutedCount", "ordinary": "ordinaryCount", "gmailImportant": "gmailImportantCount",
}
PRIVACY_KEYS = ("bodyFetched", "attachmentsFetched", "mailboxModified")


class MailStatusWriteError(Exception):
    """Only a fixed diagnostic may cross the tool/poller boundary."""


def attempt_time():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _timestamp(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("Invalid status timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Status timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _private_mode(path):
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Best effort on platforms that do not implement POSIX modes.


@contextmanager
def _commit_lock(path, timeout=2.0):
    # OS-owned lock releases on process exit. Never unlink the lock inode: that
    # would allow waiters and a new writer to lock different files simultaneously.
    with path.open("a+b") as handle:
        _private_mode(path)
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise MailStatusWriteError("mail_status_lock_timeout") from None
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _previous(path):
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return {}
    if len(raw) > MAX_BYTES:
        raise ValueError("Oversize previous status")
    value = json.loads(raw.decode("utf-8"))
    if (not isinstance(value, dict) or type(value.get("schemaVersion")) is not int
            or value.get("schemaVersion") != 1 or value.get("source") != "gmail_briefing"):
        raise ValueError("Invalid previous status")
    return value


def _safe_success(timestamp, counts, privacy):
    stamp = _timestamp(timestamp).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if not isinstance(counts, dict) or not isinstance(privacy, dict):
        raise ValueError("Missing success metrics")
    if any(type(counts.get(key)) is not int or not 0 <= counts[key] <= 1_000_000 for key in COUNT_FIELDS):
        raise ValueError("Invalid success counts")
    if (any(type(privacy.get(key)) is not bool for key in PRIVACY_KEYS)
            or privacy["attachmentsFetched"] or privacy["mailboxModified"]):
        raise ValueError("Invalid privacy evidence")
    return stamp, {key: counts[key] for key in COUNT_FIELDS}, {key: privacy[key] for key in PRIVACY_KEYS}


def _atomic_replace(source, target, timeout=0.5):
    """Allow short reader sharing conflicts without ever removing the target."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            retryable = (exc.errno in (errno.EACCES, errno.EBUSY, errno.EPERM)
                         or getattr(exc, "winerror", None) in (5, 32, 33))
            remaining = deadline - time.monotonic()
            if not retryable or remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))


def write_status(file_path, *, private_root, attempt_at, snapshot=None, error_type="provider_error"):
    """Serialize compare+replace across processes; later-started attempts win.

    Missing env is handled by the caller (disabled). Invalid configured paths,
    prior evidence, and local IO failures are surfaced, never silently reset.
    """
    temp_path = None
    try:
        path = Path(file_path)
        root = Path(private_root).resolve()
        if not path.is_absolute():
            raise ValueError("Status path must be absolute")
        path = path.resolve()
        path.relative_to(root)
        if path == root:
            raise ValueError("Status path must be a private file")
        attempt = _timestamp(attempt_at)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _commit_lock(path.with_name(path.name + ".lock")):
            try:
                previous = _previous(path)
            except (ValueError, RecursionError):
                # A trustworthy fresh provider success may repair a corrupted
                # local handoff. A failed provider attempt cannot safely erase
                # or replace unreadable prior evidence.
                if snapshot is None:
                    raise
                previous = {}
            if previous and _timestamp(previous.get("lastAttemptAt")) >= attempt:
                return "superseded"
            success_at, counts, privacy = "", {}, {}
            if snapshot is not None:
                mail = snapshot["mail"]
                success_at, counts, privacy = _safe_success(
                    snapshot.get("updatedAt"),
                    {key: mail.get(source) for key, source in COUNT_FIELDS.items()},
                    mail.get("privacy"))
            elif previous.get("lastSuccessAt"):
                success_at, counts, privacy = _safe_success(
                    previous["lastSuccessAt"], previous.get("counts"), previous.get("privacy"))
            payload = {"schemaVersion": 1, "source": "gmail_briefing",
                       "lastAttemptAt": attempt.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                       "lastAttemptOk": snapshot is not None, "lastSuccessAt": success_at,
                       "counts": counts, "privacy": privacy,
                       "errorType": "" if snapshot is not None else (
                           "auth_required" if error_type == "auth_required" else "provider_error")}
            raw = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(raw) > MAX_BYTES:
                raise ValueError("Status too large")
            fd, name = tempfile.mkstemp(prefix=".mail-status-", suffix=".tmp", dir=path.parent)
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as handle:
                _private_mode(temp_path)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            _atomic_replace(temp_path, path)
            temp_path = None
            _private_mode(path)
            return "written"
    except MailStatusWriteError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise MailStatusWriteError("mail_status_write_failed") from None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                raise MailStatusWriteError("mail_status_temp_cleanup_failed") from None
