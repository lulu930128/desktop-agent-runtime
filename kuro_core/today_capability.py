"""Canonical Today read composition. No store, provider, refresh or persistence."""
from datetime import datetime, timezone

from .integrations import resolve_mail_path
from .mail_work_adapter import read_mail_work, validate_work_max_bytes
from .study_work_adapter import read_study_work
from .today import build_today_view
from .work_contracts import TodayView, timezone_info


class TodayCapability:
    def __init__(self, integrations, *, default_timezone="UTC", mail_work_path=None,
                 mail_work_max_bytes=2097152):
        timezone_info(default_timezone)
        validate_work_max_bytes(mail_work_max_bytes)
        self.timezone = default_timezone
        self.integrations = integrations
        self.mail_work_path = (resolve_mail_path(mail_work_path)
                               if "mail" in integrations.integrations else None)
        if (self.mail_work_path is not None
                and self.mail_work_path == integrations.integrations["mail"].status_path):
            raise ValueError("Mail work_path must differ from status_path")
        self.mail_work_max_bytes = mail_work_max_bytes

    def status(self):
        # Never open handoffs for readiness/status; no Schedule schema dependency.
        return {"contract": TodayView.CONTRACT, "configured": sorted(self.integrations.integrations),
                "timezone": self.timezone}

    def register_routes(self, api):
        api.register("GET", "/v1/today", self.read)

    def read(self, query):
        if query:
            raise ValueError("Today does not accept query fields")
        return self.view(as_of=datetime.now(timezone.utc)).to_dict()

    def view(self, *, as_of):
        evidence, observations = [], []
        for source, integration in sorted(self.integrations.integrations.items()):
            if source == "study":
                result = read_study_work(integration.snapshot_path, received_at=as_of,
                    ttl_seconds=integration.ttl_seconds, max_bytes=integration.max_bytes)
            elif source == "mail":
                result = read_mail_work(self.mail_work_path, integration.status_path, received_at=as_of,
                    ttl_seconds=integration.ttl_seconds, max_bytes=self.mail_work_max_bytes,
                    status_max_bytes=integration.max_bytes)
            else:
                raise ValueError("Today source has no concrete evidence adapter")
            evidence.extend(result.evidence)
            observations.append(result.observation)
        return build_today_view(tuple(evidence), tuple(observations), as_of=as_of,
                                timezone=self.timezone, expected_sources=tuple(self.integrations.integrations))
