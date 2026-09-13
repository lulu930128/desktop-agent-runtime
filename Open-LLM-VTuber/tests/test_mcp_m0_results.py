import unittest
from mcp.types import CallToolResult, TextContent, ResourceLink, EmbeddedResource, TextResourceContents
from open_llm_vtuber.mcpp.tool_result import normalize_result, ToolResult, MAX_RESULT_BYTES


class ResultTests(unittest.TestCase):
    def test_order_structured_and_resource_identity(self):
        items=[TextContent(type='text',text='first'), ResourceLink(type='resource_link',name='source',uri='file:///source.txt'),
               TextContent(type='text',text='last'),EmbeddedResource(type='resource',resource=TextResourceContents(uri='test://source',text='embedded'))]
        result=normalize_result(CallToolResult(content=items,structuredContent={'status':'partial','warnings':['stale']}))
        self.assertEqual([x['type'] for x in result.content_items],['text','resource_link','text','resource'])
        self.assertEqual(result.text_blocks,['first','last'])
        self.assertEqual(result.resource_links[0]['uri'],'file:///source.txt')
        for value in ('first','last','embedded','partial','stale'):
            self.assertIn(value,result.model_text())

    def test_structured_only_and_empty_success(self):
        result=normalize_result(CallToolResult(content=[],structuredContent={'status':'missing'}))
        self.assertEqual(result.content_items,[])
        self.assertIn('missing',result.model_text())
        empty=normalize_result(CallToolResult(content=[]))
        self.assertFalse(empty.is_error)
        self.assertEqual(empty.status,'succeeded')

    def test_iserror_independent_of_first_item(self):
        result=normalize_result(CallToolResult(content=[TextContent(type='text',text='first')],isError=True))
        self.assertTrue(result.is_error)
        self.assertEqual(result.status,'failed')

    def test_metadata_not_sent_and_sensitive_structured_text_redacted(self):
        result=normalize_result(CallToolResult(content=[TextContent(type='text',text='{"access_token":"sentinel"}'),TextContent(type='text',text='safe')],_meta={'secret':'sentinel'}))
        self.assertEqual(result.private_metadata,{'secret':'sentinel'})
        self.assertNotIn('sentinel',result.model_text())
        self.assertIn('safe',result.model_text())

    def test_limits_do_not_become_empty_success(self):
        result=normalize_result(CallToolResult(content=[TextContent(type='text',text='x'*MAX_RESULT_BYTES)]))
        self.assertTrue(result.is_error)
        self.assertEqual(result.reason_code,'result_too_large')
        text=ToolResult(content_items=[{'type':'text','text':'x'*1000}]).model_text(limit=100)
        self.assertLessEqual(len(text.encode()),100)
        self.assertIn('truncated',text)

    def test_truncation_keeps_source_limits_before_long_prose(self):
        import json
        result = ToolResult(content_items=[{'type':'text','text':json.dumps({'answer':'x'*150000,'missing':['bars'],'warnings':['provider stale']})}])
        text = result.model_text(limit=1000)
        self.assertLessEqual(len(text.encode()),1000)
        self.assertIn('bars',text)
        self.assertIn('provider stale',text)
        self.assertIn('truncated',text)

    def test_claude_mixed_order_and_binary_resource_marker(self):
        result = ToolResult(content_items=[{'type':'text','text':'first'}, {'type':'image','data':'YWJj','mimeType':'image/png'},
                                          {'type':'text','text':'last'}, {'type':'audio','data':'YWJj','mimeType':'audio/wav'},
                                          {'type':'resource','resource':{'uri':'test://binary','blob':'private-binary'}}],
                            structured_content={'status':'partial'})
        blocks = result.claude_content()
        self.assertEqual([x['type'] for x in blocks],['text','image','text','text','text','text'])
        self.assertEqual(blocks[2]['text'],'last')
        self.assertNotIn('private-binary',str(blocks))
        self.assertIn('test://binary',str(blocks))
        self.assertIn('partial',str(blocks))
