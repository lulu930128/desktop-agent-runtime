"""Opt-in real STDIO pilot; never launched by tests or desktop startup.

Requires explicit authorization to start the supplied external reader. The only
root exposed is this task's plan directory; no model/API call or persistent config.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / 'src'))
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy


async def verify(reader_dir: Path) -> dict:
    node=shutil.which('node')
    entry=reader_dir.resolve(strict=True)/'dist/src/index.js'
    if node is None or not entry.is_file():
        raise ValueError('Existing reader build and Node are required.')
    plan_root=RUNTIME.parent/'docs/agent-runs/mcp-trust-security-m0'
    if not (plan_root/'Plan.md').is_file():
        raise ValueError('Plan fixture is missing.')
    allowed=['workspace_info','read_file']
    config={'mcp_servers':{'project-reading':{
        'command':node, 'args':[str(entry)], 'timeout':20, 'allowed_tools':allowed,
        'env':{'WORKSPACE_MCP_ROOTS':f'pilot={plan_root.resolve()}',
               'WORKSPACE_MCP_DEFAULT_ROOT':'pilot','WORKSPACE_MCP_MAX_READ_LINES':'20',
               'WORKSPACE_MCP_MAX_DIR_ENTRIES':'20'},
    }}}
    with tempfile.TemporaryDirectory(prefix='kuro-reader-pilot-') as temp:
        config_path=Path(temp)/'servers.json'
        config_path.write_text(json.dumps(config),encoding='utf-8')
        registry=ServerRegistry(config_path)
        adapter=ToolAdapter(registry)
        prompt,o,c=await adapter.get_tools(['project-reading'])
        raw=adapter.get_last_formatted_tools_dict()
        assert set(raw)=={'project-reading::'+name for name in allowed}, adapter.schema_errors
        manager=ToolManager(o,c,raw)
        async with MCPClient(registry) as client:
            executor=ToolExecutor(client,manager)
            executor._tool_policy=ToolPolicy({'tools':{name:{'mode':'read_only'} for name in raw}})
            error,info,_,_=await executor.run_single_tool('project-reading::workspace_info','pilot-info',{})
            assert not error and 'pilot' in info
            events=[event async for event in executor.execute_tools([
                {'id':'pilot-read','name':raw['project-reading::read_file'].api_name,
                 'input':{'root':'pilot','path':'Plan.md','startLine':1,'maxLines':5}}
            ],'OpenAI')]
            result=events[-1]['results'][0]['content']
            assert '# M0' in result and not any(event.get('status') in ('blocked','error') for event in events)
            # Public nonexistent escape target; the server must deny before file I/O.
            error,denied,_,_=await executor.run_single_tool('project-reading::read_file','pilot-escape',{'root':'pilot','path':'../outside-pilot.txt','maxLines':1})
            assert error and 'outside the configured workspace root' in denied.lower(), 'Expected root-boundary rejection, not a missing-file error.'
        return {'pilot':'project-reading','transport':'stdio','root_scope':'task_plan_only',
                'discovery_complete':adapter.discovery_results['project-reading'].complete,
                'exposed_tools':len(raw),'read_plan':True,'escape_denied':True,
                'entry_sha256':hashlib.sha256(entry.read_bytes()).hexdigest(),
                'persistent_config_changed':False,'model_called':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.reader_dir)),ensure_ascii=False,indent=2))
