"""Synthetic G2 review regressions: no production ports, DB, Hub or provider IO."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from kuro_core.assistant_settings import DEFAULTS
from kuro_core.core_app import CoreApplication
from kuro_core.hub_integration import HUBS, PATHS, HubIntegration, HubReadError, project_hub, source_result
from kuro_core.integrations import IntegrationRegistry
from kuro_core.omi_integration import OmiIntegration
from kuro_core.schedule_api import ScheduleCapability
from kuro_core.today_capability import TodayCapability
from test_kuro_core_api_host import TOKEN, request

NOW = datetime(2026, 10, 23, 1, tzinfo=timezone.utc)


def parts(source, *, rows=True):
    item = {'item_id': 'same-id', 'title': 'Synthetic item', 'kind': 'word',
            'meaning_tc': 'Synthetic meaning'}
    if source == 'english_study':
        item.update(lemma='sample', cefr_level='B1')
    else:
        item.update(jlpt_level='N3', updated_at=NOW.isoformat())
    due = {'ok': True, 'count': int(rows), 'items': [item] if rows else []}
    if source == 'japanese_study': due['as_of'] = NOW.isoformat()
    count = {'total':42, 'by_kind':{'word':42}} if source=='japanese_study' else 42
    return [{'ok': True, 'summary': {'items': count}}, due,
            {'ok': True, 'count': 0, 'items': []}]


class Client:
    def __init__(self, error=None):
        self.calls = []
        self.error = error
        self.closed = False
        self.entered = threading.Event()
        self.release = threading.Event()

    def get(self, source, path, stop):
        self.calls.append((source, path))
        self.entered.set()
        if self.error == 'blocking':
            self.release.wait(8)
            raise HubReadError('timeout')
        if self.error: raise self.error
        if path == PATHS[0]: return {'ok': True, 'service': HUBS[source][0]}
        return copy.deepcopy(parts(source)[PATHS.index(path)-1])

    def close(self):
        self.closed = True
        self.release.set()


def registry(**enabled):
    result = IntegrationRegistry(hubs={k: {'enabled': v} for k, v in enabled.items()})
    for source in result.readonly_sources.values(): source.client = Client()
    settings = Mock()
    settings.read.return_value = {'settings': copy.deepcopy(DEFAULTS)}
    result.readonly_sources['omi'] = OmiIntegration(settings)
    return result


class ProjectionTests(unittest.TestCase):
    def test_receipt_is_snapshot_time_while_projection_and_staleness_advance(self):
        first = project_hub('japanese_study', parts('japanese_study'), NOW, NOW, 60)
        later = NOW + timedelta(minutes=2)
        second = project_hub('japanese_study', parts('japanese_study'), NOW, later, 60)
        wire = source_result(second, as_of=later)
        self.assertEqual(first.observation.received_at, second.observation.received_at)
        self.assertEqual(second.observation.received_at, NOW)
        self.assertEqual(wire['receivedAt'], wire['details']['fetchedAt'])
        self.assertNotEqual(wire['receivedAt'], wire['projectedAt'])
        self.assertEqual(wire['freshness'], 'stale')
        self.assertEqual(first.evidence[0].evidence_id, second.evidence[0].evidence_id)
        self.assertEqual(second.evidence[0].received_at, NOW)

    def test_independent_sources_preserve_missing_time_and_language_schema(self):
        jp = project_hub('japanese_study', parts('japanese_study'), NOW, NOW, 60)
        en = project_hub('english_study', parts('english_study'), NOW, NOW, 60)
        self.assertNotEqual(jp.evidence[0].dedup_key, en.evidence[0].dedup_key)
        self.assertEqual(en.evidence[0].metadata['cefrLevel'], 'B1')
        self.assertNotIn('jlptLevel', en.evidence[0].metadata)
        self.assertIsNone(en.observation.observed_at)
        self.assertEqual(en.observation.declared_freshness.value, 'unknown')
        self.assertNotIn('due_reviews', en.observation.details['metrics'])
        self.assertEqual(project_hub('english_study', parts('english_study', rows=False),
                                    NOW, NOW, 60).evidence, ())

    def test_disabled_sources_do_not_reduce_today_quality_or_issue_reads(self):
        sources = registry()
        today = TodayCapability(sources)
        for _ in range(8): sources.background_read(threading.Event())
        view = today.view(as_of=NOW)
        self.assertTrue(view.complete)
        self.assertEqual(view.source_states, ())
        self.assertEqual(view.limitations, ())
        self.assertEqual(view.items, ())
        observations = today.read_observations({})['sources']
        self.assertEqual({o['sourceId'] for o in observations}, {*HUBS, 'omi'})
        self.assertTrue(all('disabled' in o['limitations'] for o in observations))
        self.assertTrue(all(o['availability'] == 'missing' for o in observations))
        self.assertTrue(all(not sources.readonly_sources[s].client.calls for s in HUBS))

    def test_only_english_enabled_is_expected_and_can_reach_today(self):
        sources = registry(english_study=True)
        for _ in range(8): sources.background_read(threading.Event())
        view = TodayCapability(sources).view(as_of=datetime.now(timezone.utc))
        self.assertEqual([s.integration_id for s in view.source_states], ['english_study'])
        self.assertEqual(len(view.items), 1)
        self.assertFalse(sources.readonly_sources['japanese_study'].client.calls)
        self.assertEqual(len(sources.readonly_sources['english_study'].client.calls), 4)

    def test_enabled_healthy_source_complete_despite_disabled_other_sources(self):
        sources = registry(japanese_study=True)
        sources.readonly_sources['japanese_study'].snapshot = (parts('japanese_study', rows=False), NOW)
        view = TodayCapability(sources).view(as_of=NOW)
        self.assertTrue(view.complete)
        self.assertEqual([s.integration_id for s in view.source_states], ['japanese_study'])

    def test_other_enabled_source_still_participates_in_today_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = IntegrationRegistry(hubs={'english_study': {'enabled': True}},
                mail_enabled=True, mail_status_path=Path(tmp)/'missing-status.json')
            view = TodayCapability(sources, mail_work_path=Path(tmp)/'missing-work.json').view(as_of=NOW)
            self.assertEqual({s.integration_id for s in view.source_states}, {'english_study', 'mail'})
            self.assertFalse(view.complete)
            self.assertEqual(view.items, ())

    def test_omi_requested_but_unavailable_is_expected_without_execution(self):
        sources = registry()
        omi = sources.readonly_sources['omi']
        omi.settings.read.return_value['settings']['omi']['enabled'] = True
        view = TodayCapability(sources).view(as_of=NOW)
        self.assertEqual([s.integration_id for s in view.source_states], ['omi'])
        self.assertFalse(view.complete)
        self.assertEqual(view.items, ())
        status = omi.read({})
        self.assertFalse(status['details']['executionAvailable'])
        self.assertIn('canonical_cache_consumer_unavailable', status['limitations'])

    def test_auth_failure_retains_original_receipt_and_stop_has_zero_io(self):
        hub = HubIntegration('japanese_study', {'enabled': True}, Client(HubReadError('auth_required')))
        hub.snapshot = (parts('japanese_study'), NOW)
        hub.tick(threading.Event())
        failed = hub.work(NOW + timedelta(minutes=20))
        self.assertEqual(failed.observation.availability.value, 'auth_required')
        self.assertEqual(failed.observation.received_at, NOW)
        self.assertEqual(failed.observation.declared_freshness.value, 'stale')
        stop = threading.Event(); stop.set()
        hub.next_read = 0
        hub.tick(stop)
        hub.close(); hub.tick(threading.Event())
        self.assertEqual(len(hub.client.calls), 1)


class JapaneseSummaryTests(unittest.TestCase):
    def test_canonical_nested_total_can_be_available(self):
        result = project_hub('japanese_study', parts('japanese_study', rows=False), NOW, NOW, 60)
        self.assertEqual(result.observation.details['metrics']['items'], 42)
        self.assertEqual(result.observation.availability.value, 'available')
        self.assertNotIn('summary_items_invalid', result.observation.limitations)
        self.assertEqual(result.evidence, ())

    def test_malformed_total_is_partial_without_inventing_zero(self):
        for value in ({}, {'total':None}, {'total':True}, {'total':-1},
                      {'total':'4'}, {'total':1.5}, {'total':10000001}, 42):
            payload = parts('japanese_study', rows=False)
            payload[0]['summary']['items'] = value
            result = project_hub('japanese_study', payload, NOW, NOW, 60)
            self.assertEqual(result.observation.availability.value, 'partial')
            self.assertIn('summary_items_invalid', result.observation.limitations)
            self.assertNotIn('items', result.observation.details['metrics'])

    def test_english_scalar_contract_stays_independent(self):
        payload = parts('english_study', rows=False)
        result = project_hub('english_study', payload, NOW, NOW, 60)
        self.assertEqual(result.observation.details['metrics']['items'], 42)
        payload[0]['summary']['items'] = {'total':42}
        invalid = project_hub('english_study', payload, NOW, NOW, 60)
        self.assertIn('summary_items_invalid', invalid.observation.limitations)
        self.assertNotIn('items', invalid.observation.details['metrics'])

    def test_missing_is_distinct_from_valid_zero(self):
        payload = parts('japanese_study', rows=False)
        del payload[0]['summary']['items']
        result = project_hub('japanese_study', payload, NOW, NOW, 60)
        self.assertNotIn('items', result.observation.details['metrics'])
        payload[0]['summary']['items'] = {'total':0,'by_kind':{}}
        zero = project_hub('japanese_study', payload, NOW, NOW, 60)
        self.assertEqual(zero.observation.details['metrics']['items'], 0)


class LifecycleTests(unittest.TestCase):
    def schedule(self, path):
        # Exercise the real Schedule loop/lifecycle with synthetic store/notifications.
        schedule = ScheduleCapability.__new__(ScheduleCapability)
        schedule.store = Mock(path=path)
        schedule.store.advance.return_value = {'complete': True}
        schedule.notifications = Mock()
        schedule.stop_event = threading.Event()
        schedule.worker = None
        schedule._lease = None
        schedule.timezone = 'UTC'
        schedule.materialization = schedule.notification_status = 'pending'
        return schedule

    def test_timeout_and_permission_failure_cannot_stop_or_block_schedule(self):
        for failure in ('blocking', PermissionError('synthetic denial')):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as tmp:
                schedule = self.schedule(Path(tmp)/'synthetic.db')
                twice = threading.Event()
                schedule.notifications.tick.side_effect = lambda: (
                    twice.set() if schedule.notifications.tick.call_count >= 2 else None)
                with patch('kuro_core.core_app.ScheduleCapability', return_value=schedule):
                    app = CoreApplication(Path(tmp)/'synthetic.db', port=0, token=TOKEN,
                        instance_id='synthetic', hubs={'japanese_study': {'enabled': True}})
                client = Client(failure)
                hub = app.integrations.readonly_sources['japanese_study']
                hub.client = client
                try:
                    app.start()
                    self.assertTrue(client.entered.wait(2))
                    self.assertTrue(twice.wait(6), 'Schedule stalled behind Hub IO')
                    self.assertFalse(schedule.stop_event.is_set())
                    self.assertTrue(schedule.worker.is_alive())
                    self.assertFalse(hasattr(schedule, 'background_read'))
                    if isinstance(failure, PermissionError):
                        self.assertTrue(hub.closed)
                        self.assertIn('permission_denied', hub.work(NOW).observation.limitations)
                        self.assertEqual(len(client.calls), 1)
                finally:
                    app.stop()
                self.assertFalse(app.integration_worker.is_alive())
                self.assertFalse(schedule.worker.is_alive())
                self.assertFalse(app.api.thread.is_alive())
                self.assertTrue(client.closed)
                self.assertFalse((Path(tmp)/'synthetic.db').exists())

    def test_real_core_get_routes_use_snapshots_without_hub_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            schedule = self.schedule(Path(tmp)/'synthetic.db')
            with patch('kuro_core.core_app.ScheduleCapability', return_value=schedule):
                app = CoreApplication(Path(tmp)/'synthetic.db', port=0, token=TOKEN,
                    instance_id='synthetic', hubs={s: {'enabled': True} for s in HUBS})
            for source in HUBS:
                hub = app.integrations.readonly_sources[source]
                hub.client = Client()
                for _ in range(4): hub.tick(threading.Event())
            app.api.start()
            try:
                with patch('kuro_core.hub_integration.HubClient.get', side_effect=AssertionError('GET performed HTTP')):
                    for hub in app.integrations.readonly_sources.values():
                        if isinstance(hub, HubIntegration): hub.client.get = Mock(side_effect=AssertionError('GET fetched Hub'))
                    code, response = request(app.port, '/v1/today')
                    self.assertEqual(code, 200)
                    self.assertEqual(len(response['items']), 2)
                    self.assertEqual({s['integrationId'] for s in response['sourceStates']}, set(HUBS))
                    for route in ('/v1/observations', '/v1/integrations/japanese_study',
                                  '/v1/integrations/english_study', '/v1/integrations/omi'):
                        self.assertEqual(request(app.port, route)[0], 200)
                    self.assertTrue(all(not app.integrations.readonly_sources[s].client.get.called for s in HUBS))
            finally:
                app.stop()


if __name__ == '__main__':
    unittest.main()
