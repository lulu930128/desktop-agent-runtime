"""Real installed STDIO adapters against bounded synthetic loopback fixtures only."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / 'src'))
from loguru import logger
from mcp.client.stdio import get_default_environment
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_identity import provider_alias, LEGACY_OWNERS

SERVERS = ('omi-search', 'japanese-study', 'english-study', 'listening-audio')
SENTINELS = {name: 'SYNTHETIC_MUST_NOT_INHERIT' for name in (
    'OMI_SEARCH_RUNTIME_CONTROL_TOKEN', 'OMI_SEARCH_AI_TRUST_TOKEN', 'OMI_MCP_AI_TRUST_TOKEN',
    'OMI_AI_TRUST_TOKEN', 'JSTUDY_HUB_API_TOKEN', 'ESTUDY_HUB_API_TOKEN', 'LISTENING_MCP_HTTP_TOKEN',
    'NODE_OPTIONS', 'PYTHONPATH', 'OPENAI_API_KEY')}


class Fixture(BaseHTTPRequestHandler):
    requests = []
    reject = False

    def log_message(self, *_):
        pass

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def record(self, body=None):
        # Assert without retaining any credential value in evidence.
        assert not any(key.lower() in {'authorization', 'x-omi-ai-trust-token', 'x-omi-runtime-control-token'} for key in self.headers)
        self.requests.append({'method': self.command, 'path': self.path, 'body': body})

    def do_GET(self):
        self.record()
        if self.path == '/api/ai/tools':
            return self.reply(503, {'error': 'fixture_schema_offline'})
        if self.reject:
            return self.reply(503, {'error': {'code': 'FIXTURE_OFFLINE', 'message': 'Synthetic source unavailable'}})
        if self.path == '/api/listening/v1/health':
            return self.reply(200, {'ok': True, 'contractVersion': 'listening-trainer-v1', 'languages': ['ja', 'en'],
                                   'tts': {'listenerRunning': False, 'readiness': 'listener_only', 'profiles': []}})
        if '/questions/' in self.path:
            return self.reply(200, {'ok': True, 'setId': 'fixture-set', 'questionId': 'q1', 'position': 1,
                'questionCount': 1, 'language': 'ja', 'presentation': 'text_options',
                'options': [{'key': n, 'text': 'Synthetic choice'} for n in range(1, 5)], 'audio': {'state': 'missing', 'bytes': 0}})
        if '/attempts/' in self.path:
            return self.reply(200, {'ok': True, 'contractVersion': 'listening-result-v2', 'language': 'en', 'examSystem': 'IELTS',
                'setId': 'fixture-set', 'attemptId': 'attempt1', 'title': 'Synthetic practice', 'sourceRef': 'fixture',
                'sourceKind': 'generated_practice', 'scope': 'section', 'status': 'in_progress',
                'startedAt': '2026-10-24T00:00:00Z', 'completedAt': None, 'gradingPolicyVersion': 'ielts-listening-answer-v2',
                'rawScore': 0, 'maxScore': 1, 'questionCount': 1, 'answeredCount': 0, 'details': []})
        return self.reply(200, {'ok': True})

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        assert size < 65536
        body = json.loads(self.rfile.read(size))
        self.record(body)
        assert self.path == '/api/ai/ask', 'Non-query POST attempted'
        assert body['contract_version'] == 'omi.decision.v4' and body['caller_profile'] == 'omi_search'
        assert body['mode'] == 'data_only'
        assert all(body[name] is False for name in ('allow_llm', 'allow_write', 'allow_external_fetch'))
        return self.reply(200, {'contract_version': 'omi.decision.v4', 'status': 'partial', 'ok': True,
            'target': body.get('target', {}), 'evidence': [], 'warnings': ['stale'], 'limitations': ['synthetic cache only'],
            'missing': ['fixture_missing'], 'answer': {'text': 'Synthetic cached evidence'}})


def build_hashes(config):
    files = set()
    for definition in config['mcp_servers'].values():
        entry = Path(definition['args'][-1])
        if entry.suffix == '.js':
            files.update(p for p in entry.parent.parent.rglob('*') if p.is_file())
        else:
            files.add(entry)
            files.update(entry.parent.glob('*snapshot.json'))
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


async def verify():
    logger.remove()
    config = json.loads((RUNTIME / 'mcp_servers.json').read_text(encoding='utf-8'))
    config['mcp_servers'] = {name: config['mcp_servers'][name] for name in SERVERS}
    before = build_hashes(config)
    Fixture.requests, Fixture.reject = [], False
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{fixture.server_port}'
    env_keys = ('OMI_SEARCH_API_BASE_URL', 'JSTUDY_HUB_BASE_URL', 'ESTUDY_HUB_BASE_URL', 'LISTENING_TRAINER_BASE_URL')
    for server, env_key in zip(SERVERS, env_keys):
        config['mcp_servers'][server]['env'][env_key] = origin
    receipt = {'production_backend_calls': 0, 'provider_calls': 0, 'llm_calls': 0, 'runtime_adoption': 'PENDING'}
    try:
        with tempfile.TemporaryDirectory(dir=RUNTIME.parent / '.tmp', prefix='conversation-acceptance-') as temp, patch.dict(os.environ, SENTINELS):
            assert not set(SENTINELS) & set(get_default_environment())
            path = Path(temp) / 'servers.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            registry = ServerRegistry(path)
            adapter = ToolAdapter(registry)
            _, openai, claude = await adapter.get_tools(list(SERVERS))
            raw = adapter.get_last_formatted_tools_dict()
            expected = {server + '::' + name for server, row in config['mcp_servers'].items() for name in row['allowed_tools']}
            assert set(raw) == expected, adapter.schema_errors
            assert not adapter.schema_errors and all(row.complete for row in adapter.discovery_results.values())
            manager = ToolManager(openai, claude, raw)
            policy = ToolPolicy(json.loads((RUNTIME / 'tool_policy.json').read_text(encoding='utf-8')))
            receipt['discovery'] = {name: {'complete': row.complete, 'count': len(row.tools), 'digest': row.schema_digest}
                                    for name, row in adapter.discovery_results.items()}
            receipt['exposed_ids'] = sorted(expected)
            passed, blocked = [], []
            async with MCPClient(registry) as client:
                executor = ToolExecutor(client, manager)
                executor._tool_policy = policy
                async def call(identity, arguments):
                    result = await executor.run_single_tool(identity, 'fixture', arguments)
                    assert not result[0], (identity, result[1])
                    passed.append(manager.resolve_tool_name(identity))
                    return result

                args = {'question': 'Synthetic unchanged question', 'target': {'type': 'auto'},
                        'contract_version': 'omi.decision.v4', 'mode': 'data_only', 'refresh_if_missing': False,
                        'realtime_policy': 'cache_only', 'tool_budget': {'max_calls': 3, 'max_external_fetches': 0, 'max_total_seconds': 20}}
                result = await call(raw['omi-search::omi_ask'].api_name, args)
                assert 'stale' in result[1] and 'synthetic cache only' in result[1]
                payload = next(row['body'] for row in Fixture.requests if row['method'] == 'POST')
                assert payload == {**{k: v for k, v in args.items() if k != 'refresh_if_missing'},
                                   'caller_profile': 'omi_search', 'allow_llm': False, 'allow_write': False, 'allow_external_fetch': False}
                receipt['exact_omi_backend_payload'] = payload
                await call('omi-search::omi_ask', {'question': 'Synthetic default cache-only'})
                for name in ('omi_read_market_overview', 'omi_read_data_freshness', 'omi_read_source_health', 'omi_read_capability_status'):
                    await call('omi-search::' + name, {})
                await call('omi-search::omi_read_stock_context', {'symbol': '2330'})
                await call('omi-search::omi_read_refresh_status', {'job_id': 1})
                for identity in sorted(expected):
                    if identity.startswith('omi-search::'):
                        continue
                    schema = raw[identity].input_schema
                    arguments = {key: {'setId': 'fixture-set', 'questionId': 'q1', 'attemptId': 'attempt1'}.get(key, 'fixture-item')
                                 for key in schema.get('required', [])}
                    await call(identity, arguments)
                # Explicit policy denial, including provider aliases, must stop before IO.
                count = sum(row['path'] != '/api/ai/tools' for row in Fixture.requests)
                for name in config['mcp_servers']['omi-search']['allowed_tools']:
                    for forbidden in ({'refresh_if_missing': True}, {'refresh_if_missing': 'true'}, {'mode': 'brief'},
                                      {'mode': 'analysis'}, {'caller_profile': 'kuro_readonly'}, {'allow_llm': False},
                                      {'allow_write': False}, {'allow_external_fetch': True}, {'tool_budget': {'max_external_fetches': 1}}):
                        identity = 'omi-search::' + name
                        for alias in (identity, raw[identity].api_name):
                            error, *_ = await executor.run_single_tool(alias, 'negative', {'question': 'fixture', **forbidden})
                            assert error
                            blocked.append(alias)
                for server, discovery in adapter.discovery_results.items():
                    for tool in discovery.tools:
                        if tool.name in config['mcp_servers'][server]['allowed_tools']:
                            continue
                        identity = server + '::' + tool.name
                        for alias in (identity, tool.name, provider_alias(identity)):
                            error, *_ = await executor.run_single_tool(alias, 'denied', {})
                            assert error
                            blocked.append(alias)
                        result = await client.call_tool(server, tool.name, {})
                        assert result.is_error and not result.may_have_executed and result.reason_code == 'tool_unavailable'
                for name, owner in LEGACY_OWNERS.items():
                    if owner != 'omi-market':
                        continue
                    for alias in (name, owner+'::'+name, provider_alias(owner+'::'+name)):
                        error, *_ = await executor.run_single_tool(alias, 'retired', {})
                        assert error
                        blocked.append(alias)
                assert sum(row['path'] != '/api/ai/tools' for row in Fixture.requests) == count
                for identity in expected:
                    disabled = deepcopy(policy.policy)
                    disabled['tools'][identity]['enabled'] = False
                    executor._tool_policy = ToolPolicy(disabled)
                    for alias in (identity, raw[identity].api_name):
                        error, *_ = await executor.run_single_tool(alias, 'disabled', {})
                        assert error
                        blocked.append(alias)
                executor._tool_policy = policy
                assert sum(row['path'] != '/api/ai/tools' for row in Fixture.requests) == count
                Fixture.reject = True
                for identity in ('japanese-study::study_get_summary', 'english-study::english_get_summary', 'listening-audio::listening_health'):
                    error, content, *_ = await executor.run_single_tool(identity, 'offline', {})
                    assert error, (identity, content)
                receipt['offline_sources_remain_errors'] = 3
            receipt.update(successful_fixture_calls=len(passed), exercised_ids=sorted(set(passed)), blocked_attempts=len(blocked),
                           parent_secrets_not_inherited=True, only_omi_query_posts=True)
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=2)
    assert before == build_hashes(config)
    receipt['external_files_unchanged'] = len(before)
    receipt['http_methods'] = sorted(set(row['method'] for row in Fixture.requests))
    receipt['post_paths'] = sorted(set(row['path'] for row in Fixture.requests if row['method'] == 'POST'))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new receipt path.')
    result = asyncio.run(verify())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'exposed_ids', 'exercised_ids'}}, indent=2))
