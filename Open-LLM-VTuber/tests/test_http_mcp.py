"""Synthetic HTTP MCP wire tests. No production socket or domain handler is used."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import os
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from mcp.types import Tool
from open_llm_vtuber.mcpp import mcp_client as client_module
from open_llm_vtuber.mcpp.mcp_client import MCPClient, _http_client_factory
from open_llm_vtuber.mcpp.server_registry import (
    ServerRegistry, HTTP_ENDPOINTS, HTTP_SERVER_NAMES, HTTP_READ_TOOLS,
)
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_identity import provider_alias
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_schema import provider_schema, resolved_schema, schema_digest
from kuro_launcher.tool_policy_settings import CATALOG, GROUPS

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'Open-LLM-VTuber'
RECEIPTS = ROOT / 'docs/agent-runs/kuro-http-mcp-20261024'
METADATA = json.loads((RECEIPTS / 'LiveMetadata.json').read_text(encoding='utf-8'))
EVIDENCE = {}


def definition(server):
    return dict(transport='streamable_http', url=HTTP_ENDPOINTS[server], timeout=2,
                allowed_tools=list(HTTP_READ_TOOLS[server]), require_read_only=True)


def arguments(tool):
    values = {'query': 'synthetic', 'id': 'record:synthetic', 'record_ref': 'record:synthetic',
              'revision_no': 1, 'collection_key': 'synthetic'}
    return {key: values[key] for key in tool.inputSchema.get('required', [])}


class RegistryTests(unittest.TestCase):
    def registry(self, rows):
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as folder:
            path = Path(folder) / 'servers.json'
            path.write_text(json.dumps({'mcp_servers': rows}), encoding='utf-8')
            return ServerRegistry(path)

    def test_exact_endpoints_and_invalid_config_are_fail_closed(self):
        urls = ['https://127.0.0.1:18818/mcp', 'http://localhost:18818/mcp',
                'http://127.1:18818/mcp', 'http://2130706433:18818/mcp',
                'http://[::1]:18818/mcp', 'http://127.0.0.2:18818/mcp',
                'http://example.invalid:18818/mcp', 'http://127.0.0.1:18876/mcp/',
                'http://127.0.0.1:18818/', 'http://127.0.0.1:18818/mcp/',
                'http://user:pass@127.0.0.1:18818/mcp', 'http://127.0.0.1:18818/mcp?',
                'http://127.0.0.1:18818/mcp#', 'http://127.0.0.1:18818/mcp?q=1',
                'http://127.0.0.1:18818/%6dcp', ' http://127.0.0.1:18818/mcp',
                'http://127.0.0.1:18818/mcp\n', 'http://127.0.0.1:18818/x/../mcp',
                'http://127.0.0.1:18818/mcp#fragment', None, 1, [], {}]
        for url in urls:
            with self.subTest(url=url):
                row = {**definition('memory-core'), 'url': url}
                self.assertIsNone(self.registry({'memory-core': row}).get_server('memory-core'))
        bad = [{'transport': 'stdio'}, {'transport': 'sse'}, {'transport': None},
               {'require_read_only': False}, {'require_read_only': 'true'},
               {'allowed_tools': None}, {'allowed_tools': ['search']},
               {'allowed_tools': [*HTTP_READ_TOOLS['memory-core'], 'memory_approve_candidate']},
               {'headers': {}}, {'auth': None}, {'env': {}}, {'command': ''}, {'cwd': None}]
        for update in bad:
            with self.subTest(update=update):
                self.assertIsNone(self.registry({'memory-core': {**definition('memory-core'), **update}}).get_server('memory-core'))
        self.assertIsNone(self.registry({'unknown': definition('memory-core')}).get_server('unknown'))
        self.assertIsNotNone(self.registry({'memory-core': definition('memory-core')}).get_server('memory-core'))
        EVIDENCE['unsafe_config_cases'] = len(urls) + len(bad) + 1

    def test_formal_inventory_original_60_and_source_schemas(self):
        previous = json.loads((RECEIPTS / 'OriginalInventory.json').read_text(encoding='utf-8'))
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        current = json.loads((RUNTIME / 'mcp_servers.json').read_text(encoding='utf-8'))['mcp_servers']
        authoritative = set(ToolPolicy.load_default().owner_services)
        self.assertEqual(authoritative, {'project-workspace', 'omi-search', 'english-study', 'japanese-study', 'listening-audio'})
        for name in authoritative - {'project-workspace'}:
            self.assertEqual(current[name]['url'], HTTP_ENDPOINTS[name])
        self.assertNotIn('allowed_tools', current['project-workspace'])
        for key, value in previous['mcp_servers.json']['entries'].items():
            if key not in authoritative:
                self.assertEqual(digest(current[key]), value)
        policy = ToolPolicy.load_default()
        self.assertEqual(set(policy.tools), set(CATALOG))
        for server, names in HTTP_READ_TOOLS.items():
            rows = {t['name']: Tool.model_validate(t) for t in METADATA[server]['tools']}
            self.assertTrue(METADATA[server]['complete'])
            if server in current:  # Local role may name an unconfigured service.
                self.assertEqual(set(current[server]['allowed_tools']), set(names))
            for name in names:
                tool = rows[name]
                self.assertTrue(tool.annotations.readOnlyHint)
                provider_schema(tool.inputSchema)
                resolved_schema(tool.outputSchema, require_object=False)
                self.assertTrue(policy.check(server + '::' + name, arguments(tool)).allowed)
        self.assertIn('kuro-filesystem::search_past_conversations', policy.tools)
        self.assertFalse(policy.check('memory-core::search', {'query': 'synthetic', 'sensitivity': 'restricted'}).allowed)
        # Even a corrupted local policy cannot grant an HTTP write/reviewer API.
        cfg = deepcopy(policy.policy)
        cfg['tools']['memory-core::memory_approve_candidate'] = {'mode': 'read_only'}
        self.assertFalse(ToolPolicy(cfg).check('memory-core::memory_approve_candidate', {}).allowed)

    def test_request_routing_keeps_history_separate(self):
        catalog = ToolCatalog.load_default()
        available = list(ToolPolicy.load_default().tools)
        for query, name in [('Memory Core search', 'memory-core::search'),
                            ('Memory Core collection', 'memory-core::memory_get_collection'),
                            ('PAOS positions', 'personal-asset-os::list_asset_positions'),
                            ('PAOS reconciliation', 'personal-asset-os::get_reconciliation_status'),
                            ('chat history', 'kuro-filesystem::search_past_conversations')]:
            with self.subTest(query=query):
                self.assertIn(name, catalog.route(query, available).tool_names)
        self.assertNotIn('memory-core::search', catalog.route('chat history', available).tool_names)


class WireFixture:
    """Independent Streamable HTTP JSON MCP peer using captured schemas + fake handlers."""
    def __init__(self):
        self.tools = {s: deepcopy(v['tools']) for s, v in METADATA.items()}
        self.requests = []
        self.mode = ''
        self.delay = 0
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, data, headers=None):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # expected after synthetic timeout/cancellation

            def do_GET(self):
                fixture.requests.append(('GET', self.path, None))
                self.reply(405, {})

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.requests.append(('POST', self.path, request))
                if any(k in self.headers for k in ('Authorization', 'Cookie', 'Proxy-Authorization')):
                    return self.reply(403, {})
                if fixture.mode in {'redirect', 'auth', 'offline'}:
                    return self.reply({'redirect': 307, 'auth': 401, 'offline': 503}[fixture.mode], {},
                                      {'Location': 'http://example.invalid/private'} if fixture.mode == 'redirect' else {})
                server = self.path.split('/')[1]
                method = request['method']
                if method == 'notifications/initialized':
                    return self.reply(202, {})
                if method == 'initialize':
                    result = {'protocolVersion': request['params']['protocolVersion'], 'capabilities': {'tools': {}},
                              'serverInfo': {'name': 'wrong-peer' if fixture.mode == 'identity' else HTTP_SERVER_NAMES[server], 'version': 'synthetic'}}
                elif method == 'tools/list':
                    result = {'tools': fixture.tools[server]}
                elif method == 'tools/call':
                    time.sleep(fixture.delay)
                    name = request['params']['name']
                    if name not in HTTP_READ_TOOLS[server]:
                        return self.reply(500, {})
                    result = {'content': [{'type': 'text', 'text': '{}'}], 'structuredContent': {}, 'isError': False}
                    if fixture.mode == 'invalid_output':
                        # Declared outputSchema requires structuredContent for both owners.
                        result.pop('structuredContent')
                else:
                    return self.reply(400, {})
                self.reply(200, {'jsonrpc': '2.0', 'id': request['id'], 'result': result})

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        real_client = httpx.AsyncClient
        fixture = self

        class FixtureTransport(httpx.AsyncBaseTransport):
            def __init__(self):
                self.inner = httpx.AsyncHTTPTransport(trust_env=False)

            async def handle_async_request(self, request):
                server = next((s for s, url in HTTP_ENDPOINTS.items() if str(request.url) == url), None)
                if server is None:
                    raise AssertionError('non-fixture destination attempted')
                target = f'http://127.0.0.1:{fixture.http.server_port}/{server}'
                forwarded = httpx.Request(request.method, target, headers=request.headers,
                                          content=request.content, extensions=request.extensions)
                return await self.inner.handle_async_request(forwarded)

            async def aclose(self):
                await self.inner.aclose()

        def factory(*args, **kwargs):
            assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
            return real_client(*args, **kwargs, transport=FixtureTransport())

        self.patch = patch.object(client_module.httpx, 'AsyncClient', factory)
        self.patch.start()
        return self

    def __exit__(self, *_):
        self.patch.stop()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)

    def call_count(self):
        return sum(row[2] is not None and row[2]['method'] == 'tools/call' for row in self.requests)


class HttpWireTests(unittest.IsolatedAsyncioTestCase):
    def registry(self):
        return RegistryTests().registry({server: definition(server) for server in HTTP_READ_TOOLS})

    async def test_every_tool_canonical_alias_schema_and_disabled(self):
        with WireFixture() as fixture:
            registry = self.registry()
            adapter = ToolAdapter(registry)
            _, openai, claude = await adapter.get_tools(list(HTTP_READ_TOOLS))
            raw = adapter.get_last_formatted_tools_dict()
            self.assertEqual(len(raw), 15, adapter.schema_errors)
            manager = ToolManager(openai, claude, raw)
            async with MCPClient(registry) as client:
                executor = ToolExecutor(client, manager)
                expected = []
                for identity, info in raw.items():
                    wire = next(Tool.model_validate(t) for t in METADATA[info.related_server]['tools'] if t['name'] == info.wire_name)
                    self.assertEqual(info.schema_digest, schema_digest(wire.inputSchema))
                    self.assertEqual(info.output_schema, wire.outputSchema)
                    for alias in (identity, info.api_name):
                        outcome = await executor.run_single_tool(alias, 'fixture', arguments(wire))
                        self.assertFalse(outcome[0], (identity, outcome[1]))
                        sent = next(r[2] for r in reversed(fixture.requests) if r[2] and r[2]['method'] == 'tools/call')
                        self.assertEqual(sent['params']['name'], info.wire_name)
                        self.assertEqual(sent['params']['arguments'], arguments(wire))
                    expected.append(identity)
                count = fixture.call_count()
                blocked = 0
                for server, rows in METADATA.items():
                    for tool in [*rows['tools'], *({'name': name} for name in ('unknown', 'trade', 'reconcile', 'backup', 'restore', 'refresh', 'admin'))]:
                        if tool['name'] in HTTP_READ_TOOLS[server]:
                            continue
                        identity = server + '::' + tool['name']
                        for alias in (identity, tool['name'], provider_alias(identity)):
                            self.assertTrue((await executor.run_single_tool(alias, 'deny', {}))[0])
                            blocked += 1
                        outcome = await client.call_tool(server, tool['name'], {})
                        self.assertFalse(outcome.may_have_executed)
                        self.assertTrue(outcome.is_error)
                for identity, info in raw.items():
                    policy = deepcopy(ToolPolicy.load_default().policy)
                    policy['tools'][identity]['enabled'] = False
                    executor._tool_policy = ToolPolicy(policy)
                    for alias in (identity, info.api_name):
                        self.assertTrue((await executor.run_single_tool(alias, 'disabled', {}))[0])
                        blocked += 1
                self.assertEqual(fixture.call_count(), count)
                EVIDENCE['dispatch'] = {'tools': expected, 'synthetic_calls': count, 'executor_denials': blocked,
                                        'production_business_calls': 0, 'provider_calls': 0}
            self.assertEqual(client.active_sessions, {})
            self.assertEqual(client.discovery_results, {})

    async def test_annotation_schema_and_output_drift(self):
        with WireFixture() as fixture:
            registry = self.registry()
            for server in HTTP_READ_TOOLS:
                name = HTTP_READ_TOOLS[server][0]
                tool = next(t for t in fixture.tools[server] if t['name'] == name)
                original = deepcopy(tool)
                args = arguments(Tool.model_validate(tool))
                for annotation in (None, {'readOnlyHint': False}, {'readOnlyHint': True, 'destructiveHint': True}):
                    tool['annotations'] = annotation
                    adapter = ToolAdapter(registry)
                    await adapter.get_tools([server])
                    self.assertNotIn(server + '::' + name, adapter.get_last_formatted_tools_dict())
                    async with MCPClient(registry) as client:
                        outcome = await client.call_tool(server, name, args)
                        self.assertFalse(outcome.may_have_executed)
                tool.update(original)
                async with MCPClient(registry) as client:
                    outcome = await client.call_tool(server, name, args, expected_schema_digest='changed')
                    self.assertEqual(outcome.reason_code, 'schema_changed')
                    outcome = await client.call_tool(server, name, args, expected_output_digest='changed')
                    self.assertEqual(outcome.reason_code, 'schema_changed')
                    fixture.mode = 'invalid_output'
                    outcome = await client.call_tool(server, name, args)
                    self.assertEqual(outcome.reason_code, 'output_schema_invalid')
                    fixture.mode = ''
            self.assertEqual(fixture.call_count(), 2)

    async def test_http_errors_identity_and_timeout_are_bounded(self):
        with WireFixture() as fixture:
            for mode in ('redirect', 'auth', 'offline', 'identity'):
                fixture.mode = mode
                async with MCPClient(self.registry()) as client:
                    result = await client.discover_tools('memory-core')
                    self.assertFalse(result.complete, mode)
                    self.assertEqual(client.active_sessions, {})
            self.assertEqual(fixture.call_count(), 0)
            fixture.mode, fixture.delay = '', 0.7
            registry = self.registry()
            registry.servers['memory-core'].timeout = timedelta(seconds=0.25)
            async with MCPClient(registry) as client:
                self.assertTrue((await client.discover_tools('memory-core')).complete)
                started = time.monotonic()
                outcome = await client.call_tool('memory-core', 'memory_overview', {})
                self.assertTrue(outcome.is_error)
                self.assertTrue(outcome.may_have_executed)
                self.assertLess(time.monotonic() - started, 3)
            self.assertEqual(fixture.call_count(), 1)  # no retry after unknown execution
            EVIDENCE['timeout'] = {'actual_synthetic_tools_calls': 1, 'retries': 0, 'bounded_seconds': 3}

    async def test_connection_options_never_come_from_model(self):
        with WireFixture() as fixture:
            async with MCPClient(self.registry()) as client:
                for args in ({'url': 'http://example.invalid'}, {'headers': {}}, {'token': 'synthetic'},
                             {'scopes': ['admin']}, {'sensitivity': 'restricted'}):
                    outcome = await client.call_tool('memory-core', 'search', {'query': 'synthetic', **args})
                    self.assertTrue(outcome.is_error)
                    self.assertFalse(outcome.may_have_executed)
                self.assertEqual(fixture.requests, [])

    async def test_no_proxy_redirect_or_cookie_reuse(self):
        registry = self.registry()
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://example.invalid', 'ALL_PROXY': 'http://example.invalid'}):
            async with _http_client_factory(registry.servers['memory-core'])() as http:
                self.assertFalse(http.trust_env)
                self.assertFalse(http.follow_redirects)
                for request in [httpx.Request('POST', 'http://example.invalid'),
                                httpx.Request('POST', HTTP_ENDPOINTS['memory-core'], headers={'Cookie': 'synthetic'}),
                                httpx.Request('DELETE', HTTP_ENDPOINTS['memory-core'])]:
                    with self.assertRaises(ValueError):
                        await http.event_hooks['request'][0](request)

    async def test_failed_http_connection_preserves_existing_stdio_session(self):
        with WireFixture() as fixture:
            fixture.mode = 'auth'
            client = MCPClient(self.registry())
            stdio_session = object()
            client.active_sessions['kuro-web'] = stdio_session
            closed = AsyncMock()
            client.exit_stack.push_async_callback(closed)
            result = await client.discover_tools('memory-core')
            self.assertFalse(result.complete)
            self.assertIs(client.active_sessions['kuro-web'], stdio_session)
            closed.assert_not_awaited()
            await client.aclose()
            closed.assert_awaited_once()

    async def test_eight_synthetic_stdio_connections_survive_http_and_close(self):
        # Real stdio_client transports, with tiny synthetic peers instead of any
        # production adapter. Existing eight names + two HTTP sessions share one stack.
        script = '''import sys,json
for line in sys.stdin:
 r=json.loads(line); method=r.get('method')
 if 'id' not in r: continue
 if method=='initialize':
  value={'protocolVersion':r['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'synthetic-stdio','version':'1'}}
 elif method=='tools/list':
  value={'tools':[{'name':'lookup','inputSchema':{'type':'object'},'annotations':{'readOnlyHint':True}}]}
 elif method=='tools/call':
  value={'content':[{'type':'text','text':'synthetic stdio'}],'isError':False}
 else: value={}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':value}),flush=True)
'''
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as folder, WireFixture() as fixture:
            path = Path(folder) / 'peer.py'
            path.write_text(script, encoding='utf-8')
            original = json.loads((RUNTIME / 'mcp_servers.json').read_text(encoding='utf-8'))['mcp_servers']
            names = [name for name, config in original.items() if config.get("transport", "stdio") == "stdio"]
            self.assertEqual(set(names), {"kuro-web", "kuro-filesystem", "kuro-mail", "project-workspace"})
            rows = {name: {'command': sys.executable, 'args': ['-B', '-u', str(path)], 'timeout': 3} for name in names}
            rows.update({s: definition(s) for s in HTTP_READ_TOOLS})
            registry = RegistryTests().registry(rows)
            async with MCPClient(registry) as client:
                for name in names:
                    self.assertTrue((await client.discover_tools(name)).complete)
                fixture.mode = 'auth'
                self.assertFalse((await client.discover_tools('memory-core')).complete)
                fixture.mode = ''
                for name in HTTP_READ_TOOLS:
                    self.assertTrue((await client.discover_tools(name)).complete)
                self.assertEqual(len(client.active_sessions), len(names) + len(HTTP_READ_TOOLS))
                for name in names:
                    self.assertFalse((await client.call_tool(name, 'lookup', {})).is_error)
            self.assertEqual(client.active_sessions, {})
            EVIDENCE['mixed_transport'] = {'synthetic_stdio_sessions': len(names), 'http_sessions': 2,
                                         'stdio_calls_after_http_failure_and_success': len(names), 'aclose': 'PASS'}
