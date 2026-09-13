import copy
import unittest
from unittest.mock import AsyncMock
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_result import ToolResult
from open_llm_vtuber.mcpp.tool_schema import schema_digest
from open_llm_vtuber.mcpp.types import FormattedTool, ToolCallObject, ToolCallFunctionObject


def make_executor():
    adapter=object.__new__(ToolAdapter)
    adapter.schema_profile='openai_non_strict'
    schema={'type':'object','properties':{'count':{'type':'integer','minimum':1,'maximum':3},'token':{'type':'string'}},'required':['count']}
    tools={f'{server}::read':FormattedTool(copy.deepcopy(schema),server,canonical_id=f'{server}::read',wire_name='read') for server in ('a','b')}
    o,c=adapter.format_tools_for_api(tools)
    manager=ToolManager(o,c,tools)
    client=AsyncMock()
    client.call_tool.return_value=ToolResult(content_items=[{'type':'text','text':'first'},{'type':'text','text':'last'}],structured_content={'status':'partial'})
    executor=ToolExecutor(client,manager)
    executor._tool_policy=ToolPolicy({'tools':{name:{'mode':'read_only'} for name in tools}})
    return executor,manager,client


class ExecutorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_callers_dispatch_wire_name_to_exact_server(self):
        for mode in ('OpenAI','Claude','Prompt'):
            executor,manager,client=make_executor()
            name=manager.tools['b::read'].api_name
            call=ToolCallObject(id='call',function=ToolCallFunctionObject(name=name,arguments='{"count":2}')) if mode=='OpenAI' else {'id':'call','name':name,'input':{'count':2}}
            events=[event async for event in executor.execute_tools([call],mode)]
            client.call_tool.assert_awaited_once_with(server_name='b',tool_name='read',tool_args={'count':2}, expected_schema_digest=manager.tools['b::read'].schema_digest, expected_output_digest=schema_digest(None))
            result=str(events[-1]['results'])
            self.assertIn('first',result)
            self.assertIn('last',result)
            self.assertIn('partial',result)

    async def test_invalid_policy_and_schema_have_zero_side_effects(self):
        for mode,args in [('unknown',{'count':2}),('confirm',{'count':2}),('read_only',{'count':9})]:
            executor,manager,client=make_executor()
            executor._tool_policy=ToolPolicy({'tools':{'a::read':{'mode':mode}}})
            events=[e async for e in executor.execute_tools([{'id':'call','name':'a::read','input':args}],'Prompt')]
            self.assertEqual(events[0]['status'],'blocked')
            client.call_tool.assert_not_awaited()
            await executor.run_single_tool('a::read','direct',args)
            client.call_tool.assert_not_awaited()

    async def test_prompt_server_cannot_rebind_identity(self):
        executor,manager,client=make_executor()
        calls=executor.process_tool_from_prompt_json([{'mcp_server':'missing','tool':'read','arguments':'{"count":2}'}])
        events=[e async for e in executor.execute_tools(calls,'Prompt')]
        client.call_tool.assert_not_awaited()

    async def test_snapshot_and_actual_arguments_preserved(self):
        executor,manager,client=make_executor()
        args={'count':2,'token':'private-sentinel'}
        client.call_tool.return_value=ToolResult(content_items=[{'type':'text','text':'echo private-sentinel'}])
        events=[e async for e in executor.execute_tools([{'id':'call','name':'a::read','input':args}],'OpenAI')]
        client.call_tool.assert_awaited_once_with(server_name='a',tool_name='read',tool_args=args, expected_schema_digest=manager.tools['a::read'].schema_digest, expected_output_digest=schema_digest(None))
        self.assertNotIn('private-sentinel',str(events))
        self.assertEqual(args['token'],'private-sentinel')

    async def test_malformed_identity_and_prompt_items_have_zero_io(self):
        executor, _, client = make_executor()
        calls = [{'id':'x','name':[],'input':{}}, {'id':{},'name':'a::read','input':{}}, ToolCallObject(id='x',function=None)]
        events = [e async for e in executor.execute_tools(calls,'Prompt')]
        self.assertEqual(events[0]['status'],'error')
        self.assertEqual(executor.process_tool_from_prompt_json([None,[],{}]),[])
        client.call_tool.assert_not_awaited()
