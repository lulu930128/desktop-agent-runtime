"""Offline regression for 2026-10-31 input[2].content[0].type failure."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
from test_gpt6_responses_routing import FakeStream, evt


def fixture():
    # Same typed content contract emitted by BasicMemoryAgent._to_messages.
    return [
        {"role": "user", "content": "synthetic history"},
        {"role": "assistant", "content": [{"type": "text", "text": "reply"}]},
        {"role": "user", "content": [
            {"type": "text", "text": "synthetic current turn"},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64,AA==", "detail": "auto"}},
            {"type": "text", "text": "after image"}]},
    ]


class ContentMapping(unittest.IsolatedAsyncioTestCase):
    async def test_20261031_input_2_content_0_type_actual_create(self):
        messages = fixture()
        before = copy.deepcopy(messages)
        llm = AsyncLLM("gpt-6-luna", "https://api.openai.com/v1", "fake-key")
        await llm.client.close()
        stream = FakeStream([evt("response.output_text.delta", delta="first"),
                             evt("response.output_text.delta", delta="second")])
        create = AsyncMock(return_value=stream)
        llm.client = NS(responses=NS(create=create))
        result = [x async for x in llm.chat_completion(messages, "synthetic system", tools=[])]
        self.assertEqual(result, ["first", "second"])
        params = create.call_args.kwargs
        items = params["input"]
        self.assertEqual(items[2]["content"][0], {
            "type": "input_text", "text": "synthetic current turn"})
        self.assertEqual(items[2]["content"][1], {
            "type": "input_image", "image_url": "data:image/png;base64,AA==", "detail": "auto"})
        self.assertEqual(items[2]["content"][2]["text"], "after image")
        self.assertEqual(items[1]["content"], [
            {"type": "output_text", "text": "reply", "annotations": []}])
        for item in items:
            if isinstance(item.get("content"), list):
                for block in item["content"]:
                    self.assertIn(block["type"], {"input_text", "input_image", "output_text"})
        self.assertEqual(messages, before)
        self.assertFalse(params["store"])
        self.assertTrue(params["stream"])
        self.assertTrue(stream.closed)

    def test_roles_multiturn_and_tool_content(self):
        messages = [{"role": role, "content": [{"type": "text", "text": role}]}
                    for role in ("system", "developer", "user", "assistant")]
        messages += [{"role": "assistant", "content": [{"type": "text", "text": "calling"}],
                      "tool_calls": [{"id": "call_fixture", "function": {
                          "name": "fixture_tool", "arguments": "{}"}}]},
                     {"role": "tool", "tool_call_id": "call_fixture", "content": "result"},
                     {"role": "user", "content": "next turn"}]
        items = AsyncLLM._responses_input(messages)
        self.assertEqual([i["content"][0]["type"] for i in items[:5]],
                         ["input_text"] * 3 + ["output_text"] * 2)
        self.assertEqual(items[5]["call_id"], items[6]["call_id"])
        self.assertEqual(items[5]["type"], "function_call")
        self.assertEqual(items[6]["type"], "function_call_output")
        self.assertEqual(items[7]["content"], "next turn")

    def test_unknown_blocks_fail_without_payload(self):
        for block in ({"type": "private-secret-type", "text": "private-payload"}, "private-payload"):
            with self.assertRaisesRegex(ValueError, "block type .unknown.") as raised:
                AsyncLLM._responses_input([{"role": "user", "content": [block]}])
            self.assertNotIn("private", str(raised.exception))

    async def test_chat_model_keeps_original_typed_blocks(self):
        llm = AsyncLLM("chat-model", "https://example.invalid/v1", "fake-key")
        await llm.client.close()
        create = AsyncMock(return_value=FakeStream([]))
        llm.client = NS(chat=NS(completions=NS(create=create)))
        messages = fixture()
        _ = [x async for x in llm.chat_completion(messages, None, tools=[])]
        self.assertEqual(create.call_args.kwargs["messages"], messages)
        self.assertEqual(messages[2]["content"][0]["type"], "text")


if __name__ == "__main__":
    unittest.main()
