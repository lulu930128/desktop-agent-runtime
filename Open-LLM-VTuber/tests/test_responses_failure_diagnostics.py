"""Offline diagnostics regression; no network or credentials."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import httpx
from loguru import logger
from openai import APIError, APIConnectionError, BadRequestError, AuthenticationError, RateLimitError
from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM, _safe_failure_field
from test_gpt6_responses_routing import FakeStream, evt


class FailureDiagnostics(unittest.IsolatedAsyncioTestCase):
    async def run_failure(self, *, exc=None, events=None):
        llm = AsyncLLM("gpt-6-luna", "https://api.openai.com/v1", "fake-key")
        await llm.client.close()
        stream = FakeStream(events or [])
        create = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=stream)
        llm.client = NS(responses=NS(create=create))
        records = []
        sink = logger.add(lambda message: records.append(message.record))
        try:
            result = [x async for x in llm.chat_completion(
                [{"role": "user", "content": "private-prompt"}], "private-system", tools=[])]
        finally:
            logger.remove(sink)
        create.assert_awaited_once()
        self.assertTrue(llm.support_tools)
        if not exc:
            self.assertTrue(stream.closed)
        failures = [r for r in records if "llm_api_failure" in r["message"]]
        self.assertEqual(len(failures), 1)
        combined = str(result) + str(failures)
        for secret in ("sk-secret", "https://evil.example", "private-prompt", "private-system", "raw-secret"):
            self.assertNotIn(secret, combined)
        self.assertTrue(all(isinstance(x, str) for x in result))
        return result, failures[0]

    async def test_http_status_errors(self):
        request = httpx.Request("POST", "https://evil.example")
        for cls, status, category in ((BadRequestError, 400, "api_error"),
                                       (AuthenticationError, 401, "api_error"),
                                       (RateLimitError, 429, "rate_limit")):
            with self.subTest(status=status):
                exc = cls("sk-secret https://evil.example\nraw-secret", response=httpx.Response(
                    status, request=request, headers={"x-request-id": "req_safe123"}),
                    body={"type": "invalid_request_error", "code": "invalid_value", "param": "tools[0]",
                          "message": "raw-secret"})
                result, record = await self.run_failure(exc=exc)
                self.assertEqual(record["extra"]["status"], status)
                self.assertEqual(record["extra"]["category"], category)
                self.assertEqual(record["extra"]["type"], "invalid_request_error")
                self.assertEqual(record["extra"]["request_id"], "req_safe123")
                self.assertIn("param=tools[0]", result[0])

    async def test_connection_and_unknown_api_error(self):
        request = httpx.Request("POST", "https://evil.example")
        for exc, category in ((APIConnectionError(request=request, message="raw-secret"), "connection"),
                              (APIError("raw-secret", request=request, body=None), "api_error")):
            _, record = await self.run_failure(exc=exc)
            self.assertEqual(record["extra"]["category"], category)
            self.assertEqual(record["extra"]["status"], "unknown")
            self.assertEqual(record["extra"]["code"], "unknown")
            self.assertNotIn("request_id", record["extra"])

    async def test_stream_fail_incomplete_and_error_stop_tools(self):
        for kind in ("response.failed", "response.incomplete", "error"):
            with self.subTest(kind=kind):
                event = evt(kind, code="server_error", param="tools[0]", message="raw-secret",
                            response=NS(error=NS(code="server_error", type="server_error", param="tools[0]",
                                                 message="sk-secret https://evil.example\n"),
                                        incomplete_details=NS(reason="max_output_tokens")))
                result, record = await self.run_failure(events=[
                    evt("response.output_text.delta", delta="partial"),
                    evt("response.output_item.done", output_index=0,
                        item=evt("function_call", name="test", call_id="call_1", arguments="{}")),
                    event, evt("response.output_text.delta", delta="must-not-emit")])
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0], "partial")
                self.assertEqual(record["extra"]["category"], kind)
                self.assertEqual(record["extra"]["code"], "server_error")
                if kind != "error":
                    self.assertEqual(record["extra"]["reason"], "max_output_tokens")

    async def test_malicious_metadata_rejected(self):
        event = evt("error", code="sk-secret", param="https://evil.example", message="raw-secret")
        _, record = await self.run_failure(events=[event])
        for key in ("code", "type", "param", "reason"):
            self.assertEqual(record["extra"][key], "unknown")

    def test_field_shapes_and_bounds(self):
        for field in ("code", "type", "param", "request_id", "reason"):
            for value in (None, {}, [], 123, True, "x" * 129, "foo\nbar", "sk-secret", "https://evil.example", "Bearer_token"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(_safe_failure_field(value, field), "unknown")
        self.assertEqual(_safe_failure_field("tools[0].function.name", "param"), "tools[0].function.name")
        self.assertEqual(_safe_failure_field("tools[abc]", "param"), "unknown")


if __name__ == "__main__":
    unittest.main()
