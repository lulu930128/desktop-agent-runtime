"""Argument diagnostics must explain rejection without exposing argument data."""
import json
import unittest
from unittest.mock import AsyncMock

from loguru import logger
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_identity import provider_alias
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_schema import (
    MAX_ARGUMENT_DIAGNOSTICS, MAX_DIAGNOSTIC_PATH, SchemaError,
    schema_digest, validate_arguments,
)
from open_llm_vtuber.mcpp.types import FormattedTool, ToolCallFunctionObject, ToolCallObject


class ArgumentDiagnosticsTests(unittest.TestCase):
    def reject(self, schema, args):
        with self.assertRaises(SchemaError) as caught:
            validate_arguments(schema, args)
        self.assertEqual(str(caught.exception), "invalid_arguments")
        self.assertEqual(caught.exception.code, "invalid_arguments")
        return caught.exception.diagnostics

    def test_nested_array_union_has_field_path_and_types_without_values(self):
        schema = {"type": "object", "properties": {"target": {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"anyOf": [{"type": "integer"}, {"type": "null"}]}}}}}}
        rows = self.reject(schema, {"target": {"symbols": ["PRIVATE_VALUE"]}})
        self.assertTrue(any(row["path"] == "$/target/symbols/0" and row["keyword"] == "type"
                            and row["expected_rule"] == {"type": "integer"}
                            and row["actual_type"] == "string" for row in rows))
        self.assertNotIn("PRIVATE_VALUE", json.dumps(rows))

    def test_required_missing_field_and_numeric_rule(self):
        schema = {"type": "object", "required": ["count"], "properties": {"count": {"type": "integer", "maximum": 3}}}
        row = self.reject(schema, {})[0]
        self.assertEqual((row["path"], row["keyword"], row["actual_type"], row["expected_type"]),
                         ("$/count", "required", "missing", "integer"))
        row = self.reject(schema, {"count": 8})[0]
        self.assertEqual(row["expected_rule"], {"maximum": 3})
        self.assertEqual(row["actual_type"], "integer")

    def test_non_object_boolean_and_non_json_types(self):
        for value, name in [(None, "null"), (True, "boolean"), ([], "array"), (1, "integer"), (1.5, "number"), ("secret", "string")]:
            with self.subTest(name=name):
                self.assertEqual(self.reject({"type": "object"}, value)[0]["actual_type"], name)
        for value in [float("nan"), float("inf"), object()]:
            self.assertEqual(self.reject({"type": "object"}, {"x": value})[0]["keyword"], "json")
        self.assertEqual(self.reject({"type": "object", "properties": {"n": {"type": "integer"}}}, {"n": True})[0]["actual_type"], "boolean")

    def test_enum_const_and_dynamic_keys_are_not_logged(self):
        for rule in [{"enum": ["PRIVATE_EXPECTED"]}, {"const": "PRIVATE_EXPECTED"}]:
            rows = self.reject({"type": "object", "properties": {"mode": rule}}, {"mode": "PRIVATE_ACTUAL"})
            self.assertNotIn("PRIVATE", json.dumps(rows))
        schema = {"type": "object", "patternProperties": {".*": {"type": "integer"}}}
        rows = self.reject(schema, {"PRIVATE_KEY": "PRIVATE_VALUE"})
        self.assertEqual(rows[0]["path"], "$/*")
        self.assertNotIn("PRIVATE", json.dumps(rows))
        rows = self.reject({"type": "object", "additionalProperties": False}, {"PRIVATE_KEY": "PRIVATE_VALUE"})
        self.assertNotIn("PRIVATE", json.dumps(rows))

    def test_count_path_and_rule_lengths_are_bounded(self):
        schema = {"type": "object", "properties": {"long" * 200: {"type": "array", "items": {"type": "integer"}}}}
        rows = self.reject(schema, {"long" * 200: ["x"] * 50})
        self.assertEqual(len(rows), MAX_ARGUMENT_DIAGNOSTICS)
        self.assertTrue(all(len(row["path"]) <= MAX_DIAGNOSTIC_PATH for row in rows))
        rows = self.reject({"type": "object", "properties": {"n": {"maximum": 10 ** 1000}}}, {"n": 10 ** 1001})
        self.assertLessEqual(len(json.dumps(rows[0]["expected_rule"])), 256)

    def test_valid_nullable_and_local_ref_calls_still_pass(self):
        schema = {"type": "object", "$defs": {"n": {"type": ["integer", "null"]}},
                  "properties": {"n": {"$ref": "#/$defs/n"}}}
        for args in [{}, {"n": 2}, {"n": None}]:
            validate_arguments(schema, args)

    def test_named_extra_field_and_pattern_properties_have_precise_paths(self):
        schema = {"type": "object", "properties": {"question": {"type": "string"}},
                  "patternProperties": {"^x_": {"type": "integer"}}, "additionalProperties": False}
        args = {"question": "PRIVATE_VALUE", "x_count": 2, "extra_option": ["PRIVATE_VALUE"]}
        rows = self.reject(schema, args)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"path": "$/extra_option", "keyword": "additionalProperties",
                                  "expected_rule": {"additionalProperties": False},
                                  "expected_type": "absent", "actual_type": "array"})
        self.assertNotIn("PRIVATE_VALUE", json.dumps(rows))
        validate_arguments(schema, {"question": "valid", "x_count": 2})
        # JSON Schema patterns use search semantics, not fullmatch.
        schema["patternProperties"] = {"_count": {"type": "integer"}}
        validate_arguments(schema, {"x_count_suffix": 2})

    def test_sensitive_and_unbounded_extra_keys_are_masked_in_executor_logs(self):
        identity = "diagnostic::extra"
        schema = {"type": "object", "additionalProperties": False}
        manager = ToolManager(initial_tools_dict={identity: FormattedTool(
            schema, "diagnostic", canonical_id=identity, wire_name="extra")})
        executor = ToolExecutor(AsyncMock(), manager)
        executor._tool_policy = ToolPolicy({"tools": {identity: {"mode": "read_only"}}})
        logs = []
        sink = logger.add(lambda message: logs.append(message.record["message"]), level="WARNING")
        try:
            for name in ("apiKey", "access_token", "client_secret", "credential", "password", "PRIVATE_DATA", "a" * 65, "user@example.test", "\u79c1\u4eba"):
                with self.subTest(name=name):
                    decision = executor.check_call(identity, {name: "PRIVATE_VALUE"}, tool_id="call_masked")
                    self.assertEqual((decision.status, decision.reason_code), ("blocked", "invalid_arguments"))
                    payload = json.loads(logs[-1].split(": ", 1)[1])
                    self.assertEqual(payload["diagnostics"][0]["path"], "$/*")
                    self.assertNotIn(name, logs[-1])
                    self.assertNotIn("PRIVATE_VALUE", logs[-1])
            rows = self.reject(schema, {f"extra_{i}": "PRIVATE_VALUE" for i in range(50)})
            self.assertEqual(len(rows), MAX_ARGUMENT_DIAGNOSTICS)
        finally:
            logger.remove(sink)


class ExecutorDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.identity = "diagnostic::read"
        self.alias = provider_alias(self.identity)
        self.schema = {"type": "object", "properties": {"target": {"type": "object"}}}
        info = FormattedTool(self.schema, "diagnostic", api_name=self.alias, canonical_id=self.identity,
                             wire_name="read", schema_digest=schema_digest(self.schema))
        manager = ToolManager([{"type": "function", "function": {"name": self.alias}}], [], {self.identity: info})
        self.client = AsyncMock()
        self.executor = ToolExecutor(self.client, manager)
        self.executor._tool_policy = ToolPolicy({"tools": {self.identity: {"mode": "read_only"}}})
        self.logs = []
        self.sink = logger.add(lambda message: self.logs.append(message.record["message"]), level="WARNING")

    def tearDown(self):
        logger.remove(self.sink)

    async def test_native_alias_invalid_args_are_blocked_with_correlated_log(self):
        call = ToolCallObject(id="call_diagnostics", function=ToolCallFunctionObject(
            name=self.alias, arguments=json.dumps({"target": "PRIVATE_ARGUMENT", "api_key": "sk-test-placeholder-never-valid"})))
        updates = [event async for event in self.executor.execute_tools([call], "OpenAI")]
        self.assertEqual(updates[0]["status"], "blocked")
        self.assertEqual(updates[0]["reason_code"], "invalid_arguments")
        self.assertEqual(updates[0]["outcome"], "schema_invalid")
        self.assertIn("$/target", updates[0]["content"])
        self.assertIn("schema_invalid", updates[-1]["results"][0]["content"])
        self.assertNotIn("PRIVATE", str(updates))
        self.client.call_tool.assert_not_awaited()
        line = next(line for line in self.logs if line.startswith("Tool argument schema"))
        payload = json.loads(line.split(": ", 1)[1])
        self.assertEqual((payload["tool_identity"], payload["tool_alias"], payload["call_id"]),
                         (self.identity, self.alias, "call_diagnostics"))
        self.assertEqual(payload["schema_digest"], schema_digest(self.schema))
        self.assertEqual(payload["diagnostics"][0]["path"], "$/target")
        self.assertEqual(payload["diagnostics"][0]["expected_type"], "object")
        self.assertEqual(payload["diagnostics"][0]["actual_type"], "string")
        self.assertNotIn("PRIVATE", "\n".join(self.logs))
        self.assertEqual(len([line for line in self.logs if line.startswith("Tool argument schema")]), 1)

    async def test_direct_execution_is_rejected_and_logged_before_mcp(self):
        result = await self.executor.run_single_tool(self.identity, "call_direct", {"target": 7})
        self.assertTrue(result[0])
        self.assertIn("$/target", result[1])
        self.client.call_tool.assert_not_awaited()
        self.assertIn('"call_id":"call_direct"', self.logs[0])

    def test_valid_call_and_policy_denial_do_not_emit_schema_errors(self):
        self.assertTrue(self.executor.check_call(self.identity, {"target": {}}).allowed)
        self.executor._tool_policy = ToolPolicy({"tools": {self.identity: {"mode": "deny"}}})
        decision = self.executor.check_call(self.identity, {"target": "PRIVATE"})
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "policy_disabled")
        self.assertEqual(self.logs, [])

    def test_schema_change_is_still_distinct_from_invalid_arguments(self):
        self.executor._tool_manager.tools[self.identity].input_schema["title"] = "changed"
        self.assertEqual(self.executor.check_call(self.identity, {}).reason_code, "schema_changed")
        self.assertEqual(self.logs, [])
