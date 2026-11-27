from live import *
import urllib.request,urllib.parse
async def main():
    registry=ServerRegistry(RT/'mcp_servers.json')
    adapter=ToolAdapter(registry)
    _,o,c=await adapter.get_tools(['listening-audio','omi-search'])
    manager=ToolManager(o,c,adapter.get_last_formatted_tools_dict())
    report={'start':now(),'calls':[]}
    async with MCPClient(registry) as client:
        async def read(owner,name,args):
            info=manager.get_tool(owner+'::'+name)
            ex=ToolExecutor(client,manager)
            assert ex.check_call(owner+'::'+name,args).allowed
            result=await client.call_tool(owner,name,args,expected_schema_digest=schema_digest(info.input_schema),
                                          expected_output_digest=schema_digest(info.output_schema))
            data=result.structured_content or {}
            row={'tool':owner+'::'+name,'args_sha256':sha(canonical_json(args)),'schema_sha256':schema_digest(info.input_schema),
                 'input_schema':info.input_schema,'call_id':result.execution_id,'status':result.status,'reason_code':result.reason_code,'duration_s':result.duration_seconds,
                 'started':result.started_at,'finished':result.completed_at,'received':result.result_received,
                 'result_sha256':sha(result.model_text()),'keys':list(data),'source_error':(data.get('error',{}).get('code') if isinstance(data.get('error'),dict) else None)}
            if owner=='omi-search':
                row.update(arguments=args,contains_2330='2330' in result.model_text(),
                           evidence=result.model_text()[:900])
            if owner=='listening-audio' and not result.is_error:
                row['returned_question_matches']=args.get('questionId') in result.model_text()
            report['calls'].append(row);save('business-readback.json',report)
            return not result.is_error
        await read('omi-search','omi_search_tw_symbols',{'keyword':'2330','limit':1})
        def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:18811'+path,timeout=8))
        sets=get('/api/sets')['sets']
        report['trainer_catalog']={'kind':'documented legacy GET /api/sets and study view','candidate_count':len(sets)}
        for item in sets:
            sid=item['set_id']; view=get('/api/sets/'+urllib.parse.quote(sid,safe='')+'/study')
            questions=view['set'].get('questions',[])
            if questions and await read('listening-audio','listening_get_question',
                {'setId':sid,'questionId':questions[0]['id']}):break
        report['end']=now();save('business-readback.json',report)
if __name__=='__main__':asyncio.run(main())
