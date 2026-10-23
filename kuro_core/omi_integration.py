"""OMI observation admission only. Conversation remains the analysis owner."""
from datetime import datetime, timezone
from .assistant_settings import validate_settings
from .hub_integration import observation, source_result
from .contracts import AvailabilityStatus as A
from .work_evidence import WorkEvidenceRead


class OmiIntegration:
    def __init__(self, settings):
        self.settings = settings

    def work(self, now):
        try:
            policy = validate_settings(self.settings.read({})['settings'])['omi']
            reason = ('disabled' if not policy['enabled'] else 'query_budget_zero'
                      if policy['dailyQueryBudget']==0 else 'canonical_cache_consumer_unavailable')
        except (OSError, ValueError, TypeError, KeyError):
            policy=None; reason='settings_unavailable'
        return WorkEvidenceRead((),observation('omi',now,availability=A.MISSING,
            limitations=(reason,'no_refresh_not_verified','quota_ledger_unavailable'),
            details={'policy':policy,'enabled':policy['enabled'] if policy else None,
                'executionAvailable':False,'analysisOwner':'Conversation omi.ask / omi.decision.v4',
                'requiredEnvelope':{'realtime_policy':'cache_only','allow_llm':False,
                    'allow_external_fetch':False,'allow_write':False},
                'queriesUsedToday':None,'idempotencyVerified':False}))

    def read(self, query):
        if query: raise ValueError('OMI does not accept query fields')
        return source_result(self.work(datetime.now(timezone.utc)))
