"""Exercise the real agent without cloud, history, speech engines or GUI IO."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock
import json

from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from open_llm_vtuber.agent.input_types import BatchInput, TextData, TextSource
from open_llm_vtuber.agent.output_types import SentenceOutput
from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_identity import provider_alias
from open_llm_vtuber.mcpp.tool_result import ToolResult
from open_llm_vtuber.mcpp.types import FormattedTool, ToolCallObject, ToolCallFunctionObject

IDENTITY = "omi-search::omi_ask"
ALIAS = provider_alias(IDENTITY)


def market_manager():
    schema = {"type": "object", "properties": {"question": {"type": "string"}},
              "required": ["question"], "additionalProperties": False}
    return ToolManager(
        [{"type": "function", "function": {"name": ALIAS, "parameters": schema}}], [],
        {IDENTITY: FormattedTool(schema, "omi-search", canonical_id=IDENTITY, api_name=ALIAS, wire_name="omi_ask")})


class FixtureLLM(AsyncLLM):
    def __init__(self):
        self.calls = []

    async def chat_completion(self, messages, system=None, tools=None):
        self.calls.append((messages, system, tools))
        yield "一般對話回答。"


class NoToolQueryTruthTests(unittest.IsolatedAsyncioTestCase):
    async def turn(self, text, *, enabled=True, native=True, available=False):
        llm = FixtureLLM()
        if available:
            async def misleading(messages, system=None, tools=None):
                llm.calls.append((messages, system, tools))
                yield "市場查詢被權限擋下，我已經查了。"
            llm.chat_completion = misleading
        if not native:
            # Still an async fixture, but deliberately not a native-tool LLM type.
            llm = SimpleNamespace(calls=llm.calls, chat_completion=llm.chat_completion)
        executor = Mock()
        executor.turn_session.return_value = nullcontext()
        agent = BasicMemoryAgent(
            llm, "fixture", SimpleNamespace(extract_emotion=lambda _: []),
            use_mcpp=enabled, tool_manager=market_manager() if available else ToolManager(), tool_executor=executor,
            tts_preprocessor_config=SimpleNamespace(
                remove_special_char=False, ignore_brackets=True,
                ignore_parentheses=True, ignore_asterisks=True, ignore_angle_brackets=True),
            segment_method="regex",
        )
        # Reproduce misleading older context; it must not establish a current denial.
        agent._memory = [{"role": "assistant", "content": "市場查詢被權限擋下"}]
        events = [event async for event in agent.chat(BatchInput(
            texts=[TextData(source=TextSource.INPUT, content=text)],
            metadata={"chat_speech": {"locale": "zh-TW", "policy": "summary", "route": "dual_lane"}},
        ))]
        display = "".join(event.display_text.text for event in events if isinstance(event, SentenceOutput))
        self.assertFalse(any(isinstance(event, dict) and event.get("type") == "tool_call_status" for event in events))
        executor.execute_tools.assert_not_called()
        return display, llm, agent

    async def test_market_without_candidates_never_asks_model_to_explain_denial(self):
        for text in ("可以幫我看看昨天美股的大致狀況嗎", "美股昨天收盤如何", "昨天美國股市大盤"):
            with self.subTest(text=text):
                display, llm, agent = await self.turn(text)
                self.assertIn("沒有執行市場查詢", display)
                self.assertIn("尚未取得 OMI 資料", display)
                self.assertNotIn("權限", display)
                self.assertEqual(llm.calls[0][2][0]["function"]["name"], "kuro_discover")
                self.assertEqual(agent._memory[-1]["content"], display)

    async def test_disabled_or_unsupported_tools_preserve_not_queried_truth(self):
        for options in ({"enabled": False}, {"native": False}):
            with self.subTest(options=options):
                display, llm, _ = await self.turn("美股昨天收盤如何", **options)
                self.assertIn("沒有執行市場查詢", display)
                self.assertEqual(llm.calls, [])

    async def test_explicit_no_tools_does_not_claim_service_or_permission_failure(self):
        display, llm, _ = await self.turn("不用工具，昨天美股的大致狀況")
        self.assertIn("依照這輪不用工具的要求", display)
        self.assertNotIn("權限", display)
        self.assertNotIn("沒有可執行", display)
        self.assertEqual(llm.calls, [])

    async def test_ordinary_chat_retains_no_call_facts_in_system_prompt(self):
        display, llm, _ = await self.turn("昨天過得如何")
        self.assertEqual(display, "一般對話回答。")
        self.assertEqual(len(llm.calls), 1)
        system = llm.calls[0][1]
        self.assertIn("Search installed MCP tools", system)
        self.assertIn("actual tool results", system)
        self.assertEqual([t["function"]["name"] for t in llm.calls[0][2]], ["kuro_discover"])

    async def test_exposed_candidate_without_a_call_cannot_stream_or_store_false_denial(self):
        display, llm, agent = await self.turn("可以幫我看看昨天美股的大致狀況嗎", available=True)
        self.assertIn("沒有執行市場查詢", display)
        self.assertNotIn("權限", display)
        self.assertNotIn("已經查", display)
        self.assertTrue(llm.calls[0][2])
        self.assertEqual(agent._memory[-1]["content"], display)

    async def test_claude_without_a_call_cannot_stream_false_denial(self):
        async def completion(*args, **kwargs):
            yield {"type": "text_delta", "text": "市場查詢被權限擋下，我已經查了。"}
            yield {"type": "message_stop"}
        agent = BasicMemoryAgent.__new__(BasicMemoryAgent)
        agent._llm = SimpleNamespace(chat_completion=completion)
        agent._compose_tool_system_prompt = lambda *args: "fixture"
        agent._add_message = Mock()
        events = [event async for event in agent._claude_tool_interaction_loop([], [{}], require_tool_evidence=True)]
        text = "".join(event for event in events if isinstance(event, str))
        self.assertIn("沒有執行市場查詢", text)
        self.assertNotIn("權限", text)
        agent._add_message.assert_called_once_with(text, "assistant")

    async def test_actual_schema_policy_and_mcp_failures_keep_original_status(self):
        for mode, arguments, reason in (
            ("read_only", {"question": "fixture", "extra": True}, "invalid_arguments"),
            ("deny", {"question": "fixture"}, "policy_disabled"),
            ("read_only", {"question": "fixture"}, "backend_unavailable"),
        ):
            with self.subTest(reason=reason):
                manager = market_manager()
                client = AsyncMock()
                client.call_tool.return_value = ToolResult(
                    canonical_tool_id=IDENTITY, server_id="omi-search", wire_name="omi_ask",
                    status="failed", is_error=True, reason_code="backend_unavailable",
                    content_items=[{"type": "text", "text": "backend_unavailable"}])
                executor = ToolExecutor(client, manager)
                executor._tool_policy = ToolPolicy({"tools": {IDENTITY: {"mode": mode}}})
                count = 0
                async def completion(*args, **kwargs):
                    nonlocal count
                    count += 1
                    if count == 1:
                        yield "尚無證據卻聲稱已查。"
                        yield [ToolCallObject(id="truth-test", function=ToolCallFunctionObject(
                            name=ALIAS, arguments=json.dumps(arguments)))]
                    else:
                        yield "本輪工具回傳的原因是 " + reason
                agent = BasicMemoryAgent.__new__(BasicMemoryAgent)
                agent._llm = SimpleNamespace(chat_completion=completion)
                agent._system = "fixture"
                agent.prompt_mode_flag = False
                agent._compose_tool_system_prompt = lambda *args: "fixture"
                agent._add_message = Mock()
                agent._tool_executor = executor
                events = [event async for event in agent._openai_tool_interaction_loop([], [{}], require_tool_evidence=True)]
                statuses = [event for event in events if isinstance(event, dict) and event.get("type") == "tool_call_status"]
                expected_status = "error" if reason == "backend_unavailable" else "blocked"
                self.assertTrue(any(event.get("status") == expected_status and event.get("reason_code") == reason for event in statuses))
                text = "".join(event for event in events if isinstance(event, str))
                self.assertNotIn("聲稱已查", text)
                self.assertIn(reason, text)
                self.assertNotIn("沒有執行市場查詢", text)
                if reason == "backend_unavailable":
                    client.call_tool.assert_awaited_once()
                else:
                    client.call_tool.assert_not_awaited()

    async def test_attempted_call_without_final_result_is_not_reported_as_no_call(self):
        count = 0
        async def completion(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 1:
                yield [ToolCallObject(id="incomplete", function=ToolCallFunctionObject(name=ALIAS, arguments='{}'))]
            else:
                yield "市場查詢被權限擋下。"
        async def incomplete_executor(**kwargs):
            yield {"type": "tool_call_status", "status": "error", "reason_code": "transport_or_validation_error"}
        agent = BasicMemoryAgent.__new__(BasicMemoryAgent)
        agent._llm = SimpleNamespace(chat_completion=completion)
        agent._system = "fixture"
        agent.prompt_mode_flag = False
        agent._compose_tool_system_prompt = lambda *args: "fixture"
        agent._add_message = Mock()
        agent._tool_executor = SimpleNamespace(execute_tools=incomplete_executor)
        events = [event async for event in agent._openai_tool_interaction_loop([], [{}], require_tool_evidence=True)]
        text = "".join(event for event in events if isinstance(event, str))
        self.assertEqual(text, "本輪已嘗試工具呼叫，但尚未取得有效的市場證據。")


if __name__ == "__main__":
    unittest.main()
