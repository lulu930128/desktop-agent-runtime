"""Canonical Today read composition. No store, provider, refresh or persistence."""
from datetime import datetime, timezone
import json

from .integrations import resolve_mail_path
from .mail_work_adapter import read_mail_work, validate_work_max_bytes
from .study_work_adapter import read_study_work
from .today import build_today_view
from .work_contracts import TodayView, timezone_info
from .hub_integration import source_result, bounded_evidence
from .contracts import isoformat_utc


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
        api.register('GET', '/v1/observations', self.read_observations)

    def read(self, query):
        if query:
            raise ValueError("Today does not accept query fields")
        now = datetime.now(timezone.utc)
        all_results = self._results(now, include_disabled=True)
        results = [r for r in all_results if r.observation.details.get('enabled') is not False]
        overview = []
        for result in all_results:
            o = result.observation
            overview.append({'sourceId': o.integration_id, 'enabled': o.details.get('enabled', True),
                'availability': o.availability.value, 'connection': o.connection.value,
                'freshness': o.effective_freshness(as_of=now).value,
                'observedAt': isoformat_utc(o.observed_at),
                'receivedAt': (o.details.get('fetchedAt') if o.integration_id in ('japanese_study', 'english_study')
                               else isoformat_utc(o.received_at) if o.observed_at is not None else None),
                'limitations': list(o.limitations),
                'evidenceCount': len(result.evidence) if o.availability.value in ('available', 'partial') else None,
                'executionAvailable': o.details.get('executionAvailable')})
        # Preserve TodayView's wire contract; detailed evidence belongs to observations.
        # Per-source budgets preserve coverage, and include the real API envelope/UTF-8.
        budget = 12000
        while True:
            response = self._view([bounded_evidence(r, budget) for r in results], now).to_dict()
            # Lean source diagnostics, including disabled/blocked integrations; no Evidence duplication.
            response['sourceOverview'] = overview
            if len(json.dumps({'ok':True, **response},ensure_ascii=False,allow_nan=False).encode('utf-8'))<=64000:
                return response
            if budget == 0: raise ValueError('Today source metadata exceeds transport budget')
            budget //= 2

    def read_observations(self, query):
        if query: raise ValueError('Observations do not accept query fields')
        now = datetime.now(timezone.utc)
        return {'contract':'kuro.core.observations.v1', 'sources':[
            source_result(r, as_of=now) for r in self._results(now, include_disabled=True)]}

    def view(self, *, as_of):
        return self._view(self._results(as_of), as_of)

    def _results(self, as_of, *, include_disabled=False):
        results = []
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
            results.append(result)
        for source in self.integrations.readonly_sources.values():
            result = source.work(as_of)
            if include_disabled or result.observation.details.get('enabled') is not False:
                results.append(result)
        return results

    def _view(self, results, as_of):
        return build_today_view(tuple(e for r in results for e in r.evidence),
            tuple(r.observation for r in results), as_of=as_of, timezone=self.timezone,
            expected_sources=tuple(r.observation.integration_id for r in results))
