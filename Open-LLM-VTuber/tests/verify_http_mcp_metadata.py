"""Opt-in metadata-only discovery; never sends tools/call or loads credentials."""
import argparse
import asyncio
import json
from datetime import timedelta
from pathlib import Path
import sys
from unittest.mock import patch

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ENDPOINTS = {
    'memory-core': 'http://127.0.0.1:18818/mcp',
    'personal-asset-os': 'http://127.0.0.1:18876/mcp/',
}


async def discover():
    receipt = {}
    for name, url in ENDPOINTS.items():
        requests, statuses = [], []

        async def guard(request):
            if str(request.url) != url or request.method not in {'GET', 'POST'}:
                raise ValueError('metadata_endpoint_or_method_denied')
            method = json.loads(request.content)['method'] if request.method == 'POST' else 'sse'
            if method not in {'initialize', 'notifications/initialized', 'tools/list', 'sse'}:
                raise ValueError('metadata_rpc_denied')
            if 'authorization' in request.headers or 'cookie' in request.headers:
                raise ValueError('credential_denied')
            requests.append({'http_method': request.method, 'rpc_method': method})

        async def status(response):
            statuses.append(response.status_code)

        def factory(headers=None, timeout=None, auth=None):
            if auth is not None:
                raise ValueError('auth_denied')
            return httpx.AsyncClient(headers=headers, timeout=timeout, trust_env=False,
                                     follow_redirects=False, event_hooks={'request': [guard], 'response': [status]})

        result = {'url': url, 'complete': False, 'requests': requests, 'statuses': statuses, 'tools': []}
        try:
            async with streamablehttp_client(url, timeout=5, sse_read_timeout=5,
                                            terminate_on_close=False, httpx_client_factory=factory) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=5)) as session:
                    initialized = await session.initialize()
                    result['server_info'] = initialized.serverInfo.model_dump(mode='json')
                    cursor, seen = None, set()
                    for _ in range(20):
                        page = await session.list_tools(cursor=cursor)
                        result['tools'].extend(tool.model_dump(mode='json', by_alias=True) for tool in page.tools)
                        cursor = page.nextCursor
                        if cursor is None:
                            result['complete'] = True
                            break
                        if cursor in seen:
                            raise ValueError('repeated_cursor')
                        seen.add(cursor)
            result['status'] = 'METADATA_PASS' if result['complete'] else 'INCOMPLETE'
        except Exception as exc:
            result['status'] = 'AUTH_BLOCKED' if any(code in (401, 403) for code in statuses) else 'TRANSPORT_BLOCKED'
            result['error_type'] = type(exc).__name__
        result['business_tools_call_count'] = 0
        receipt[name] = result
        print(name, result['status'], len(result['tools']), statuses)
    return receipt


async def discover_through_kuro():
    """Same metadata-only boundary through the actual Registry/MCPClient branch."""
    runtime = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(runtime / 'src'))
    from open_llm_vtuber.mcpp import mcp_client
    from open_llm_vtuber.mcpp.server_registry import ServerRegistry
    original_factory = mcp_client._http_client_factory
    receipt = {server: {'requests': [], 'statuses': []} for server in ENDPOINTS}

    def audited_factory(server):
        factory = original_factory(server)

        async def guard(request):
            method = json.loads(request.content)['method'] if request.method == 'POST' else 'sse'
            if method not in {'initialize', 'notifications/initialized', 'tools/list', 'sse'}:
                raise ValueError('metadata_rpc_denied')
            receipt[server.name]['requests'].append({'http_method': request.method, 'rpc_method': method})

        async def status(response):
            receipt[server.name]['statuses'].append(response.status_code)

        def build(**kwargs):
            client = factory(**kwargs)
            client.event_hooks['request'].append(guard)
            client.event_hooks['response'].append(status)
            return client
        return build

    registry = ServerRegistry(runtime / 'mcp_servers.json')
    with patch.object(mcp_client, '_http_client_factory', audited_factory):
        async with mcp_client.MCPClient(registry) as client:
            for server in ENDPOINTS:
                result = await client.discover_tools(server)
                row = receipt[server]
                row.update(complete=result.complete, reason=result.reason, pages=result.pages_read,
                           schema_digest=result.schema_digest, observed_at=result.observed_at,
                           tools=[tool.model_dump(mode='json', by_alias=True) for tool in result.tools],
                           business_tools_call_count=0)
                row['status'] = ('METADATA_PASS' if result.complete else 'AUTH_BLOCKED'
                                 if any(code in (401, 403) for code in row['statuses']) else 'TRANSPORT_BLOCKED')
                print(server, row['status'], len(result.tools), row['statuses'])
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--through-kuro', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new receipt path.')
    probe = discover_through_kuro if args.through_kuro else discover
    args.output.write_text(json.dumps(asyncio.run(probe()), ensure_ascii=False, indent=2), encoding='utf-8')
