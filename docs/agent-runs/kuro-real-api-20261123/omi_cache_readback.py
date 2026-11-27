from live import *
async def main():
    registry=ServerRegistry(RT/'mcp_servers.json')
    from datetime import timedelta
    owner_wait = '--owner-wait' in sys.argv
    if owner_wait:
        registry.servers['omi-search'].timeout = timedelta(seconds=100)
    adapter=ToolAdapter(registry)
    await adapter.get_tools(['omi-search'])
    name='omi_read_data_freshness'
    info=adapter.get_last_formatted_tools_dict()['omi-search::'+name]
    args={'market':'tw','question':'Read cached Taiwan market data freshness only.',
          'realtime_policy':'cache_only','refresh_if_missing':False,'include_intraday':False}
    async with MCPClient(registry) as client:
        r=await client.call_tool('omi-search',name,args,expected_schema_digest=schema_digest(info.input_schema),expected_output_digest=schema_digest(info.output_schema))
    d=r.structured_content or {}
    def examine(node,prefix=''):
        out={}
        if isinstance(node,dict):
            for k,v in node.items():
                key=prefix+'.'+k if prefix else k
                if isinstance(v,(dict,list)) and prefix.count('.')<4:out.update(examine(v,key))
                elif k in ('freshness','status','as_of','asof','market','reason_code','contract_version','code') and isinstance(v,str) and len(v)<80:out[key]=v
        elif isinstance(node,list) and node:out.update(examine(node[0],prefix+'.0'))
        return out
    save('omi-owner-wait.json' if owner_wait else 'omi-cache-readback.json',{'diagnostic_client_timeout_seconds':100 if owner_wait else 30,'args':args,'schema_sha256':schema_digest(info.input_schema),'call_id':r.execution_id,'start':r.started_at,'end':r.completed_at,'duration_s':r.duration_seconds,'status':r.status,'reason_code':r.reason_code,'received':r.result_received,'result_sha256':sha(r.model_text()),'keys':list(d),'source':examine(d)})
if __name__=='__main__':asyncio.run(main())
