"""Opt-in bounded real STDIO acceptance; no provider, live history or database IO."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / 'src'))
from mcp.client.stdio import get_default_environment
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy

TOOLS = {'workspace_info', 'list_dir', 'find_files', 'search_text', 'read_file', 'read_files', 'project_context'}
OLD = {'list_allowed_roots', 'list_directory', 'search_files', 'read_text_file'}


async def verify():
    config = json.loads((RUNTIME / 'mcp_servers.json').read_text(encoding='utf-8'))
    definition = config['mcp_servers']['project-workspace']
    entry = Path(definition['args'][0]).resolve(strict=True)
    assert set(definition['allowed_tools']) == TOOLS
    assert 'WORKSPACE_MCP_WRITE_POLICY' not in definition['env']
    # Hash the accepted build without reading or mutating external runtime state.
    build_hashes = {p.relative_to(entry.parent.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in entry.parent.parent.rglob('*') if p.is_file()}
    receipt = {'transport': 'stdio', 'entry': str(entry), 'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(),
               'build_files': len(build_hashes), 'build_manifest_sha256': hashlib.sha256(json.dumps(build_hashes, sort_keys=True).encode()).hexdigest(),
               'model_calls': 0, 'provider_calls': 0, 'live_runtime_adoption': False}
    with tempfile.TemporaryDirectory(prefix='kuro-workspace-fixture-') as temp:
        directory = Path(temp)
        root = directory / 'root'
        root.mkdir()
        (root / 'README.md').write_text('# Workspace fixture\nNEEDLE safe text\n', encoding='utf-8')
        (root / 'notes.txt').write_text('second harmless file\n', encoding='utf-8')
        # Synthetic denied files only. No real credentials are opened.
        (root / '.env').write_text('SYNTHETIC_DENIED_SENTINEL\n', encoding='utf-8')
        (directory / 'outside.txt').write_text('OUTSIDE_SENTINEL\n', encoding='utf-8')
        fixture = deepcopy(config)
        fixture['mcp_servers'] = {k: fixture['mcp_servers'][k] for k in ('kuro-filesystem', 'project-workspace')}
        fixture['mcp_servers']['kuro-filesystem']['command'] = sys.executable
        fixture['mcp_servers']['kuro-filesystem']['args'] = [str(RUNTIME / 'local_mcp/filesystem_tools_server.py')]
        fixture['mcp_servers']['project-workspace']['env'].update(
            WORKSPACE_MCP_ROOTS=f'fixture={root}', WORKSPACE_MCP_DEFAULT_ROOT='fixture')
        config_path = directory / 'servers.json'
        config_path.write_text(json.dumps(fixture), encoding='utf-8')
        # A parent operate setting must not enter the Kuro child environment.
        with patch.dict(os.environ, {'WORKSPACE_MCP_WRITE_POLICY': str(directory / 'must-not-be-inherited.json')}):
            assert 'WORKSPACE_MCP_WRITE_POLICY' not in get_default_environment()
            registry = ServerRegistry(config_path)
            adapter = ToolAdapter(registry)
            _, openai, claude = await adapter.get_tools(['kuro-filesystem', 'project-workspace'])
            raw = adapter.get_last_formatted_tools_dict()
            expected = {'project-workspace::' + name for name in TOOLS} | {'kuro-filesystem::search_past_conversations'}
            assert set(raw) == expected, adapter.schema_errors
            assert not adapter.schema_errors
            assert all(result.complete for result in adapter.discovery_results.values())
            receipt['exposed_ids'] = sorted(raw)
            receipt['schemas'] = {
                server: result.schema_digest for server, result in adapter.discovery_results.items()}
            manager = ToolManager(openai, claude, raw)
            async with MCPClient(registry) as client:
                executor = ToolExecutor(client, manager)
                executor._tool_policy = ToolPolicy(json.loads((RUNTIME / 'tool_policy.json').read_text(encoding='utf-8')))
                async def call(name, args):
                    error, content, _, _ = await executor.run_single_tool('project-workspace::' + name, 'fixture-' + name, args)
                    assert not error, (name, content)
                    assert 'SYNTHETIC_DENIED_SENTINEL' not in content and 'OUTSIDE_SENTINEL' not in content
                    return content
                info = json.loads(await call('workspace_info', {}))
                assert info['mode'] == 'read-only' and info['writeCapabilities']['enabled'] is False
                assert [row['id'] for row in info['roots']] == ['fixture']
                receipt['workspace_identity'] = {k: info[k] for k in ('applicationVersion', 'toolContractVersion', 'buildId', 'mode', 'writeCapabilities', 'limits')}
                for name, args, marker in (
                    ('list_dir', {'root': 'fixture', 'maxEntries': 10}, 'README.md'),
                    ('find_files', {'root': 'fixture', 'pattern': '**/*.md', 'maxResults': 5}, 'README.md'),
                    ('search_text', {'root': 'fixture', 'query': 'NEEDLE', 'maxResults': 5}, 'NEEDLE'),
                    ('read_file', {'root': 'fixture', 'path': 'README.md', 'maxLines': 5}, 'NEEDLE'),
                    ('read_files', {'root': 'fixture', 'files': [{'path': 'README.md'}, {'path': 'notes.txt'}]}, 'second harmless'),
                    ('project_context', {'root': 'fixture', 'project': '.'}, 'Workspace fixture'),
                ):
                    assert marker in await call(name, args), name
                negatives = [
                    ('read_file', {'root': 'fixture', 'path': '../outside.txt'}, 'outside'),
                    ('read_file', {'root': 'fixture', 'path': str(directory / 'outside.txt')}, 'relative'),
                    ('read_file', {'root': 'fixture', 'path': '.env'}, 'denied'),
                    ('read_file', {'root': 'fixture', 'path': '.git/config'}, 'denied'),
                    ('read_file', {'root': 'unknown', 'path': 'README.md'}, 'root'),
                    ('read_files', {'root': 'fixture', 'files': [{'path': 'README.md'}, {'path': '.env'}]}, 'denied'),
                    ('project_context', {'root': 'fixture', 'project': '..'}, 'outside'),
                ]
                # Direct MCPClient calls isolate the backend guard, independently of ToolPolicy.
                for name, args, marker in negatives:
                    result = await client.call_tool('project-workspace', name, args)
                    assert result.is_error, (name, args)
                    assert marker in json.dumps(result.content_items).lower(), result.reason_code
                    assert 'SYNTHETIC_DENIED_SENTINEL' not in json.dumps(result.content_items)
                    assert 'OUTSIDE_SENTINEL' not in json.dumps(result.content_items)
                for name in ('write_file', 'apply_patch', 'create_file', 'delete_file', 'run_command', 'git_commit', 'git_push', 'restart'):
                    result = await client.call_tool('project-workspace', name, {})
                    assert result.is_error and not result.may_have_executed
                    assert result.reason_code == 'tool_unavailable'
                    error, _, _, _ = await executor.run_single_tool('project-workspace::' + name, 'negative', {})
                    assert error
                for name in OLD:
                    result = await client.call_tool('kuro-filesystem', name, {})
                    assert result.is_error and not result.may_have_executed
                    for identity in (name, 'kuro-filesystem::' + name):
                        error, _, _, _ = await executor.run_single_tool(identity, 'retired', {})
                        assert error
                history = await client.discover_tools('kuro-filesystem')
                assert [tool.name for tool in history.tools] == ['search_past_conversations']
                # Empty query proves callable transport without opening the history index.
                error, content, _, _ = await executor.run_single_tool('kuro-filesystem::search_past_conversations', 'history', {'query': '', 'conf_uid': 'synthetic-character'})
                assert not error and 'query is empty' in content
                receipt.update(read_tools_passed=7, backend_negative_cases=len(negatives), write_tools_blocked=8,
                               old_tools_blocked=4, history_transport=True, parent_write_policy_not_inherited=True)
    # Confirm the formal roots/limits through the same child, metadata only.
    registry = ServerRegistry(RUNTIME / 'mcp_servers.json')
    async with MCPClient(registry) as client:
        result = await client.call_tool('project-workspace', 'workspace_info', {})
        assert not result.is_error
        info = json.loads(next(item['text'] for item in result.content_items if item['type'] == 'text'))
        roots = {row['id']: row['path'] for row in info['roots']}
        expected_roots = {'projects': r'C:\project', 'mcp_tools': r'C:\GPT_MCPtool', 'work': r'C:\work'}
        assert {k: Path(v).resolve() for k, v in roots.items()} == {k: Path(v).resolve() for k, v in expected_roots.items()}
        assert info['mode'] == 'read-only' and info['writeCapabilities']['enabled'] is False
        receipt['formal_workspace'] = {'roots': roots, 'mode': info['mode'], 'writeCapabilities': info['writeCapabilities'],
                                       'buildId': info['buildId'], 'limits': info['limits']}
    assert build_hashes == {p.relative_to(entry.parent.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in entry.parent.parent.rglob('*') if p.is_file()}
    receipt['external_build_unchanged'] = True
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new receipt path.')
    receipt = asyncio.run(verify())
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
