import json
import unittest
import os
import tempfile
from pathlib import Path
from open_llm_vtuber.chat_history_manager import create_new_history, store_message
from open_llm_vtuber.chat_event_manager import store_history_event
from open_llm_vtuber.character_memory_manager import process_character_memory_turn
from unittest.mock import patch, AsyncMock, Mock
from types import SimpleNamespace
from loguru import logger
from open_llm_vtuber.mcpp.privacy import project, safe_text, argument_summary
from test_mcp_m0_integration import make_executor


class PrivacyProjectionTests(unittest.TestCase):
    def test_history_events_and_memory_exclude_callback(self):
        cwd=os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.dict(os.environ,{'KURO_MEMORY_ROOT':str(Path(folder)/'memory')}):
                    uid=create_new_history('test')
                    callback='https://localhost/callback?code=sentinel&state=sentinel'
                    store_message('test',uid,'human',callback)
                    store_history_event(conf_uid='test',history_uid=uid,event_type='tool_call',detail={'nested':{'token':'sentinel'},'status':'partial'},compact_detail=False)
                    changed,_=process_character_memory_turn(conf_uid='test',history_uid=uid,user_text='請記住 '+callback)
                    self.assertFalse(changed)
                    for path in Path(folder).rglob('*'):
                        if path.is_file():
                            self.assertNotIn('sentinel',path.read_text(encoding='utf-8'))
            finally:
                os.chdir(cwd)
    def test_nested_json_url_and_header_secrets(self):
        for value in (
            {'nested':[{'access_token':'sentinel'}]},
            '{"refresh_token":"sentinel"}',
            'https://localhost/callback?code=sentinel&state=sentinel',
            'Authorization: Bearer sentinel',
        ):
            self.assertNotIn('sentinel',str(project(value)))
        self.assertNotIn('sentinel',argument_summary({'any':'sentinel'}))

    def test_projection_preserves_domain_limits_and_code(self):
        value={'status':'partial','missing':['bars'],'warnings':['stale'],'code':503,'freshness':'missing'}
        self.assertEqual(project(value),value)
        code='const state = loadState();\nconst code = readFile();'
        self.assertEqual(safe_text(code),code)
        self.assertEqual(safe_text('ordinary project evidence'),'ordinary project evidence')

    def test_privacy_precedes_truncation(self):
        text='ordinary '*1000+'https://example.invalid/callback?code=sentinel'
        self.assertNotIn('sentinel',safe_text(text,limit=100))
        self.assertIn('omitted',safe_text(text,limit=100))


class PrivacyExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_exception_and_prompt_logs_do_not_copy_payload(self):
        from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM as OpenAILLM
        from open_llm_vtuber.agent.stateless_llm.claude_llm import AsyncLLM as ClaudeLLM
        from openai import APIError
        import httpx
        messages=[{'role':'user','content':'sentinel'}]
        for cls in (OpenAILLM,ClaudeLLM):
            provider=object.__new__(cls)
            provider.model, provider.base_url, provider.temperature, provider.support_tools = 'fixture','https://example.invalid',0,True
            provider.system=''
            if cls is OpenAILLM:
                request=AsyncMock(side_effect=APIError('sentinel',httpx.Request('GET','https://example.invalid'),body=None))
                provider.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request)))
            else:
                context=AsyncMock()
                context.__aenter__.side_effect=RuntimeError('sentinel')
                request=Mock(return_value=context)
                provider.client=SimpleNamespace(messages=SimpleNamespace(stream=request))
            logs=[]
            sink=logger.add(lambda message: logs.append(str(message)),level='TRACE')
            try:
                events=[]
                try:
                    async for event in provider.chat_completion(messages):
                        events.append(event)
                except RuntimeError as error:
                    events.append(str(error))
            finally:
                logger.remove(sink)
            self.assertNotIn('sentinel',''.join(logs)+str(events))
            # Privacy projection must not change the actual provider request.
            self.assertIn('sentinel',str(request.call_args))

    async def test_malformed_input_never_logged(self):
        executor,manager,client=make_executor()
        logs=[]
        sink=logger.add(lambda message: logs.append(str(message)))
        try:
            events=[e async for e in executor.execute_tools([{'input':{'token':'sentinel'}}],'Prompt')]
        finally:
            logger.remove(sink)
        self.assertNotIn('sentinel',''.join(logs))
        self.assertNotIn('sentinel',str(events))
        client.call_tool.assert_not_awaited()

    async def test_reflected_exception_not_logged_or_displayed(self):
        executor,manager,client=make_executor()
        client.call_tool.side_effect=RuntimeError('sentinel')
        logs=[]
        sink=logger.add(lambda message: logs.append(str(message)))
        try:
            events=[e async for e in executor.execute_tools([{'id':'call','name':'a::read','input':{'count':1}}],'Prompt')]
        finally:
            logger.remove(sink)
        self.assertNotIn('sentinel',''.join(logs))
        self.assertNotIn('sentinel',str(events))
