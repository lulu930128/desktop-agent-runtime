import asyncio
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from mcp.types import Tool, CallToolResult, TextContent, ErrorData
from mcp.shared.exceptions import McpError
from open_llm_vtuber.mcpp.mcp_client import MCPClient, ValidatedClientSession
from open_llm_vtuber.mcpp.tool_schema import schema_digest
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.types import MCPServer


def fixture(pages):
    registry=object.__new__(ServerRegistry)
    registry.servers={'fake':MCPServer('fake','unused',timeout=timedelta(seconds=.2))}
    client=MCPClient(registry)
    session=SimpleNamespace(list_tools=AsyncMock(side_effect=pages))
    client._ensure_server_running_and_get_session=AsyncMock(return_value=session)
    return client,session


def page(name=None,cursor=None):
    return SimpleNamespace(tools=[] if name is None else [Tool(name=name,inputSchema={'type':'object'})],nextCursor=cursor)


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_pages_and_atomic_cache(self):
        client,session=fixture([page('a','opaque'),page('b')])
        result=await client.discover_tools('fake')
        self.assertTrue(result.complete)
        self.assertEqual([t.name for t in result.tools],['a','b'])
        self.assertEqual(result.pages_read,2)
        self.assertEqual(session.list_tools.await_args_list[1].kwargs,{'cursor':'opaque'})
        self.assertEqual(len(client._list_tools_cache['fake']),2)

    async def test_second_page_failure_preserves_complete_cache(self):
        client,session=fixture([page('old'),page('new','opaque'),RuntimeError('private cursor')])
        await client.discover_tools('fake')
        result=await client.discover_tools('fake',refresh=True)
        self.assertFalse(result.complete)
        self.assertEqual([t.name for t in client._list_tools_cache['fake']],['old'])
        self.assertTrue(result.cache_observed_at)
        self.assertNotIn('private cursor',result.reason)

    async def test_repeated_cursor_and_duplicate_identity(self):
        for pages in ([page('a','c'),page('b','c')],[page('a','c'),page('a')]):
            client,_=fixture(pages)
            result=await client.discover_tools('fake')
            self.assertFalse(result.complete)
            self.assertNotIn('fake',client._list_tools_cache)

    async def test_page_count_and_tool_count_caps(self):
        client,_=fixture([page(str(i),str(i)) for i in range(20)])
        self.assertFalse((await client.discover_tools('fake')).complete)
        tools=[Tool(name=str(i),inputSchema={'type':'object'}) for i in range(1001)]
        client,_=fixture([SimpleNamespace(tools=tools,nextCursor=None)])
        self.assertFalse((await client.discover_tools('fake')).complete)

    async def test_timeout_and_cancel_leave_incomplete_diagnostics(self):
        client,session=fixture([])
        async def slow(**kwargs):
            await asyncio.sleep(1)
        session.list_tools.side_effect=slow
        self.assertEqual((await client.discover_tools('fake')).reason,'discovery_timeout')
        session.list_tools.side_effect=asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await client.discover_tools('fake')
        self.assertEqual(client.discovery_results['fake'].reason,'cancelled')

    async def test_complete_empty_is_distinct_and_other_server_survives(self):
        client,session=fixture([RuntimeError('failure'),page()])
        self.assertFalse((await client.discover_tools('fake')).complete)
        result=await client.discover_tools('other')
        self.assertTrue(result.complete)
        self.assertEqual(result.tools,[])

    async def test_fresh_schema_change_and_missing_tool_never_execute(self):
        for expected in ('old-digest', schema_digest({'type':'object'})):
            client, session = fixture([page('a' if expected == 'old-digest' else 'different')])
            session.call_tool = AsyncMock()
            result = await client.call_tool('fake', 'a', {}, expected_schema_digest=expected)
            self.assertIn(result.reason_code, {'schema_changed', 'tool_unavailable'})
            self.assertFalse(result.may_have_executed)
            session.call_tool.assert_not_awaited()

    async def test_sdk_output_validation_preserves_failed_evidence(self):
        client, _ = fixture([page('a')])
        await client.discover_tools('fake')
        session = ValidatedClientSession(None, None)
        session._tool_output_schemas['a'] = {'type':'object','properties':{'count':{'type':'integer'}},'required':['count']}
        session.list_tools = AsyncMock(return_value=page('a'))
        session.send_request = AsyncMock(return_value=CallToolResult(content=[TextContent(type='text',text='received')], structuredContent={'count':'wrong'}))
        client._ensure_server_running_and_get_session = AsyncMock(return_value=session)
        result = await client.call_tool('fake','a',{})
        self.assertEqual(result.reason_code,'output_schema_invalid')
        self.assertTrue(result.result_received)
        self.assertIn('received',result.model_text())
        session.send_request.assert_awaited_once()

    async def test_protocol_unknown_and_cancel_are_distinct_without_retry(self):
        for error, status in [(McpError(ErrorData(code=-32603,message='sentinel')),'failed'),
                              (RuntimeError('sentinel'),'unknown'), (asyncio.CancelledError(),'cancelled')]:
            client, session = fixture([page('a')])
            session.call_tool = AsyncMock(side_effect=error)
            if status == 'cancelled':
                with self.assertRaises(asyncio.CancelledError):
                    await client.call_tool('fake','a',{})
                result = client.last_call_result
            else:
                result = await client.call_tool('fake','a',{})
            self.assertEqual(result.status,status)
            self.assertNotIn('sentinel',result.model_text())
            self.assertTrue(result.may_have_executed)
            session.call_tool.assert_awaited_once()

    async def test_invalid_page_and_byte_limit_fail_closed(self):
        for response in [SimpleNamespace(tools=None,nextCursor=None),
                         SimpleNamespace(tools=[Tool(name='big',description='x'*(8*1024*1024),inputSchema={'type':'object'})],nextCursor=None)]:
            client, _ = fixture([response])
            result = await client.discover_tools('fake')
            self.assertFalse(result.complete)
            self.assertNotIn('fake',client._list_tools_cache)
