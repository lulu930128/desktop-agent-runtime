"""Kuro's effective OMI descriptor, canonical validation and sole executor path."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import AsyncMock

from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_result import ToolResult
from open_llm_vtuber.mcpp.tool_schema import SchemaError, provider_schema, schema_digest, validate_arguments
from open_llm_vtuber.mcpp.types import FormattedTool, ToolCallFunctionObject, ToolCallObject

IDENTITY = "omi-search::omi_ask"
QUESTION = "可以幫我查查昨天美股的狀況嗎"
# Contract-shaped fixture; the opt-in live probe separately verifies discovery digests.
SCHEMA = {
    "type": "object", "required": ["question"], "additionalProperties": False,
    "properties": {
        "question": {"type": "string"},
        "target": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["auto", "market", "us_stock"]},
            "market": {"type": "string"}, "id": {"type": "string"}}},
        "mode": {"type": "string", "enum": ["brief", "data_only", "full"], "default": "data_only"},
        "contract_version": {"type": "string", "enum": ["omi.decision.v4"], "default": "omi.decision.v4"},
        "refresh_if_missing": {"type": "boolean", "default": False},
        "realtime_policy": {"type": "string", "enum": ["cache_only", "prefer_live", "require_live"], "default": "prefer_live"},
        "refresh_policy": {"type": "object", "properties": {
            "mode": {"type": "string", "enum": ["off", "stale_first"], "default": "stale_first"},
            "before_answer": {"type": "boolean", "default": True}}},
        "tool_budget": {"type": "object", "properties": {
            "max_calls": {"type": "integer", "minimum": 0, "maximum": 12, "default": 5},
            "max_external_fetches": {"type": "integer", "minimum": 0, "maximum": 8, "default": 3},
            "max_total_seconds": {"type": "integer", "minimum": 1, "maximum": 90, "default": 25}}},
    },
}


def setup():
    policy = ToolPolicy(json.loads((Path(__file__).parent / "fixtures/legacy_tool_grants.json").read_text(encoding="utf-8")))
    adapter = object.__new__(ToolAdapter)
    adapter.schema_profile, adapter._tool_policy = "openai_non_strict", policy
    raw = {IDENTITY: FormattedTool(deepcopy(SCHEMA), "omi-search", canonical_id=IDENTITY, wire_name="omi_ask")}
    openai, claude = adapter.format_tools_for_api(raw)
    manager = ToolManager(openai, claude, raw)
    client = AsyncMock()
    client.call_tool.return_value = ToolResult(structured_content={"ok": True})
    executor = ToolExecutor(client, manager)
    executor._tool_policy = policy
    return policy, manager, executor, client, openai[0]["function"], claude[0]


class EffectiveOmiArgumentsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.policy, self.manager, self.executor, self.client, self.function, self.claude = setup()
        self.args = {"question": QUESTION, "target": {"type": "market", "market": "US"},
                     "realtime_policy": "cache_only", "mode": "data_only", "refresh_if_missing": False}

    def prepare(self, args):
        return self.policy.prepare_arguments(IDENTITY, args, SCHEMA)

    def test_descriptor_projects_policy_and_preserves_canonical_digest(self):
        info = self.manager.get_tool(IDENTITY)
        effective = self.function["parameters"]
        self.assertEqual(info.input_schema, SCHEMA)
        self.assertEqual(info.schema_digest, schema_digest(SCHEMA))
        self.assertEqual(info.provider_schema_digest, schema_digest(effective))
        self.assertNotEqual(info.schema_digest, info.provider_schema_digest)
        self.assertEqual(effective, self.claude["input_schema"])
        self.assertFalse(effective["additionalProperties"])
        self.assertNotIn("market", effective["properties"])
        props = effective["properties"]
        for key, allowed in (("mode", ["data_only"]), ("refresh_if_missing", [False])):
            self.assertEqual(props[key]["enum"], allowed)
        budget = props["tool_budget"]["properties"]
        for name, limit in (("max_calls", 5), ("max_external_fetches", 0), ("max_total_seconds", 25)):
            self.assertEqual((budget[name]["maximum"], budget[name]["default"]), (limit, limit))
        self.assertEqual(budget["max_external_fetches"]["enum"], [0])
        self.assertIn("target.market", self.function["description"])
        self.assertIn("target", props["target"]["description"])
        self.assertEqual(props["realtime_policy"]["default"], "cache_only")

    def test_declared_defaults_pass_both_effective_schema_and_policy(self):
        args = self.prepare(self.args)
        validate_arguments(SCHEMA, args)
        validate_arguments(self.function["parameters"], args)
        self.assertTrue(self.policy.check(IDENTITY, args).allowed)
        self.assertTrue(self.executor.check_call(IDENTITY, self.args).allowed)
        self.assertEqual(args["tool_budget"]["max_external_fetches"], 0)
        self.assertEqual(args["refresh_policy"], {"mode": "off", "before_answer": False})

    def test_original_excess_fetch_budget_remains_denied_with_actionable_feedback(self):
        args = {**self.args, "tool_budget": {"max_external_fetches": 3}}
        self.assertEqual(self.prepare(args)["tool_budget"]["max_external_fetches"], 3)
        decision = self.executor.check_call(IDENTITY, args)
        self.assertEqual(decision.reason_code, "argument_policy")
        self.assertIn('"tool_budget.max_external_fetches": 0', decision.reason)
        with self.assertRaises(SchemaError):
            validate_arguments(self.function["parameters"], args)
        corrected = {**args, "tool_budget": {"max_external_fetches": 0}}
        self.assertTrue(self.executor.check_call(IDENTITY, corrected).allowed)

    async def test_root_market_repair_reaches_mcp_with_canonical_digest(self):
        original = {"question": QUESTION, "market": "US"}
        saved = deepcopy(original)
        self.assertTrue(self.executor.check_call(self.function["name"], original).allowed)
        error, _, metadata, _ = await self.executor.run_single_tool(self.function["name"], "root-market", original)
        self.assertFalse(error)
        self.assertEqual(metadata["execution_status"], "succeeded")
        sent = self.client.call_tool.call_args.kwargs
        self.assertEqual((sent["server_name"], sent["tool_name"]), ("omi-search", "omi_ask"))
        self.assertEqual(sent["tool_args"]["target"], {"type": "market", "market": "US"})
        self.assertNotIn("market", sent["tool_args"])
        self.assertEqual(sent["tool_args"]["tool_budget"]["max_external_fetches"], 0)
        self.assertEqual(sent["expected_schema_digest"], schema_digest(SCHEMA))
        validate_arguments(SCHEMA, sent["tool_args"])
        self.assertEqual(original, saved)

    def test_market_alias_is_idempotent_and_only_unambiguous(self):
        for target in ({}, {"type": "market"}, {"type": "market", "market": "US"}):
            args = {"question": QUESTION, "market": "US", "target": target}
            prepared = self.prepare(args)
            self.assertTrue(self.executor.check_call(IDENTITY, args).allowed)
            self.assertEqual(self.prepare(prepared), prepared)
        for args in ({"market": 7}, {"market": ""}, {"market": "US", "target": None},
                     {"market": "US", "target": {"market": "TW"}},
                     {"market": "US", "target": {"type": "us_stock", "id": "AAPL"}}):
            with self.subTest(args=args):
                self.assertEqual(self.executor.check_call(IDENTITY, {"question": QUESTION, **args}).reason_code,
                                 "invalid_arguments")

    async def test_unknown_fields_are_rejected_after_known_field_repair(self):
        args = {"question": QUESTION, "market": "US", "unexpected": "PRIVATE"}
        decision = self.executor.check_call(IDENTITY, args)
        self.assertEqual(decision.reason_code, "invalid_arguments")
        self.assertIn("$/unexpected", decision.reason)
        self.assertNotIn("PRIVATE", decision.reason)
        await self.executor.run_single_tool(IDENTITY, "unknown", args)
        self.client.call_tool.assert_not_awaited()

    async def test_refresh_write_and_excess_budgets_still_never_reach_mcp(self):
        for extra in ({"mode": "full"}, {"mode": "trade"}, {"refresh_if_missing": True},
                      {"refresh_if_missing": "false"}, {"allow_write": True}, {"allow_external_fetch": True},
                      {"tool_budget": {"max_calls": 6}}, {"tool_budget": {"max_total_seconds": 26}},
                      {"tool_budget": {"max_external_fetches": 1}}, {"tool_budget": {"max_external_fetches": -1}},
                      {"tool_budget": {"max_external_fetches": True}}):
            with self.subTest(extra=extra):
                self.assertFalse(self.executor.check_call(IDENTITY, {**self.args, **extra}).allowed)
                result = await self.executor.run_single_tool(IDENTITY, "denied", {**self.args, **extra})
                self.assertTrue(result[0])
        self.client.call_tool.assert_not_awaited()

    async def test_native_execute_status_and_alias_path(self):
        call = ToolCallObject(id="native", function=ToolCallFunctionObject(
            name=self.function["name"], arguments=json.dumps(self.args)))
        updates = [row async for row in self.executor.execute_tools([call], "OpenAI")]
        self.assertEqual([r["status"] for r in updates if r["type"] == "tool_call_status"], ["running", "completed"])
        self.assertEqual(updates[-2]["execution_status"], "succeeded")
        self.client.call_tool.assert_awaited_once()

    def test_schema_change_and_disabled_policy_are_not_repaired_around(self):
        self.manager.tools[IDENTITY].input_schema["title"] = "drift"
        self.assertEqual(self.executor.check_call(IDENTITY, self.args).reason_code, "schema_changed")
        self.manager.tools[IDENTITY].input_schema.pop("title")
        self.executor._tool_policy = ToolPolicy({"tools": {IDENTITY: {"mode": "deny"}}})
        self.assertEqual(self.executor.check_call(IDENTITY, self.args).reason_code, "policy_disabled")

    def test_projection_uses_current_policy_limits(self):
        config = deepcopy(self.policy.policy)
        config["tools"][IDENTITY]["max_numeric_args"]["tool_budget.max_calls"] = 2
        policy = ToolPolicy(config)
        effective = policy.llm_schema(IDENTITY, SCHEMA)
        self.assertEqual(effective["properties"]["tool_budget"]["properties"]["max_calls"]["default"], 2)
        self.assertEqual(policy.prepare_arguments(IDENTITY, self.args, SCHEMA)["tool_budget"]["max_calls"], 2)

    def test_unrelated_tool_descriptor_and_arguments_unchanged(self):
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile, adapter._tool_policy = "openai_non_strict", self.policy
        raw = {"other::read": FormattedTool(deepcopy(SCHEMA), "other", canonical_id="other::read", wire_name="read")}
        tools, _ = adapter.format_tools_for_api(raw)
        self.assertEqual(tools[0]["function"]["parameters"], provider_schema(SCHEMA))
        args = {"market": "US", "tool_budget": {"max_external_fetches": 3}}
        self.assertEqual(self.policy.prepare_arguments("other::read", args, SCHEMA), args)

    def test_exact_question_routes_to_omi_and_non_market_does_not(self):
        selected = self.manager.get_formatted_tools("OpenAI", request_text=QUESTION)
        self.assertEqual(selected[0]["function"]["name"], self.function["name"])
        for text in ("昨天過得怎麼樣", "可以幫我查查昨天的英文練習嗎", "今天午餐吃什麼"):
            self.assertEqual(self.manager.get_formatted_tools("OpenAI", request_text=text), [])


if __name__ == "__main__":
    unittest.main()
