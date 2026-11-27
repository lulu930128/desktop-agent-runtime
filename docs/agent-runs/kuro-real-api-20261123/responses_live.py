"""Observe real SDK streams and Kuro's production OpenAI tool loop, writing only sanitized receipts."""
import re
from live import *
from open_llm_vtuber.agent.stateless_llm_factory import LLMFactory
from open_llm_vtuber.mcpp.tool_schema import schema_digest

async def main():
    cfg=yaml.safe_load((RT/'conf.launcher_runtime.yaml').read_text(encoding='utf-8-sig'))['character_config']
    agent_cfg=cfg['agent_config']; settings=agent_cfg['agent_settings']['basic_memory_agent']
    provider=settings['llm_provider']; opts=agent_cfg['llm_configs'][provider]
    llm=LLMFactory.create_llm(provider,**opts)
    assert str(llm.client.base_url).rstrip('/')=='https://api.openai.com/v1' and llm._uses_responses
    assert settings['use_mcpp'] and set(OWNER_SERVICES)<=set(settings['mcp_enabled_servers'])
    llm.client.max_retries=0
    prompt=(f'請使用工具讀取 Project Workspace 的 projects 根目錄下 {PROBE}。這是本次公開驗收檔。'
            '讀出 receipt 與 lookup；再用 English Study 的公開 Reference Catalog 搜尋 lookup 指定的詞，限傳回一筆。'
            '最後列出檔案裡的 receipt、詞、命中總數及第一筆來源。請自己尋找並載入需要的工具。只讀取這份檔案和公開詞目。')
    record={'start':now(),'credential_present':bool(opts.get('llm_api_key')),'configuration':'conf.launcher_runtime.yaml',
            'model':llm.model,'effort':llm._responses_reasoning_effort,'provider':provider,'role':cfg['conf_uid'],
            'prompt':prompt,'requests':[],'events':[],'complete':False}
    filename='responses-'+datetime.now(timezone.utc).strftime('%H%M%S')+'.json'
    def flush():save(filename,record)
    flush()
    registry,manager=await init()
    real_create=llm.client.responses.create
    async def observe(**kw):
        req={'start':now(),'model':kw['model'],'reasoning':kw.get('reasoning'),'names':[t['name'] for t in kw.get('tools',[])],
             'schema_sha256':{t['name']:schema_digest(t['parameters']) for t in kw.get('tools',[])},
             'input_types':[i.get('type',i.get('role')) for i in kw['input']],'sent_store':kw.get('store'),'function_calls':[]}
        record['requests'].append(req);flush()
        try:
            stream=await real_create(**kw)
        except Exception as e:
            req.update(end=now(),error_type=type(e).__name__,http=getattr(e,'status_code',None),request_id=getattr(e,'request_id',None))
            body=getattr(e,'body',None)
            if isinstance(body,dict):
                err=body.get('error',body)
                if isinstance(err,dict):
                    req['error']={k:str(err[k])[:350] for k in ('code','type','param','message') if err.get(k) and 'key' not in str(err[k]).lower()}
            flush();raise
        req.update(http=stream.response.status_code,request_id=stream.response.headers.get('x-request-id'))
        class Observed:
            def __aiter__(self):
                async def events():
                    async for e in stream:
                        rsp=getattr(e,'response',None)
                        if rsp:
                            req.update(response_id=rsp.id,returned_model=rsp.model,status=rsp.status)
                            if rsp.usage:req['usage']=rsp.usage.model_dump()
                        item=getattr(e,'item',None)
                        if e.type=='response.output_item.done' and getattr(item,'type',None)=='function_call':
                            args=json.loads(item.arguments); req['function_calls'].append({'name':item.name,'call_id':item.call_id,'arguments':args})
                        yield e
                return events()
            async def close(self):
                req['end']=now();flush();await stream.close()
        return Observed()
    llm.client.responses.create=observe
    ws='project-workspace::read_file'; english='english-study::english_search_reference_entries'
    async with MCPClient(registry) as client:
        ex=ToolExecutor(client,manager)
        original=ex.check_call
        def scope(name,args,**kw):
            decision=original(name,args,**kw)
            if name==ws and args.get('path')==PROBE and args.get('root')=='projects':return decision
            if name==english and args.get('query','').lower()=='study':return decision
            return ToolPolicyDecision(False,'blocked','Outside this read-only test scope.','verification_scope')
        ex.check_call=scope
        agent=BasicMemoryAgent.__new__(BasicMemoryAgent)
        agent._tool_manager,agent._tool_executor,agent._llm=manager,ex,llm
        agent._system='你是 Kuro。依使用者要求完成可驗證的工具查詢。'
        agent.prompt_mode_flag=False;agent._memory=[];agent._turn_chat_speech={'route':'tool_verification'}
        answers=[]
        try:
            async for event in agent._openai_tool_interaction_loop([{'role':'user','content':prompt}],[],route_prompt=DISCOVERY_DESCRIPTION):
                if isinstance(event,str):answers.append(event)
                elif isinstance(event,dict) and event.get('type')=='tool_call_status':
                    row={k:event[k] for k in ('tool_id','tool_name','timestamp','status','reason_code','outcome','call_summary') if k in event}
                    content=event.get('content','')
                    row.update(content_sha256=sha(content),contains_challenge=NONCE in content)
                    if row['tool_name']==english and row.get('outcome')=='actual_success':
                        row['reference_result']=content[:2000]
                    record['events'].append(row);flush()
        finally:
            answer=''.join(answers)
            record['answer']=answer[:2600];record['end']=now()
            successes=[e['tool_name'] for e in record['events'] if e.get('outcome')=='actual_success']
            record['complete']=successes==[ws,english] and NONCE in answer and 'study' in answer.lower() and bool(record['requests'][-1].get('status')=='completed')
            flush();await llm.client.close()
    print(filename, record['complete'],len(record['requests']))
if __name__=='__main__':asyncio.run(main())
