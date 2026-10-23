"""Existing config owner -> actual Core worker -> HTTP Today; synthetic Hubs only."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import yaml

from kuro_core.core_app import CoreApplication
from kuro_core.hub_integration import HUBS
from kuro_launcher.config import load_config
from test_g2_hub_transport import synthetic_hub
from test_g2_integration_boundaries import LifecycleTests
from test_kuro_core_api_host import TOKEN, request

ROOT=Path(__file__).resolve().parents[1]


class StudyOptInTests(unittest.TestCase):
    def test_reviewed_yaml_opt_in_reaches_worker_and_today_then_stops(self):
        with tempfile.TemporaryDirectory() as tmp, \
                synthetic_hub(service='japanese-study-hub') as jp, \
                synthetic_hub(service='english-study-hub') as en:
            path=Path(tmp)/'fixture.yaml'
            data=yaml.safe_load((ROOT/'docs/config/StudyHubOptIn.yaml').read_text(encoding='utf-8'))
            self.assertTrue(all(not s['enabled'] for s in data['core']['integrations'].values()))
            data['paths']={'ROOT':tmp,'logs_dir':tmp}
            data['core'].update(enabled=True,port=12345)
            for source in HUBS: data['core']['integrations'][source]['enabled']=True
            path.write_text(yaml.safe_dump(data),encoding='utf-8')
            cfg=load_config(path)
            schedule=LifecycleTests().schedule(Path(tmp)/'synthetic.db')
            with patch('kuro_core.core_app.ScheduleCapability',return_value=schedule):
                app=CoreApplication(Path(tmp)/'synthetic.db',port=0,token=TOKEN,
                    instance_id='synthetic-opt-in',hubs=cfg.core_hubs)
            with patch.dict(HUBS,{
                'japanese_study':('japanese-study-hub',jp[0],'SYNTHETIC_NO_TOKEN'),
                'english_study':('english-study-hub',en[0],'SYNTHETIC_NO_TOKEN')}):
                try:
                    app.start()
                    deadline=time.monotonic()+12
                    while time.monotonic()<deadline:
                        if all(app.integrations.readonly_sources[s].snapshot for s in HUBS): break
                        threading.Event().wait(.05)
                    self.assertTrue(all(app.integrations.readonly_sources[s].snapshot for s in HUBS))
                    self.assertEqual((len(jp[3]),len(en[3])),(4,4))
                    code,today=request(app.port,'/v1/today')
                    self.assertEqual(code,200)
                    self.assertEqual({i['source'] for i in today['items']},set(HUBS))
                    self.assertEqual(len(today['items']),2)  # same per-source id deduped, never cross-source
                    self.assertEqual((len(jp[3]),len(en[3])),(4,4))
                    self.assertFalse(schedule.stop_event.is_set())
                finally: app.stop()
            self.assertFalse(app.integration_worker.is_alive())
            self.assertFalse(schedule.worker.is_alive())
            for source in HUBS: app.integrations.readonly_sources[source].tick(threading.Event())
            self.assertEqual((len(jp[3]),len(en[3])),(4,4))
            self.assertFalse((Path(tmp)/'synthetic.db').exists())

    def test_default_opt_out_core_worker_has_zero_hub_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.yaml'
            data=yaml.safe_load((ROOT/'docs/config/StudyHubOptIn.yaml').read_text(encoding='utf-8'))
            data['paths']={'ROOT':tmp,'logs_dir':tmp}
            data['core'].update(enabled=True,port=12345)
            path.write_text(yaml.safe_dump(data),encoding='utf-8')
            cfg=load_config(path)
            schedule=LifecycleTests().schedule(Path(tmp)/'synthetic.db')
            with patch('kuro_core.core_app.ScheduleCapability',return_value=schedule):
                app=CoreApplication(Path(tmp)/'synthetic.db',port=0,token=TOKEN,
                    instance_id='synthetic-opt-out',hubs=cfg.core_hubs)
            with patch('kuro_core.hub_integration.HubClient.get',side_effect=AssertionError('disabled IO')) as get:
                try:
                    app.start(); threading.Event().wait(.1)
                    # Exercise both disabled registrations without waiting for wall-clock ticks.
                    for _ in range(4): app.integrations.background_read(app.integration_stop)
                    code,today=request(app.port,'/v1/today')
                    self.assertEqual(code,200); self.assertTrue(today['complete'])
                    self.assertEqual(today['sourceStates'],[])
                    get.assert_not_called()
                finally: app.stop()
            self.assertFalse(app.integration_worker.is_alive())


if __name__=='__main__': unittest.main()
