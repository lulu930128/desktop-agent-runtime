"""Read-only live verification. Receipts contain metadata, never API keys or learner records."""
import asyncio, hashlib, json, os, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import yaml
from loguru import logger
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RT = ROOT / "Open-LLM-VTuber"
sys.path.insert(0, str(RT / "src"))
sys.path.insert(0, str(RT))
os.environ["KURO_TOOL_POLICY_PATH"] = str(RT / "tool_policy.json")
from open_llm_vtuber.mcpp.server_registry import ServerRegistry, OWNER_SERVICES
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager, DISCOVERY_DESCRIPTION, ToolSelection
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy, ToolPolicyDecision
from open_llm_vtuber.mcpp.tool_schema import schema_digest
from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
logger.remove()
def now(): return datetime.now(timezone.utc).isoformat()
def save(name, body):
    p = HERE / name
    tmp = p.with_suffix('.part')
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)
def sha(x): return hashlib.sha256(x.encode()).hexdigest()
def canonical_json(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,default=str)
async def init():
    registry = ServerRegistry(RT / 'mcp_servers.json')
    adapter = ToolAdapter(registry)
    _, a, c = await adapter.get_tools(list(OWNER_SERVICES))
    manager = ToolManager(a,c,adapter.get_last_formatted_tools_dict())
    manager.bind_discovery(adapter,OWNER_SERVICES)
    return registry,manager
async def live():
    registry, manager = await init()
    policy = ToolPolicy.load_default()
    inv = manager.inventory(policy)
    evidence = {'observed_at':now(),'services':inv['services'],'tools':[
        {k:v for k,v in r.items() if k not in ('description','label')} for r in inv['tools']],'calls':[]}
    calls = [('project-workspace','read_file',{'root':'projects','path':PROBE}),
             ('japanese-study','study_get_summary',{}),
             ('english-study','english_search_reference_entries',{'query':'study','limit':1}),
             ('listening-audio','listening_health',{}),
             ('listening-audio','listening_get_question',{'setId':'kuro-verification','questionId':'Q1'}),
             ('omi-search','omi_read_data_freshness',{'market':'tw'})]
    async with MCPClient(registry) as client:
        ex = ToolExecutor(client,manager)
        for owner,wire,args in calls:
            key=owner+'::'+wire
            row={'tool':key,'started':now(),'arguments':args}
            info=manager.get_tool(key)
            if info:
                row.update(input_schema=info.input_schema,output_schema_sha256=schema_digest(info.output_schema))
            decision=ex.check_call(key,args)
            row['policy']=decision.reason_code
            if decision.allowed:
                result=await client.call_tool(owner,wire,args,expected_schema_digest=schema_digest(info.input_schema),
                                               expected_output_digest=schema_digest(info.output_schema))
                data=result.structured_content or {}
                row.update(execution_id=result.execution_id,status=result.status,reason_code=result.reason_code,
                           received=result.result_received,elapsed_s=result.duration_seconds,
                           result_sha256=sha(result.model_text()),result_bytes=len(result.model_text().encode()),
                           keys=list(data) if isinstance(data,dict) else [],source={})
                if isinstance(data,dict):
                    for k in ('status','ok','count','total','freshness','error','reason_code','reasonCode','code','source','contract_version','mode'):
                        v=data.get(k)
                        if isinstance(v,(bool,int)) or isinstance(v,str) and len(v)<75:row['source'][k]=v
                        elif k=='error' and isinstance(v,dict):
                            row['source'][k]={a:v[a] for a in ('status','code','retryable') if a in v}
                if result.is_error and not row['source']:
                    row['error_class']='owner_call_error'
                if key.endswith('::read_file'): row['challenge_matched']=NONCE in result.model_text()
            row['ended']=now(); evidence['calls'].append(row); save('live-mcp.json',evidence)
    return registry,manager
PROBE='desktop-agent-runtime/docs/agent-runs/kuro-real-api-20261123/public-challenge.txt'
NONCE=(HERE/'public-challenge.txt').read_text(encoding='utf-8').splitlines()[0].split('=')[1]
if __name__=='__main__':
    asyncio.run(live())
