"""Offline kuro-web fixtures; no production runtime, credentials or HTTP calls."""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_mcp"))
import web_fetch as transport
import web_evidence as evidence
import web_tools_server as web


PUBLIC = "93.184.216.34"
PUBLIC6 = "2606:4700:4700::1111"


def dns(ip=PUBLIC):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


def response(body=b"<html><main>Fixture evidence</main></html>", *, status=200, headers=None):
    fields = {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(body)), "Connection": "close"}
    fields.update(headers or {})
    return (f"HTTP/1.1 {status} Fixture\r\n" + "".join(f"{key}: {value}\r\n" for key, value in fields.items()) + "\r\n").encode() + body


class WireStream:
    def __init__(self, wire, peer=PUBLIC, port=443):
        self.wire, self.peer, self.port = wire, peer, port
        self.writes = []
        self.tls = []
        self.closed = False

    async def read(self, max_bytes, timeout=None):
        chunk, self.wire = self.wire[:max_bytes], self.wire[max_bytes:]
        return chunk

    async def write(self, data, timeout=None):
        self.writes.append(data)

    async def aclose(self):
        self.closed = True

    async def start_tls(self, ssl_context, server_hostname, timeout=None):
        self.tls.append((server_hostname, ssl_context.check_hostname, ssl_context.verify_mode))
        return self

    def get_extra_info(self, name):
        if name == "server_addr":
            return self.peer, self.port
        return False if name == "is_readable" else None


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.resolver = self.stack.enter_context(patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=dns())))
        self.connector = self.stack.enter_context(patch.object(transport.httpcore.AnyIOBackend, "connect_tcp", AsyncMock()))
        self.stack.enter_context(patch.object(transport, "_requests", transport.WindowQuota(60)))
        self.stack.enter_context(patch.object(transport, "_brave_requests", transport.WindowQuota(2)))
        self.stack.enter_context(patch.object(transport, "_slots", asyncio.Semaphore(4)))
        self.streams = []

    def wire(self, *responses, peer=PUBLIC, port=443):
        self.streams = [WireStream(row, peer, port) for row in responses]
        self.connector.side_effect = list(self.streams)

    async def blocked(self, url, reason, **kwargs):
        with self.assertRaisesRegex(transport.FetchBlocked, reason):
            await transport.fetch_text(url, **kwargs)

    async def test_pins_numeric_tcp_and_preserves_host_tls(self):
        self.wire(response())
        result = await transport.fetch_text("https://public.example/article")
        self.assertIn("Fixture evidence", result.text)
        self.assertEqual(self.connector.await_args.args, (PUBLIC, 443))
        self.assertEqual(self.resolver.await_count, 1)
        self.assertEqual(self.streams[0].tls, [("public.example", True, ssl.CERT_REQUIRED)])
        self.assertIn(b"Host: public.example\r\n", b"".join(self.streams[0].writes))
        self.assertTrue(self.streams[0].closed)

    async def test_public_ipv6_and_plain_http(self):
        self.resolver.return_value = dns(PUBLIC6)
        self.wire(response(), peer=PUBLIC6)
        await transport.fetch_text("https://v6.example/")
        self.assertEqual(self.connector.await_args.args, (PUBLIC6, 443))
        self.wire(response(), port=80)
        self.resolver.return_value = dns()
        await transport.fetch_text("http://public.example/")
        self.assertFalse(self.streams[0].tls)

    async def test_private_literal_ipv4_ipv6_and_special_ranges(self):
        for ip in ("127.0.0.1", "10.2.3.4", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0",
                   "100.64.0.1", "192.0.0.9", "192.0.2.1", "224.0.0.1", "255.255.255.255",
                   "::1", "::", "fc00::1", "fe80::1", "ff02::1", "2001:db8::1", "::ffff:127.0.0.1",
                   "64:ff9b::a00:1", "2002:7f00:1::1", "3fff::1"):
            with self.subTest(ip=ip):
                host = f"[{ip}]" if ":" in ip else ip
                await self.blocked(f"https://{host}/", "non_public_ip")
        self.connector.assert_not_awaited()

    async def test_private_dns_mixed_answers_and_obfuscated_numeric(self):
        for host in ("public.example", "127.1", "0x7f000001", "2130706433"):
            self.resolver.return_value = dns() + dns("127.0.0.1")
            with self.assertRaises(transport.FetchBlocked):
                await transport.fetch_text("https://" + host)
        self.connector.assert_not_awaited()

    async def test_rebinding_never_reconnects_original_hostname(self):
        self.resolver.side_effect = [dns(), dns("127.0.0.1")]
        self.wire(response())
        await transport.fetch_text("https://public.example/")
        self.assertEqual(self.resolver.await_count, 1)
        self.assertEqual(self.connector.await_args.args[0], PUBLIC)
        await self.blocked("https://public.example/again", "non_public_ip")
        self.assertEqual(self.connector.await_count, 1)

    async def test_private_or_wrong_peer_fails_before_tls_or_http(self):
        for peer in ("127.0.0.1", "1.1.1.1", None):
            self.wire(response(), peer=peer)
            with self.assertRaises((transport.FetchBlocked, ValueError)):
                await transport.fetch_text("https://public.example/")
            self.assertFalse(self.streams[0].writes)
            self.assertFalse(self.streams[0].tls)
            self.assertTrue(self.streams[0].closed)

    async def test_redirect_revalidates_private_host_and_dns(self):
        self.wire(response(status=302, headers={"Location": "https://127.0.0.1/secret"}))
        await self.blocked("https://public.example/", "non_public_ip")
        self.assertEqual(self.connector.await_count, 1)
        self.resolver.side_effect = [dns(), dns("10.0.0.1")]
        self.wire(response(status=302, headers={"Location": "https://rebound.example/"}))
        await self.blocked("https://public.example/", "non_public_ip")
        self.assertEqual(self.connector.await_count, 2)

    async def test_same_hostname_redirect_resolves_again(self):
        self.resolver.side_effect = [dns(), dns("::1")]
        self.wire(response(status=302, headers={"Location": "/next"}))
        await self.blocked("https://public.example/", "non_public_ip")
        self.assertEqual(self.resolver.await_count, 2)
        self.assertEqual(self.connector.await_count, 1)

    async def test_redirect_loop_limit_and_downgrade(self):
        self.wire(response(status=302, headers={"Location": "/"}))
        await self.blocked("https://public.example/", "redirect_loop")
        self.wire(*(response(status=302, headers={"Location": f"/{i}"}) for i in range(4)))
        await self.blocked("https://public.example/start", "redirect_limit")
        self.wire(response(status=302, headers={"Location": "http://public.example/"}))
        await self.blocked("https://public.example/", "https_downgrade_blocked")

    async def test_redirect_success_closes_hops_and_reports_final_url(self):
        self.wire(response(status=302, headers={"Location": "/article"}), response())
        result = await transport.fetch_text("https://public.example/")
        self.assertEqual(result.final_url, "https://public.example/article")
        self.assertTrue(all(s.closed for s in self.streams))

    async def test_oversized_declared_and_streamed_chunked_bodies(self):
        self.wire(response(headers={"Content-Length": str(transport.MAX_BYTES + 1)}))
        await self.blocked("https://public.example/", "response_too_large")
        body = b"x" * (transport.MAX_BYTES + 1)
        wire = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nTransfer-Encoding: chunked\r\n\r\n" + hex(len(body))[2:].encode() + b"\r\n" + body + b"\r\n0\r\n\r\n"
        self.wire(wire)
        await self.blocked("https://public.example/", "response_too_large")
        self.assertTrue(self.streams[0].closed)

    async def test_content_types_encoding_status_and_ambiguous_headers(self):
        for mime in ("application/pdf", "application/json", "image/png", "application/octet-stream", ""):
            self.wire(response(headers={"Content-Type": mime}))
            await self.blocked("https://public.example/", "unsupported_content_type")
        self.wire(response(headers={"Content-Encoding": "gzip"}))
        await self.blocked("https://public.example/", "compressed_content_blocked")
        self.wire(response(status=403))
        await self.blocked("https://public.example/", "http_status_unavailable")
        self.wire(response(headers={"content-type": "application/pdf"}))
        await self.blocked("https://public.example/", "ambiguous_response_headers")

    async def test_proxy_and_ca_environment_are_not_used(self):
        self.wire(response())
        with patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
                                       "ALL_PROXY": "http://127.0.0.1:9", "SSL_CERT_FILE": "nonexistent-fixture.pem"}):
            await transport.fetch_text("https://public.example/")
        self.assertEqual(self.connector.await_args.args, (PUBLIC, 443))
        self.assertIn(b"GET / HTTP/1.1", b"".join(self.streams[0].writes))

    async def test_credentials_only_fixed_provider_and_no_redirect_leak(self):
        await self.blocked("https://other.example/", "credential_target_blocked", api_key="synthetic-fixture")
        self.connector.assert_not_awaited()
        self.wire(response(status=302, headers={"Location": "https://other.example/"}))
        await self.blocked(transport.BRAVE_ENDPOINT, "provider_redirect_blocked", api_key="synthetic-fixture")
        self.assertEqual(self.connector.await_count, 1)

    async def test_invalid_urls_block_without_connect(self):
        for url in ("file:///x", "ftp://public.example/x", "https://localhost./", "https://x.local/",
                    "https://u:p@public.example/", "https://public.example:444/", "https://public.example/\r\nx",
                    "https://[fe80::1%25eth0]/", "https://public.example\\@127.0.0.1/"):
            with self.subTest(url=url), self.assertRaises(transport.FetchBlocked):
                await transport.fetch_text(url)
        self.connector.assert_not_awaited()

    async def test_timeout_and_cancellation_close_stream(self):
        self.wire(response())
        self.streams[0].read = AsyncMock(side_effect=lambda *a, **k: None)
        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
        self.streams[0].read = slow
        with self.assertRaises((TimeoutError, asyncio.TimeoutError)):
            await transport.fetch_text("https://public.example/", timeout=.03)
        self.assertTrue(self.streams[0].closed)
        self.wire(response())
        self.streams[0].read = slow
        task = asyncio.create_task(transport.fetch_text("https://public.example/"))
        await asyncio.sleep(.03)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.streams[0].closed)

    async def test_dns_timeout_is_bounded(self):
        async def slow(*a, **k):
            await asyncio.sleep(10)
        self.resolver.side_effect = slow
        with self.assertRaises((TimeoutError, asyncio.TimeoutError)):
            await transport.fetch_text("https://public.example/", timeout=.02)
        self.connector.assert_not_awaited()

    async def test_quotas_and_concurrency(self):
        with patch.object(transport, "_requests", transport.WindowQuota(0)):
            await self.blocked("https://public.example/", "request_quota_exhausted")
        token = transport.budget.set(transport.ResearchBudget(hops=0))
        try:
            await self.blocked("https://public.example/", "operation_hop_quota_exhausted")
        finally:
            transport.budget.reset(token)
        active = peak = 0
        async def connect(host, port, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            await asyncio.sleep(.02)
            active -= 1
            return WireStream(response())
        self.connector.side_effect = connect
        await asyncio.gather(*(transport.fetch_text(f"https://public.example/{i}") for i in range(9)))
        self.assertEqual(peak, 4)

    async def test_brave_json_is_bounded_and_rate_limited(self):
        self.wire(response(b'{"web":{"results":[]}}', headers={"Content-Type": "application/json"}),
                  response(b'{}', headers={"Content-Type": "application/json"}))
        for _ in range(2):
            result = await transport.fetch_text(transport.BRAVE_ENDPOINT, api_key="synthetic-fixture")
            self.assertEqual(result.content_type, "application/json")
        await self.blocked(transport.BRAVE_ENDPOINT, "request_quota_exhausted", api_key="synthetic-fixture")
        self.assertEqual(self.connector.await_count, 2)

    async def test_unavailable_pinning_api_is_fail_closed(self):
        self.connector.side_effect = RuntimeError("backend unavailable")
        with self.assertRaises(RuntimeError):
            await transport.fetch_text("https://public.example/")
        self.assertEqual(self.connector.await_args.args[0], PUBLIC)
        self.assertEqual(self.connector.await_count, 1)

    async def test_queue_deadline_and_budget_reset(self):
        with patch.object(transport, "_slots", asyncio.Semaphore(0)):
            with self.assertRaises(TimeoutError):
                await transport.fetch_text("https://public.example/", timeout=.02)
        self.connector.assert_not_awaited()
        @transport.bounded_research
        async def nested():
            self.assertIsNotNone(transport.budget.get())
            raise TimeoutError()
        self.assertIn("operation_timeout", await nested())
        self.assertIsNone(transport.budget.get())


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.http = self.stack.enter_context(patch.object(web, "fetch_text", AsyncMock(side_effect=AssertionError("Unexpected network"))))
        self.ddg = self.stack.enter_context(patch.object(web, "_search_ddg", AsyncMock(return_value=[])))
        self.stack.enter_context(patch.object(web, "_brave", web.BraveConfiguration()))

    def enable_brave(self):
        self.stack.enter_context(patch.object(web, "_brave", web.BraveConfiguration(True, "synthetic-fixture")))
        self.http.side_effect = None
        self.http.return_value = transport.FetchResponse(json.dumps({"web": {"results": [{"url": "https://brave-result.example/a", "title": "API result", "description": "Excerpt"}]}}), transport.BRAVE_ENDPOINT, "application/json")

    async def test_ddg_success_never_calls_brave_even_opted_in(self):
        self.enable_brave()
        self.ddg.return_value = [{"url": "https://public.example/", "title": "DDG", "snippet": "Fixture"}]
        rows = await web._search_once("fixture", 5)
        self.assertEqual(rows[0]["provider"], "duckduckgo_html")
        self.http.assert_not_awaited()

    async def test_no_key_or_disabled_keeps_ddg_and_returns_unavailable(self):
        for config in (web.BraveConfiguration(), web.BraveConfiguration(True, ""), web.BraveConfiguration(False, "synthetic")):
            with patch.object(web, "_brave", config):
                rows = await web._search_once("fixture", 5)
                self.assertEqual(rows.statuses[-1]["reason"], "not_configured")
        self.http.assert_not_awaited()

    async def test_fetch_rejected_authority_never_echoes_userinfo(self):
        for url in ("https://user:synthetic-private-value@public.example/", "https://[invalid", "file:///fixture"):
            text = await web.fetch_content(url)
            self.assertTrue(text.startswith("Fetch error:"))
            self.assertNotIn("synthetic-private-value", text)
        self.http.assert_not_awaited()

    async def test_ddg_zero_and_failure_use_same_bounded_fallback(self):
        self.enable_brave()
        for failure in (None, RuntimeError("must-not-echo-private-provider-error")):
            self.ddg.side_effect = failure
            rows = await web._search_once("fixture", 5)
            self.assertEqual(rows[0]["provider"], "brave_api")
            self.assertNotIn("must-not-echo", str(rows.statuses))
            self.assertEqual(self.http.await_args.args[0], transport.BRAVE_ENDPOINT)
            self.assertEqual(self.http.await_args.kwargs["params"], {"q": "fixture", "count": 5})

    async def test_fallback_failure_and_malformed_schema_degrade(self):
        self.enable_brave()
        for body in ("bad json", "[]", '{"web": null}', '{"web":{"results":{}}}'):
            self.http.return_value = transport.FetchResponse(body, transport.BRAVE_ENDPOINT, "application/json")
            rows = await web._search_once("fixture", 5)
            self.assertEqual(rows, [])
            self.assertEqual(rows.statuses[-1]["status"], "unavailable")

    async def test_shared_fallback_query_quota(self):
        self.enable_brave()
        token = transport.budget.set(transport.ResearchBudget())
        try:
            batches = await asyncio.gather(*(web._search_once(f"q{i}", 5) for i in range(8)))
            self.assertEqual(self.http.await_count, 2)
            self.assertEqual(sum(bool(batch) for batch in batches), 2)
        finally:
            transport.budget.reset(token)

    async def test_ddg_parser_relative_redirect_and_duplicate_canonical(self):
        html = '''<div class="result"><h2 class="result__title"><a href="/l/?uddg=https%3A%2F%2Fpublic.example%2Fa%3Futm_source%3Dtest">One</a></h2><div class="result__snippet">Text</div></div>
        <div class="result"><h2 class="result__title"><a href="https://public.example/a">Duplicate</a></h2></div>
        <div class="result"><h2 class="result__title"><a href="http://127.0.0.1/">Private</a></h2></div>'''
        with patch.object(web, "_get_text", AsyncMock(return_value=html)):
            rows = await ORIGINAL_DDG("fixture", 5)
        normalized = web._provider_rows(rows, "duckduckgo_html", web.SearchQuery("fixture", 5))
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["canonical_url"], "https://public.example/a")

    async def test_depth_caps_and_query_size(self):
        fixture = [{"url": f"https://public.example/{i}", "title": "Fixture", "snippet": "Evidence"} for i in range(10)]
        self.ddg.return_value = fixture
        with patch.object(web, "_fetch_snapshot", AsyncMock(return_value={"content": "body", "error": ""})) as fetch:
            for depth, queries, pages in (("fast", 3, 0), ("normal", 5, 2), ("deep", 8, 4)):
                self.ddg.reset_mock()
                fetch.reset_mock()
                await web.advanced_search_web("latest official API documentation comparison", depth=depth, fetch_top_pages=99, max_results=10)
                self.assertLessEqual(self.ddg.await_count, queries)
                self.assertEqual(fetch.await_count, pages)
        with self.assertRaisesRegex(transport.FetchBlocked, "query_size_limit"):
            await web._search_once("x" * 601, 5)

    async def test_five_tools_mock_call_and_string_compatibility(self):
        self.ddg.return_value = [{"url": "https://public.example/", "title": "Fixture", "snippet": "Evidence"}]
        self.http.side_effect = None
        self.http.return_value = transport.FetchResponse("<main>Body evidence</main>", "https://public.example/", "text/html")
        tools = await web.mcp.list_tools()
        expected = {"search_web", "smart_search_web", "advanced_search_web", "fetch_content", "get_current_time"}
        self.assertEqual({t.name for t in tools}, expected)
        args = {"search_web": {"query": "fixture"}, "smart_search_web": {"question": "fixture"},
                "advanced_search_web": {"question": "fixture"}, "fetch_content": {"url": "https://public.example/"}, "get_current_time": {}}
        for name in expected:
            result = await web.mcp.call_tool(name, args[name])
            # MCP 1.15 returns legacy TextContent plus its original string result.
            text = str(result)
            self.assertTrue(text)
            if name != "get_current_time":
                self.assertIn("kuro.web.evidence.v1", text)

    async def test_opt_in_does_not_read_key_when_disabled_or_log_key(self):
        class Guarded(dict):
            def get(self, name, default=None):
                if name.endswith("API_KEY"):
                    raise AssertionError("Credential access without opt-in")
                return super().get(name, default)
        self.assertFalse(web.BraveConfiguration.from_environment(Guarded()).enabled)
        self.assertNotIn("synthetic-key", repr(web.BraveConfiguration(True, "synthetic-key")))

    async def test_unexpanded_or_invalid_key_disables_fallback_without_io(self):
        for key in ("", "%KURO_WEB_BRAVE_API_KEY%", "$KURO_WEB_BRAVE_API_KEY",
                    "${KURO_WEB_BRAVE_API_KEY}", "prefix-%MISSING%-suffix",
                    "prefix-${MISSING}-suffix", " ", "invalid\nvalue", "x" * 2049):
            with self.subTest(case="empty/placeholder/invalid"):
                config = web.BraveConfiguration.from_environment({"KURO_WEB_BRAVE_ENABLED": "1", "KURO_WEB_BRAVE_API_KEY": key})
                self.assertFalse(config.enabled)
                self.assertFalse(config.api_key)
                with patch.object(web, "_brave", config):
                    result = await web._search_once("fixture", 5)
                self.assertEqual(result.statuses[-1]["reason"], "not_configured")
        self.http.assert_not_awaited()

    async def test_five_canonical_tools_adapter_policy_and_executor_dispatch(self):
        from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
        from open_llm_vtuber.mcpp.tool_manager import ToolManager
        from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
        from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog
        from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
        from open_llm_vtuber.mcpp.tool_result import ToolResult
        from open_llm_vtuber.mcpp.types import FormattedTool
        root = Path(__file__).resolve().parents[1]
        discovered = await web.mcp.list_tools()
        raw = {f"kuro-web::{tool.name}": FormattedTool(tool.inputSchema, "kuro-web", canonical_id=f"kuro-web::{tool.name}",
               wire_name=tool.name, output_schema=tool.outputSchema) for tool in discovered}
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile = "openai_non_strict"
        openai, claude = adapter.format_tools_for_api(raw)
        self.assertFalse(adapter.schema_errors)
        self.assertEqual(len(openai), 5)
        self.assertEqual(len(claude), 5)
        client = AsyncMock()
        client.call_tool.return_value = ToolResult(content_items=[{"type": "text", "text": "offline fixture"}])
        executor = ToolExecutor(client, ToolManager(openai, claude, raw))
        executor._tool_policy = ToolPolicy(json.loads((root / "tool_policy.json").read_text(encoding="utf-8")))
        arguments = {"search_web": {"query": "fixture"}, "smart_search_web": {"question": "fixture"},
                     "advanced_search_web": {"question": "fixture"}, "fetch_content": {"url": "https://public.example/"}, "get_current_time": {}}
        for name, args in arguments.items():
            error, *_ = await executor.run_single_tool("kuro-web::" + name, "fixture", args)
            self.assertFalse(error, name)
            self.assertEqual(client.call_tool.await_args.kwargs["server_name"], "kuro-web")
            self.assertEqual(client.call_tool.await_args.kwargs["tool_name"], name)
        catalog = ToolCatalog.load_default()
        for power in ("fast", "normal", "deep"):
            route = catalog.route("search public web sources", list(raw), thinking_power=power)
            self.assertTrue(route.tool_names)
            self.assertTrue(set(route.tool_names).issubset(raw))
            executor._thinking_power = power
            shaped = executor._apply_thinking_power("kuro-web::advanced_search_web", {"question": "fixture"})
            self.assertEqual(shaped["depth"], power)
        self.assertEqual(client.call_tool.await_count, 5)


ORIGINAL_DDG = web._search_ddg


# Runs the real server __main__/FastMCP entrypoint in a disposable STDIO child.
# All provider I/O is replaced before entry; only synthetic env is delivered.
STDIO_ENV_CHILD = '''
import json
from pathlib import Path
import runpy
import sys
sys.path.insert(0, sys.argv[1])
import web_fetch

async def no_tcp(*args, **kwargs):
    raise AssertionError("Network forbidden in env fixture")

async def fake_fetch(url, *, params=None, api_key=None, **kwargs):
    if url == web_fetch.BRAVE_ENDPOINT:
        if api_key != "synthetic-brave-only":
            raise AssertionError("Invalid fixture credential")
        text = json.dumps({"web": {"results": [{"url": "https://fixture.example/", "title": "Opt-in fixture", "description": "Synthetic child evidence"}]}})
        return web_fetch.FetchResponse(text, url, "application/json")
    if url == "https://html.duckduckgo.com/html/":
        return web_fetch.FetchResponse("<html></html>", url, "text/html")
    raise AssertionError("Unexpected fixture target")

web_fetch.PublicNetworkBackend.connect_tcp = no_tcp
web_fetch.fetch_text = fake_fetch
runpy.run_path(str(Path(sys.argv[1]) / "web_tools_server.py"), run_name="__main__")
'''


class BraveStdioEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    async def check_child(self, parent_values, *, registry_env, expected_enabled):
        from mcp.client.stdio import get_default_environment
        from open_llm_vtuber.mcpp.server_registry import ServerRegistry
        from open_llm_vtuber.mcpp.mcp_client import MCPClient
        root = Path(__file__).resolve().parents[1]
        # Read only the SDK's basic OS allowlist, never ambient Brave variables.
        synthetic = {**get_default_environment(), **parent_values}
        with tempfile.TemporaryDirectory(prefix="kuro-web-env-") as directory:
            directory = Path(directory)
            child = directory / "fixture_child.py"
            child.write_text(STDIO_ENV_CHILD, encoding="utf-8")
            entry = {"command": sys.executable, "args": [str(child), str(root / "local_mcp")],
                     "cwd": str(directory), "timeout": 10}
            if registry_env:
                entry["env"] = {name: "%" + name + "%" for name in ("KURO_WEB_BRAVE_ENABLED", "KURO_WEB_BRAVE_API_KEY")}
            registry_path = directory / "registry.json"
            registry_path.write_text(json.dumps({"mcp_servers": {"kuro-web": entry}}), encoding="utf-8")
            self.assertNotIn("synthetic-brave-only", registry_path.read_text(encoding="utf-8"))
            with patch("os.environ", synthetic), patch("mcp.client.stdio._terminate_process_tree",
                    AsyncMock(side_effect=AssertionError("Fixture must exit on EOF"))) as terminate:
                self.assertNotIn("KURO_WEB_BRAVE_ENABLED", get_default_environment())
                self.assertNotIn("KURO_WEB_BRAVE_API_KEY", get_default_environment())
                registry = ServerRegistry(registry_path)
                async with MCPClient(registry) as client:
                    discovered = await client.discover_tools("kuro-web")
                    self.assertTrue(discovered.complete)
                    expected = await web.mcp.list_tools()
                    self.assertEqual([t.model_dump(mode="json") for t in discovered.tools],
                                     [t.model_dump(mode="json") for t in expected])
                    result = await client.call_tool("kuro-web", "search_web", {"query": "fixture"})
                    self.assertFalse(result.is_error)
                    text = result.model_text()
                    self.assertNotIn("synthetic-brave-only", text)
                    payload = json.loads(result.text_blocks[0].split("observations):\n", 1)[1])
                    status = payload["provider_status"][-1]
                    self.assertEqual(status["provider"], "brave_api")
                    if expected_enabled:
                        self.assertEqual(status["status"], "ok")
                    else:
                        self.assertEqual(status["reason"], "not_configured")
                terminate.assert_not_awaited()

    async def test_parent_only_environment_does_not_opt_in_child(self):
        await self.check_child({"KURO_WEB_BRAVE_ENABLED": "1", "KURO_WEB_BRAVE_API_KEY": "synthetic-brave-only"},
                               registry_env=False, expected_enabled=False)

    async def test_registry_placeholders_deliver_only_explicit_complete_opt_in(self):
        for values, enabled in (({"KURO_WEB_BRAVE_ENABLED": "1", "KURO_WEB_BRAVE_API_KEY": "synthetic-brave-only"}, True),
                                ({"KURO_WEB_BRAVE_ENABLED": "1"}, False),
                                ({"KURO_WEB_BRAVE_API_KEY": "synthetic-brave-only"}, False),
                                ({"KURO_WEB_BRAVE_ENABLED": "0", "KURO_WEB_BRAVE_API_KEY": "synthetic-brave-only"}, False)):
            with self.subTest(enabled=enabled, names=sorted(values)):
                await self.check_child(values, registry_env=True, expected_enabled=enabled)


class EvidenceTests(unittest.TestCase):
    def test_search_only_has_observation_time_but_no_fetch_time(self):
        observed = "2026-10-26T01:00:00+00:00"
        result = evidence.evidence_for({"url": "https://fixture.example/", "observations": [{"observed_at": observed}]})
        self.assertEqual(result["search_observed_at"], observed)
        self.assertIsNone(result["body_fetched_at"])
        self.assertIsNone(result["fetched_at"])

    def test_successful_fetch_keeps_search_and_body_times_separate(self):
        observed, fetched = "2026-10-26T01:00:00+00:00", "2026-10-26T01:01:00+00:00"
        result = evidence.evidence_for({"url": "https://fixture.example/", "observations": [{"observed_at": observed}],
                                      "fetched": {"content": "Body", "fetched_at": fetched, "error": ""}})
        self.assertEqual(result["search_observed_at"], observed)
        self.assertEqual(result["body_fetched_at"], fetched)
        self.assertEqual(result["fetched_at"], fetched)
        direct = evidence.evidence_for({"url": "https://fixture.example/", "fetched": {"content": "Body", "fetched_at": fetched}})
        self.assertIsNone(direct["search_observed_at"])
        self.assertEqual(direct["body_fetched_at"], fetched)

    def test_failed_fetch_never_falls_back_to_search_or_error_timestamp(self):
        observed = "2026-10-26T01:00:00+00:00"
        for attempted_at in (None, "2026-10-26T01:01:00+00:00"):
            result = evidence.evidence_for({"url": "https://fixture.example/", "observations": [{"observed_at": observed}],
                                          "fetched": {"error": "fetch_timeout", "fetched_at": attempted_at}})
            self.assertEqual(result["search_observed_at"], observed)
            self.assertIsNone(result["body_fetched_at"])
            self.assertIsNone(result["fetched_at"])
            self.assertIn("body_fetch_failed", result["missing"])

    def test_main_extraction_metadata_and_no_updated_as_published(self):
        html = '''<html><head><title>Fixture title</title><meta name="description" content="Description">
        <meta property="og:updated_time" content="2020-01-02T00:00:00Z"></head><body>
        <nav>Navigation</nav><article><p>Evidence body.</p><p hidden>Hidden</p><script>bad()</script></article><footer>Footer</footer></body></html>'''
        snapshot = evidence.extract_snapshot("https://public.example/", html, 1000)
        self.assertEqual(snapshot["content"], "Evidence body.")
        self.assertEqual(snapshot["published_time"]["status"], "unknown")
        self.assertEqual(snapshot["modified_time_original"], "2020-01-02T00:00:00Z")
        self.assertTrue(snapshot["fetched_at"].endswith("+00:00"))

    def test_publication_original_validated_missing_invalid_future_timezone(self):
        for raw, status in (("2020-01-01", "date_only"), ("2020-01-01T08:00:00+08:00", "parsed"),
                            ("2020-01-01T00:00:00", "unknown"), ("nonsense", "unknown"), ("2999-01-01", "unknown")):
            value = evidence.published_time([{"value": raw, "source": "fixture"}])
            self.assertEqual(value["status"], status)
            self.assertEqual(value["original"], raw)
        self.assertEqual(evidence.published_time([])["status"], "unknown")

    def test_conflicting_dates_and_jsonld_with_precise_receipts(self):
        html = '''<meta property="article:published_time" content="2020-01-01T00:00:00Z">
        <script type="application/ld+json">{"@graph":[{"datePublished":"2021-01-01T00:00:00Z"}]}</script><article>Body</article>'''
        snapshot = evidence.extract_snapshot("https://public.example/", html, 1000)
        self.assertEqual(snapshot["published_time"]["status"], "conflicting")
        item = evidence.evidence_for({"url": "https://public.example/", "fetched": snapshot})
        self.assertEqual(item["conflicts"][0]["field"], "published_time")
        self.assertEqual(len(item["conflicts"][0]["evidence"]), 2)
        self.assertIsNone(item["published_time"]["validated"])

    def test_canonical_dedupe_preserves_semantic_url_parts(self):
        self.assertEqual(evidence.canonical_url("https://EXAMPLE.com:443/a?utm_source=x&x=1#top"), "https://example.com/a?x=1")
        for left, right in (("https://www.example.com/a", "https://example.com/a"),
                            ("https://example.com/a", "https://example.com/a/"),
                            ("https://example.com/?ref=a", "https://example.com/?ref=b")):
            self.assertNotEqual(evidence.canonical_url(left), evidence.canonical_url(right))

    def test_provider_merge_conflicting_excerpts_and_failed_body(self):
        a = {"url": "https://public.example/a?utm_source=x", "title": "Official", "snippet": "First excerpt", "provider": "duckduckgo_html"}
        b = {**a, "url": "https://public.example/a", "snippet": "Second excerpt", "provider": "brave_api"}
        merged = web._merge_results([("q1", [a]), ("q2", [b])], question="fixture")
        self.assertEqual(len(merged), 1)
        merged[0]["fetched"] = {"error": "fetch_timeout"}
        result = evidence.evidence_for(merged[0])
        self.assertEqual(result["provider"], ["duckduckgo_html", "brave_api"])
        self.assertEqual(result["verification"]["status"], "unsupported")
        self.assertEqual(result["verification"]["confidence"]["kind"], "heuristic")
        self.assertIn("body_fetch_failed", result["missing"])
        self.assertEqual(result["conflicts"][0]["status"], "conflicting")
        self.assertEqual(len(result["conflicts"][0]["evidence"]), 2)

    def test_identical_cross_domain_excerpt_is_not_independent_verification(self):
        rows = [{"url": f"https://{name}.example/", "snippet": "Same syndicated excerpt"} for name in ("a", "b")]
        text = evidence.evidence_appendix(rows, recency_days=1)
        payload = json.loads(text.split("observations):\n", 1)[1])
        self.assertFalse(payload["recency"]["filter_enforced"])
        self.assertEqual(payload["cross_source"][0]["independent_corroboration"], "unsupported")
        self.assertEqual(payload["cross_source"][0]["quote"], "Same syndicated excerpt")

    def test_long_body_is_bounded_and_declared_canonical_is_only_metadata(self):
        snapshot = evidence.extract_snapshot("https://public.example/article", '<link rel="canonical" href="http://127.0.0.1/"><article>' + "x" * 2000 + "</article>", 500)
        self.assertEqual(len(snapshot["content"]), 500)
        self.assertTrue(snapshot["content_truncated"])
        self.assertEqual(snapshot["canonical_url"], "https://public.example/article")

    def test_old_search_date_and_body_date_disagree_without_freshness_claim(self):
        snapshot = evidence.extract_snapshot("https://public.example/final", '<meta property="article:published_time" content="2021-01-01"><main>Body</main>', 500)
        result = evidence.evidence_for({"url": "https://public.example/start", "fetched": snapshot,
            "observations": [{"provider": "brave_api", "published_original": "2020-01-01", "observed_at": "2026-10-26T00:00:00+00:00"}]})
        self.assertEqual(result["published_time"]["status"], "conflicting")
        self.assertEqual(result["body_url"], "https://public.example/final")
        self.assertEqual(result["verification"]["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
