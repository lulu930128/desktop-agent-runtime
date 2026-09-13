"""Exercise the real agent's preflight with fake transport and no model call."""
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from open_llm_vtuber.agent.agents import basic_memory_agent as agent_module
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_result import ToolResult
from open_llm_vtuber.mcpp.types import FormattedTool


class OmiAgentPathTests(unittest.IsolatedAsyncioTestCase):
    async def run_preflight(self, policy, stream_events):
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile = 'openai_non_strict'
        schema = {'type':'object','properties':{'allow_write':{'type':'boolean'},'tool_budget':{'type':'object'}}}
        tools = {'omi-market::'+name:FormattedTool(schema, 'omi-market', canonical_id='omi-market::'+name, wire_name=name) for name in ('omi.ask','omi.ask_stream')}
        o, c = adapter.format_tools_for_api(tools)
        manager = ToolManager(o,c,tools)
        client = AsyncMock()
        client.call_tool.return_value = ToolResult(structured_content={'contract_version':'omi.decision.v4','status':'partial','warnings':['stale'],'missing':['bars']})
        executor = ToolExecutor(client,manager)
        executor._tool_policy = policy
        agent = object.__new__(agent_module.BasicMemoryAgent)
        agent._tool_manager, agent._tool_executor = manager, executor
        agent._use_mcpp, agent._last_omi_resolution = True, None
        agent._tts_preprocessor_config = agent._live2d_model = None
        agent._faster_first_response, agent._segment_method = False, 'regex'
        agent._to_text_prompt = lambda _: '請分析台積電股票與市場數據'
        agent._compose_tool_route_text = lambda text: text
        agent._to_messages = lambda _: []
        agent._format_relevant_memory_prompt = lambda _: ''
        agent._compose_tool_system_prompt = lambda **_: ''
        agent._add_message = lambda *args: None
        agent._llm = object.__new__(agent_module.OpenAICompatibleAsyncLLM)
        captured = []
        async def completion(messages, system):
            captured.extend(messages)
            yield 'done'
        agent._llm.chat_completion = completion
        stream_calls = []
        async def stream(arguments):
            stream_calls.append(arguments)
            for event in stream_events:
                yield event
        with ExitStack() as stack:
            # Bypass speech rendering only; policy, routing and preflight stay real.
            for name in ('tts_filter','display_processor','actions_extractor','sentence_divider'):
                stack.enter_context(patch.object(agent_module,name,lambda *a,**kw: lambda f:f))
            stack.enter_context(patch.object(agent_module,'stream_omi_ask_events',stream))
            events = [event async for event in agent._chat_function_factory()(None)]
        return events,captured,client,stream_calls

    async def test_absent_policy_blocks_stream_and_fallback(self):
        events, _, client, calls = await self.run_preflight(None,[])
        self.assertEqual(calls,[])
        client.call_tool.assert_not_awaited()
        self.assertTrue(any(isinstance(e,dict) and e.get('status')=='blocked' for e in events))

    async def test_stream_failure_does_not_repeat_via_mcp(self):
        policy = ToolPolicy.load_default()
        events, captured, client, calls = await self.run_preflight(policy,[{'event':'transport_error','data':{'error':'outcome unknown'}}])
        self.assertEqual(len(calls),1)
        client.call_tool.assert_not_awaited()
        self.assertIn('unknown',str(captured))

    async def test_blocked_stream_uses_validated_bounded_fallback(self):
        policy = ToolPolicy({'tools':{'omi-market::omi.ask_stream':{'mode':'confirm'},'omi-market::omi.ask':{'mode':'read_only','deny_truthy_args':['allow_write']}}})
        _, captured, client, calls = await self.run_preflight(policy,[])
        self.assertEqual(calls,[])
        client.call_tool.assert_awaited_once()
        self.assertFalse(client.call_tool.await_args.kwargs['tool_args']['allow_write'])
        self.assertIn('stale',str(captured))

    async def test_final_limits_and_secret_projection_reach_model_context(self):
        event = {'event':'final','data':{'contract_version':'omi.decision.v4','ok':True,'warnings':['stale'],'missing':['bars'],'access_token':'sentinel'}}
        events, captured, client, calls = await self.run_preflight(ToolPolicy.load_default(),[event])
        self.assertEqual(len(calls),1)
        client.call_tool.assert_not_awaited()
        self.assertNotIn('sentinel',str(events)+str(captured))
        self.assertIn('stale',str(captured))
