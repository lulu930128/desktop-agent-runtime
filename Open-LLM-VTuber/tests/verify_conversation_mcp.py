"""Opt-in real STDIO discovery using installed adapters and no production backend."""
import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / 'src'))
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_schema import provider_schema, resolved_schema, SchemaError


async def discover():
    external = Path('C:/GPT_MCPtool')
    definitions = {
        'omi-search': {'command': str(external / 'OMI_search/.venv/Scripts/python.exe'),
                       'args': ['-B', str(external / 'OMI_search/server.py')],
                       'env': {'OMI_SEARCH_API_BASE_URL': 'http://127.0.0.1:1',
                               'OMI_SEARCH_SCHEMA_TIMEOUT_SECONDS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}},
    }
    for server, folder in [('japanese-study', 'japanese_study'), ('english-study', 'english_study'), ('listening-audio', 'listening_audio')]:
        definitions[server] = {'command': shutil.which('node'), 'args': [str(external / folder / 'dist/src/index.js')]}
    results = {}
    with tempfile.TemporaryDirectory(dir=RUNTIME.parent / '.tmp', prefix='conversation-discovery-') as temp:
        path = Path(temp) / 'servers.json'
        path.write_text(json.dumps({'mcp_servers': definitions}), encoding='utf-8')
        async with MCPClient(ServerRegistry(path)) as client:
            for name in definitions:
                result = await client.discover_tools(name)
                rows = []
                for tool in result.tools:
                    error = ''
                    try:
                        provider_schema(tool.inputSchema)
                        if tool.outputSchema is not None:
                            resolved_schema(tool.outputSchema, require_object=False)
                    except SchemaError as exc:
                        error = exc.code
                    rows.append({'name': tool.name, 'annotations': tool.annotations.model_dump() if tool.annotations else None,
                                 'inputSchema': tool.inputSchema, 'projection_error': error})
                entry = Path(definitions[name]['args'][-1])
                results[name] = {'complete': result.complete, 'reason': result.reason, 'pages': result.pages_read,
                                 'schema_digest': result.schema_digest, 'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(),
                                 'tools': rows}
                print(name, result.complete, len(rows), [(r['name'], r['projection_error']) for r in rows if r['projection_error']])
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new receipt path.')
    args.output.write_text(json.dumps(asyncio.run(discover()), ensure_ascii=False, indent=2), encoding='utf-8')
