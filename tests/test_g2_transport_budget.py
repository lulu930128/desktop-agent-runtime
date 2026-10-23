"""Worst-case synthetic Hub payload through real Core HTTP and Qt read adapter."""
from datetime import datetime, timezone
import http.client
import json
from types import SimpleNamespace
import unittest

from kuro_core.api_server import CoreApiServer
from kuro_core.hub_integration import HUBS
from kuro_core.today_capability import TodayCapability
from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.qt_controller import QtLauncherController
from test_g2_integration_boundaries import registry, parts
from test_kuro_core_api_host import TOKEN


class TransportBudgetTests(unittest.TestCase):
    def test_two_hubs_full_pages_fit_formal_transport_and_qt_controller(self):
        sources=registry(japanese_study=True,english_study=True)
        now=datetime.now(timezone.utc)
        for source in HUBS:
            payload=parts(source,rows=False)
            if source=='japanese_study': payload[1]['as_of']=now.isoformat()
            for bucket in (1,2):
                payload[bucket].update(count=20,items=[{
                    'item_id':f'{bucket}-{i}', 'title':'長標題'*100, 'meaning_tc':'長中文摘要'*100,
                    'kind':'word','cefr_level':'B1','jlpt_level':'N3'} for i in range(20)])
            sources.readonly_sources[source].snapshot=(payload,now)
        api=CoreApiServer(port=0,token=TOKEN)
        TodayCapability(sources).register_routes(api)
        sources.register_routes(api)
        api.start()
        try:
            TodayCapability(sources).read({})
            runtime=CoreRuntime(SimpleNamespace(core_port=api.port),lambda *args:None)
            runtime.token=TOKEN
            controller=SimpleNamespace(_core_request=runtime.request)
            result=QtLauncherController.read_today(controller)
            self.assertNotIn('sourceObservations',result)
            self.assertFalse(result['complete'])
            self.assertIn('source_limitations',result['limitations'])
            self.assertEqual({i['source'] for i in result['items']},set(HUBS))
            self.assertLess(len(result['items']),80)
            self.assertEqual(result['counts']['total'],len(result['items']))
            ids={i['workId'] for i in result['items']}
            self.assertTrue(all(set(s['itemIds'])<=ids for s in result['sections']))
            for route in ('/v1/today','/v1/observations',
                          '/v1/integrations/japanese_study','/v1/integrations/english_study'):
                connection=http.client.HTTPConnection('127.0.0.1',api.port,timeout=2)
                try:
                    connection.request('GET',route,headers={'Authorization':'Bearer '+TOKEN})
                    response=connection.getresponse(); raw=response.read()
                    self.assertEqual(response.status,200)
                    self.assertLessEqual(len(raw),65536)
                    self.assertEqual(len(raw),int(response.getheader('Content-Length')))
                    data=json.loads(raw)
                    if route=='/v1/observations':
                        for source in data['sources']:
                            if source['sourceId'] in HUBS:
                                self.assertTrue(source['details']['hasMore'])
                                self.assertEqual(source['details']['evidenceTotal'],40)
                    print(f'{route}: {len(raw)} bytes <= 65536')
                finally:
                    connection.close()
                self.assertTrue(runtime.request(route)['ok'])
            for source in HUBS:
                self.assertEqual(len(sources.readonly_sources[source].work(now).evidence),40)
                self.assertEqual(sources.readonly_sources[source].client.calls,[])
        finally:
            api.stop(); sources.close()
        self.assertFalse(api.thread.is_alive())


if __name__=='__main__': unittest.main()
