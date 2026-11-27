"""Focused regression: GPT-6 Responses adapter and multi-domain tool routing."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import yaml

from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.types import FormattedTool, ToolCallObject

MODELS = ("gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")
QUESTION = ("應該不只吧，我是說像可以查我本機檔案的工具，還有看外網的工具，"
            "還有可以看我日文/英文學習狀況的工具")
AVAILABLE = [
    "kuro-web::advanced_search_web", "kuro-web::fetch_content",
    "kuro-web::smart_search_web", "omi-search::omi_ask",
    "omi-search::omi_read_data_freshness", "omi-search::omi_read_source_health",
    "project-workspace::read_file", "project-workspace::find_files",
    "japanese-study::study_get_summary", "english-study::english_get_summary",
]


class ToolInventoryRegression(unittest.TestCase):
    def test_actual_multidomain_query_retains_three_requested_capabilities(self):
        catalog = ToolCatalog.load_default()
        route = catalog.route(QUESTION, AVAILABLE)
        self.assertLessEqual(len(route.tool_names), catalog.max_candidate_tools)
        self.assertTrue(any(name.startswith("project-workspace::") for name in route.tool_names))
        self.assertTrue(any(name.startswith("japanese-study::") for name in route.tool_names))
        self.assertTrue(any(name.startswith("english-study::") for name in route.tool_names))
        self.assertIn("kuro-web::advanced_search_web", route.tool_names)

    def test_only_discovered_candidates_may_be_exposed(self):
        route = ToolCatalog.load_default().route(QUESTION, AVAILABLE[:6])
        self.assertTrue(set(route.tool_names).issubset(set(AVAILABLE[:6])))
        self.assertFalse(any("study" in name for name in route.tool_names))

    def test_single_market_query_remains_omi_first(self):
        route = ToolCatalog.load_default().route("可以幫我查2330這支股票狀況嗎", AVAILABLE)
        self.assertEqual(route.tool_names[0], "omi-search::omi_ask")

    def test_inventory_prompt_is_snapshot_not_six_tool_claim(self):
        raw = {"japanese-study::study_get_summary": FormattedTool(
            {"type": "object", "properties": {}}, "japanese-study")}
        manager = ToolManager(initial_tools_dict=raw)
        manager.get_formatted_tools("OpenAI", request_text="你有哪些工具")
        prompt = manager.get_last_route_prompt()
        self.assertIn("discovered ToolManager snapshot", prompt)
        self.assertIn("japanese-study::study_get_summary", prompt)
        self.assertIn("not proof of successful execution", prompt)

    def test_besides_omi_followup_exposes_discovery_snapshot(self):
        raw = {"project-workspace::read_file": FormattedTool(
            {"type": "object", "properties": {}}, "project-workspace")}
        manager = ToolManager(initial_tools_dict=raw)
        manager.get_formatted_tools("OpenAI", request_text="除了omi呢")
        prompt = manager.get_last_route_prompt()
        self.assertIn("project-workspace::read_file", prompt)
        self.assertIn("multi_tool_use.parallel", prompt)

    def test_launcher_four_real_model_ids_and_default(self):
        settings = yaml.safe_load((Path(__file__).resolve().parents[2]
                                   / "kuro_launcher.settings.yaml").read_text(encoding="utf-8"))
        selection = settings["llm"]["openai"]
        self.assertEqual(tuple(selection["models"]), MODELS)
        self.assertEqual(selection["default_model"], "gpt-6-luna")


class FakeStream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __aiter__(self):
        async def emit():
            for event in self.events:
                yield event
        return emit()

    async def close(self):
        self.closed = True


def evt(kind, **kwargs):
    return SimpleNamespace(type=kind, **kwargs)


class ResponsesAdapterRegression(unittest.IsolatedAsyncioTestCase):
    def test_translate_chat_history_tool_roundtrip_to_responses_items(self):
        chat = [
            {"role": "user", "content": "查詢美股"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_123", "type": "function",
                 "function": {"name": "omi_search_omi_ask", "arguments": '{"question":"美股"}'}}
            ]},
            {"role": "tool", "tool_call_id": "call_123", "content": '{"ok":true}'},
        ]
        data = AsyncLLM._responses_input(chat)
        self.assertEqual([item.get("type") for item in data[1:]],
                         ["function_call", "function_call_output"])
        self.assertEqual(data[1]["call_id"], data[2]["call_id"])
        self.assertNotIn("tool_call_id", data[2])

    async def test_each_requested_gpt6_model_uses_responses_without_temperature(self):
        for model in MODELS:
            with self.subTest(model=model):
                llm = AsyncLLM(model=model, base_url="https://api.openai.com/v1",
                               llm_api_key="test-not-a-real-key")
                self.assertTrue(llm._uses_responses)
                stream = FakeStream([
                    evt("response.output_text.delta", delta="已確認"),
                    evt("response.output_item.added", output_index=0,
                        item=evt("function_call", name="omi_search_omi_ask",
                                 call_id="call_123", arguments="")),
                    evt("response.function_call_arguments.delta", output_index=0,
                        delta='{"question":"美股"}'),
                    evt("response.output_item.done", output_index=0,
                        item=evt("function_call", name="omi_search_omi_ask",
                                 call_id="call_123", arguments='{"question":"美股"}')),
                ])
                fake_create = AsyncMock(return_value=stream)
                llm.client = SimpleNamespace(responses=SimpleNamespace(create=fake_create))
                result = [row async for row in llm.chat_completion(
                    [{"role": "user", "content": "查詢美股"}], "指令",
                    tools=[{"type": "function", "function": {
                        "name": "omi_search_omi_ask",
                        "description": "Market data",
                        "parameters": {"type": "object", "properties": {}}}}])]
                self.assertEqual(result[0], "已確認")
                self.assertEqual(len(result), 2)
                self.assertIsInstance(result[1][0], ToolCallObject)
                self.assertEqual(result[1][0].id, "call_123")
                self.assertEqual(result[1][0].function.name, "omi_search_omi_ask")
                self.assertEqual(result[1][0].function.arguments, '{"question":"美股"}')
                self.assertTrue(stream.closed)
                params = fake_create.call_args.kwargs
                self.assertEqual(params["model"], model)
                self.assertEqual(params["reasoning"]["effort"],
                                 "low" if model in MODELS[:2] else "none")
                self.assertFalse(params["store"])
                self.assertNotIn("temperature", params)
                self.assertEqual(params["tools"][0]["strict"], False)


    async def test_reasoning_item_is_replayed_before_matching_tool_call(self):
        llm = AsyncLLM(model="gpt-6.1-sol", base_url="https://api.openai.com/v1",
                       llm_api_key="test-not-a-real-key")

        class ReasoningItem:
            type = "reasoning"

            def model_dump(self, **kwargs):
                return {"type": "reasoning", "id": "rs_123",
                        "summary": [], "encrypted_content": "opaque-test-cipher"}

        first_stream = FakeStream([
            evt("response.output_item.done", output_index=0, item=ReasoningItem()),
            evt("response.output_item.done", output_index=1,
                item=evt("function_call", name="omi_search_omi_ask",
                         call_id="call_123", arguments='{"question":"美股"}')),
        ])
        second_stream = FakeStream([evt("response.output_text.delta", delta="完成")])
        create = AsyncMock(side_effect=[first_stream, second_stream])
        llm.client = SimpleNamespace(responses=SimpleNamespace(create=create))
        tools = [{"type": "function", "function": {
            "name": "omi_search_omi_ask",
            "parameters": {"type": "object", "properties": {}}}}]

        first = [item async for item in llm.chat_completion(
            [{"role": "user", "content": "查詢美股"}], "system", tools=tools)]
        self.assertEqual(first[-1][0].id, "call_123")

        chat_with_result = [
            {"role": "user", "content": "查詢美股"},
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_123", "type": "function", "function": {
                    "name": "omi_search_omi_ask", "arguments": '{"question":"美股"}'}}]},
            {"role": "tool", "tool_call_id": "call_123", "content": '{"ok":true}'},
        ]
        second = [item async for item in llm.chat_completion(
            chat_with_result, "system", tools=tools)]
        self.assertEqual(second, ["完成"])
        second_input = create.call_args_list[1].kwargs["input"]
        self.assertEqual([item.get("type") for item in second_input[1:4]],
                         ["reasoning", "function_call", "function_call_output"])
        self.assertEqual(second_input[1]["encrypted_content"], "opaque-test-cipher")
        self.assertTrue(first_stream.closed)
        self.assertTrue(second_stream.closed)

    async def test_reject_incomplete_response_function_call(self):
        llm = AsyncLLM(model="gpt-6-luna", base_url="https://api.openai.com/v1",
                       llm_api_key="test-not-a-real-key")
        stream = FakeStream([
            evt("response.output_item.done", output_index=0,
                item=evt("function_call", name="omi_search_omi_ask",
                         call_id="", arguments="{}"))
        ])
        llm.client = SimpleNamespace(responses=SimpleNamespace(
            create=AsyncMock(return_value=stream)))
        with self.assertRaisesRegex(RuntimeError, "lacks call_id"):
            _ = [row async for row in llm.chat_completion(
                [{"role": "user", "content": "test"}], "system", tools=[])]
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()
