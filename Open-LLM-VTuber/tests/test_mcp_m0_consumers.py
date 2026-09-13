"""Run actual consumer functions without loading speech engines or GUI services."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from loguru import logger

from open_llm_vtuber.mcpp.privacy import project, safe_text
from open_llm_vtuber.mcpp import market_preflight
from open_llm_vtuber.mcpp.tool_identity import legacy_name


def consumer(filename, name, namespace):
    path=Path(__file__).resolve().parents[1]/'src/open_llm_vtuber/conversations'/filename
    nodes=ast.parse(path.read_text(encoding='utf-8')).body
    function=next(node for node in nodes if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name)
    tree=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),function],type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree),str(path),'exec'),namespace)
    return namespace[name]


class ConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_status_broadcast_redacts_before_cap(self):
        event={'type':'tool_call_status','status':'error','content':'x'*5000+'?code=sentinel&state=sentinel','_meta':{'token':'sentinel'}}
        async def chat(_):
            yield event
        context=SimpleNamespace(agent_engine=SimpleNamespace(chat=chat),character_config=SimpleNamespace(character_name='fixture'))
        broadcast=AsyncMock()
        process=consumer('group_conversation.py','process_member_response',{'project':project,'safe_text':safe_text,'logger':logger,'json':json})
        await process(context,None,AsyncMock(),None,broadcast,['fixture'])
        delivered=broadcast.await_args.args[1]
        self.assertNotIn('sentinel',str(delivered))
        self.assertLessEqual(len(delivered['content'].encode()),2048)
        self.assertEqual(event['_meta']['token'],'sentinel')

    async def test_canonical_omi_evidence_survives_history_consumer(self):
        store=Mock()
        save=consumer('single_conversation.py','_store_tool_status_event',{
            'legacy_name':legacy_name,'store_history_event':store,
            'build_omi_evidence_snapshot':market_preflight.build_omi_evidence_snapshot,
            'format_omi_evidence_for_history':market_preflight.format_omi_evidence_for_history})
        evidence={'kind':'omi_evidence','warnings':['stale'],'missing':['bars']}
        context=SimpleNamespace(history_uid='h',character_config=SimpleNamespace(conf_uid='fixture'))
        save(context=context,output_item={'status':'completed','tool_name':'omi-market::omi.ask','content':'truncated UI text','omi_evidence':evidence},skip_history=False)
        self.assertEqual(store.call_args.kwargs['event_type'],'omi_evidence')
        self.assertEqual(store.call_args.kwargs['detail'],evidence)

    async def test_omi_worker_error_is_safe_and_delta_is_incomplete(self):
        def failed(_):
            yield {'event':'delta','data':{'text':'partial evidence'}}
            raise RuntimeError('sentinel')
        with patch.object(market_preflight,'_iter_omi_sse_http_events',failed):
            events=[event async for event in market_preflight.stream_omi_ask_events({})]
        self.assertNotIn('sentinel',str(events))
        self.assertTrue(market_preflight.format_omi_stream_final_tool_result(events)['is_error'])
        self.assertTrue(market_preflight.format_omi_stream_final_tool_result(events[:1])['is_error'])
