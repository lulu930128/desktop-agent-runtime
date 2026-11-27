"""Scripted provider transcripts through the real agent loops and policy/executor."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_manager import DISCOVERY, ToolManager
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_result import ToolResult, normalize_result
from open_llm_vtuber.mcpp.types import FormattedTool, ToolCallObject, ToolCallFunctionObject


class DynamicToolTurnTests(unittest.IsolatedAsyncioTestCase):
    async def replay(self, mode):
        service = "english-study"
        write = service + "::english_record_practice"
        read = service + "::english_get_practice_session"
        schema = {"type":"object", "properties":{"id":{"type":"string"}}, "required":["id"]}
        wires = {name: FormattedTool(schema, service, wire_name=name.split("::")[1], canonical_id=name)
                 for name in (write, read)}
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile = "openai_non_strict"
        openai, claude = adapter.format_tools_for_api(wires)
        manager = ToolManager(openai, claude, wires)
        client = AsyncMock()
        client.call_tool.side_effect = [
            ToolResult(status="unknown", reason_code="timeout", is_error=True, result_received=False),
            ToolResult(structured_content={"session_id":"fixture", "saved":True}),
        ]
        executor = ToolExecutor(client, manager)
        executor._tool_policy = ToolPolicy({"tools":{}, "owner_services":[service]})
        calls = [(DISCOVERY, {}), (DISCOVERY, {"load":[write]}),
                 (wires[write].api_name, {"id":17}), (wires[write].api_name, {"id":"fixture"}),
                 (wires[write].api_name, {"id":"fixture"}), (DISCOVERY, {"load":[read]}),
                 (wires[read].api_name, {"id":"fixture"})]
        offered = []
        async def completion(messages, system, tools):
            index = len(offered)
            offered.append([t["name"] if mode == "Claude" else t["function"]["name"] for t in tools])
            if index == len(calls):
                if mode == "Claude":
                    yield {"type":"text_delta","text":"已讀回"}
                    yield {"type":"message_stop"}
                else:
                    yield "已讀回"
                return
            name, args = calls[index]
            if mode == "Claude":
                yield {"type":"tool_use_complete","data":{"name":name,"id":str(index),"input":args}}
                yield {"type":"message_stop"}
            else:
                yield [ToolCallObject(id=str(index), function=ToolCallFunctionObject(name,json.dumps(args)))]

        agent = BasicMemoryAgent.__new__(BasicMemoryAgent)
        agent._tool_manager, agent._tool_executor = manager, executor
        agent._system, agent.prompt_mode_flag = "fixture", False
        agent._llm = SimpleNamespace(chat_completion=completion)
        agent._compose_tool_system_prompt = lambda *args: "fixture"
        agent._add_message = Mock()
        loop = agent._claude_tool_interaction_loop if mode == "Claude" else agent._openai_tool_interaction_loop
        events = [event async for event in loop([], [])]
        self.assertEqual(offered[0], [DISCOVERY])
        self.assertEqual(offered[2], [DISCOVERY, wires[write].api_name])
        self.assertEqual(offered[-1], [DISCOVERY, wires[read].api_name])
        outcomes = [e.get("outcome") for e in events if isinstance(e, dict) and e.get("outcome")]
        self.assertEqual(outcomes, ["schema_invalid", "result_unknown", "result_unknown", "actual_success"])
        self.assertEqual([c.kwargs["tool_name"] for c in client.call_tool.await_args_list],
                         ["english_record_practice", "english_get_practice_session"])
        self.assertIn("已讀回", events)

    async def test_openai_recovery_and_schema_switch(self):
        await self.replay("OpenAI")

    async def test_claude_recovery_and_schema_switch(self):
        await self.replay("Claude")

    def test_owner_rejection_even_without_protocol_error_flag(self):
        response = Mock()
        response.model_dump.return_value = {"structuredContent": {"ok": False, "error": "WRITE_POLICY_DENIED"}}
        result = normalize_result(response, server_id="project-workspace")
        self.assertTrue(result.is_error)
        self.assertEqual(result.reason_code, "source_auth_denied")

    async def test_readonly_wire_failure_reasons(self):
        service, wire = "english-study", "english_get_summary"
        name = service + "::" + wire
        info = FormattedTool({"type": "object"}, service, canonical_id=name, wire_name=wire, read_only=True)
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile = "openai_non_strict"
        mapping = {name: info}
        openai, claude = adapter.format_tools_for_api(mapping)
        client = AsyncMock()
        executor = ToolExecutor(client, ToolManager(openai, claude, mapping))
        for reason, expected in [("timeout", "timeout"), ("transport_offline", "transport_offline"),
                                 ("source_auth_denied", "policy_denied")]:
            with self.subTest(reason=reason):
                client.call_tool.return_value = ToolResult(status="unknown" if reason == "timeout" else "failed",
                    reason_code=reason, is_error=True, result_received=False)
                events = [event async for event in executor.execute_tools(
                    [{"id":"fixture","name":info.api_name,"input":{}}], "OpenAI")]
                self.assertEqual(events[-2]["outcome"], expected)
