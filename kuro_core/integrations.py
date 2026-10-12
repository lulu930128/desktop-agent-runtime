"""Read-only integration registry. Provider projection stays in its adapter."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from .mail_adapter import build_mail_status, validate_mail_limits

from .study_adapter import (
    DEFAULT_MAX_SNAPSHOT_BYTES, MAX_SNAPSHOT_BYTES, MAX_TTL_SECONDS, build_study_status,
)


def validate_study_limits(ttl_seconds, max_bytes):
    for name, value, maximum in (("ttl_seconds", ttl_seconds, MAX_TTL_SECONDS),
                                 ("max_bytes", max_bytes, MAX_SNAPSHOT_BYTES)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"Study {name} must be an integer between 1 and {maximum}")


def resolve_study_path(value):
    """Validate configuration without requiring an existing handoff file."""
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError("Enabled Study requires an explicit snapshot_path")
    text = str(value).strip()
    if "\x00" in text or "${" in text or ("%" in text and text.count("%") >= 2):
        raise ValueError("Study snapshot_path must be a resolved path")
    try:
        path = Path(text)
        if not path.is_absolute():
            raise ValueError("Study snapshot_path must be absolute")
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("Study snapshot_path must be a resolvable absolute path") from exc


@dataclass(frozen=True)
class StudyIntegration:
    snapshot_path: Path
    ttl_seconds: int = 3600
    max_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES

    def __post_init__(self):
        validate_study_limits(self.ttl_seconds, self.max_bytes)
        object.__setattr__(self, "snapshot_path", resolve_study_path(self.snapshot_path))

    def read(self, query):
        if query:
            raise ValueError("Study does not accept query fields")
        return build_study_status(self.snapshot_path, as_of=datetime.now(timezone.utc),
                                  ttl_seconds=self.ttl_seconds, max_bytes=self.max_bytes)


def resolve_mail_path(value):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError("Enabled Mail requires an explicit status_path")
    text = str(value).strip()
    if "\x00" in text or "${" in text or ("%" in text and text.count("%") >= 2):
        raise ValueError("Mail status_path must be resolved")
    path = Path(text)
    if not path.is_absolute():
        raise ValueError("Mail status_path must be absolute")
    return path.resolve()


@dataclass(frozen=True)
class MailIntegration:
    status_path: Path
    ttl_seconds: int = 1800
    max_bytes: int = 65536

    def __post_init__(self):
        validate_mail_limits(self.ttl_seconds, self.max_bytes)
        object.__setattr__(self, "status_path", resolve_mail_path(self.status_path))

    def read(self, query):
        if query:
            raise ValueError("Mail does not accept query fields")
        return build_mail_status(self.status_path, as_of=datetime.now(timezone.utc),
                                 ttl_seconds=self.ttl_seconds, max_bytes=self.max_bytes)


class IntegrationRegistry:
    def __init__(self, *, study_enabled=False, study_snapshot_path=None,
                 study_ttl_seconds=3600, study_max_bytes=DEFAULT_MAX_SNAPSHOT_BYTES,
                 mail_enabled=False, mail_status_path=None, mail_ttl_seconds=1800, mail_max_bytes=65536):
        validate_study_limits(study_ttl_seconds, study_max_bytes)
        validate_mail_limits(mail_ttl_seconds, mail_max_bytes)
        self.integrations = {}
        if mail_enabled:
            self.integrations["mail"] = MailIntegration(mail_status_path, mail_ttl_seconds, mail_max_bytes)
        if study_enabled:
            self.integrations["study"] = StudyIntegration(
                resolve_study_path(study_snapshot_path), study_ttl_seconds, study_max_bytes)

    def register_routes(self, api):
        for name, integration in self.integrations.items():
            api.register("GET", f"/v1/integrations/{name}", integration.read)

    def status(self):
        # Configuration only: startup/readiness never reads a private handoff.
        return {"contract": "kuro.core.integrations.v1", "configured": sorted(self.integrations)}
