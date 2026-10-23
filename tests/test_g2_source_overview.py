"""Source diagnostics do not fabricate Today items or fetch live providers."""
from datetime import timedelta
import unittest
from unittest.mock import patch
from test_g2_integration_boundaries import registry, parts, NOW
from kuro_core.today_capability import TodayCapability


class SourceOverviewTests(unittest.TestCase):
    def test_empty_english_and_disabled_omi_are_visible_without_fake_work(self):
        sources=registry(japanese_study=True,english_study=True)
        for name in ('japanese_study','english_study'):
            sources.readonly_sources[name].snapshot=(parts(name, rows=name=='japanese_study'),NOW)
        with patch('kuro_core.today_capability.datetime') as clock:
            clock.now.return_value=NOW
            result=TodayCapability(sources).read({})
        overview={r['sourceId']:r for r in result['sourceOverview']}
        self.assertEqual(overview['english_study']['availability'],'partial')
        self.assertIn('source_observed_at_missing',overview['english_study']['limitations'])
        self.assertEqual(overview['english_study']['evidenceCount'],0)
        self.assertEqual(overview['english_study']['connection'],'connected')
        self.assertFalse(overview['omi']['enabled'])
        self.assertFalse(overview['omi']['executionAvailable'])
        self.assertIsNone(overview['omi']['receivedAt'])
        self.assertNotIn('omi',{r['integrationId'] for r in result['sourceStates']})
        self.assertEqual({r['source'] for r in result['items']},{'japanese_study'})
        self.assertNotIn('evidence',overview['english_study'])
        for source in sources.readonly_sources.values():
            if hasattr(source,'client'): self.assertEqual(source.client.calls,[])

    def test_missing_auth_and_stale_preserve_quality_not_zero_tasks(self):
        sources=registry(english_study=True)
        source=sources.readonly_sources['english_study']
        # Actual Hub failure fields, no private runtime or HTTP.
        source.error='auth_required'
        result=TodayCapability(sources).read({})
        row=next(r for r in result['sourceOverview'] if r['sourceId']=='english_study')
        self.assertIsNone(row['evidenceCount'])
        self.assertEqual(row['availability'],'auth_required')
        self.assertEqual(result['items'],[])
        source.snapshot=(parts('english_study',rows=False),NOW-timedelta(days=2))
        result=TodayCapability(sources).read({})
        row=next(r for r in result['sourceOverview'] if r['sourceId']=='english_study')
        self.assertEqual(row['freshness'],'stale')


if __name__=='__main__': unittest.main()
