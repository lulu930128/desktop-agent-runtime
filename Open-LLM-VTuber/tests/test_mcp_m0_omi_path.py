"""Actual agent routing, no model/transport or automatic market preflight."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from open_llm_vtuber.agent.agents import basic_memory_agent as agent_module
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.types import FormattedTool

class OmiAgentPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_market_route_offers_canonical_tool_without_autorun(self):
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile = 'openai_non_strict'
        identity = 'omi-search::omi_ask'
        tools = {identity: FormattedTool({'type': 'object', 'properties': {'question': {'type': 'string'}}},
                 'omi-search', canonical_id=identity, wire_name='omi_ask')}
        o, c = adapter.format_tools_for_api(tools)
        manager = ToolManager(o, c, tools)
        client = AsyncMock()
        agent = object.__new__(agent_module.BasicMemoryAgent)
        agent._tool_manager, agent._tool_executor = manager, ToolExecutor(client, manager)
        agent._use_mcpp = True
        agent._tts_preprocessor_config = agent._live2d_model = None
        agent._faster_first_response, agent._segment_method = False, 'regex'
        agent._to_text_prompt = lambda _: 'TSMC stock market'
        agent._compose_tool_route_text = lambda text: text
        agent._to_messages = lambda _: []
        agent._format_relevant_memory_prompt = lambda _: ''
        agent._llm = object.__new__(agent_module.OpenAICompatibleAsyncLLM)
        offered = []
        async def interaction(messages, tools, **kwargs):
            offered.extend(tools)
            yield 'fixture response'
        agent._openai_tool_interaction_loop = interaction
        with ExitStack() as stack:
            for name in ('tts_filter', 'display_processor', 'actions_extractor', 'sentence_divider'):
                stack.enter_context(patch.object(agent_module, name, lambda *a, **k: lambda fn: fn))
            events = [event async for event in agent.chat(SimpleNamespace(metadata={"chat_speech":{"route":"legacy_bridge"}}))]
        self.assertTrue(events)
        self.assertEqual([row['function']['name'] for row in offered], ['kuro_discover'])
        client.call_tool.assert_not_awaited()
        self.assertFalse(hasattr(agent_module, 'stream_omi_ask_events'))
