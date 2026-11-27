"""Opt-in offline source schemas and fake dispatch; no STDIO or provider startup."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
from unittest.mock import AsyncMock, patch

RUNTIME = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RUNTIME/'src'), str(RUNTIME/'local_mcp')]
from mcp.types import Tool
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_result import ToolResult
from open_llm_vtuber.mcpp.types import FormattedTool


async def verify():
    inventories, digests = {}, {}
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden in source inventory')):
        for server, filename in [('kuro-web','web_tools_server.py'), ('kuro-filesystem','filesystem_tools_server.py'), ('kuro-mail','mail_tools_server.py')]:
            path = RUNTIME/'local_mcp'/filename
            spec = importlib.util.spec_from_file_location('inventory_'+server.replace('-','_'), path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            inventories[server] = await module.mcp.list_tools()
            digests[server] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert [tool.name for tool in inventories['kuro-filesystem']] == ['search_past_conversations']
        # External adapters are verified only through real STDIO in
        # verify_conversation_mcp.py; never import third-party server modules.
    raw = {f'{server}::{tool.name}':FormattedTool(tool.inputSchema,server,canonical_id=f'{server}::{tool.name}',wire_name=tool.name,output_schema=tool.outputSchema) for server,tools in inventories.items() for tool in tools}
    count = len(raw)
    adapter = object.__new__(ToolAdapter)
    adapter.schema_profile = 'openai_non_strict'
    o,c = adapter.format_tools_for_api(raw)
    assert not adapter.schema_errors, adapter.schema_errors
    assert len(o) == len(c) == count
    manager = ToolManager(o,c,raw)
    client = AsyncMock()
    client.call_tool.return_value = ToolResult(content_items=[{'type':'text','text':'isolated provider fixture'}])
    executor = ToolExecutor(client,manager)
    for name,args in [('kuro-web::get_current_time',{}),('kuro-filesystem::search_past_conversations',{'query':'fixture','conf_uid':'synthetic-character'}),
                      ('kuro-mail::mail.list_unread',{})]:
        error,_,_,_ = await executor.run_single_tool(name,'fixture',args)
        assert not error, name
    assert client.call_tool.await_count == 3
    return {'source_counts':{server:len(tools) for server,tools in inventories.items()},'valid_schemas':count,
            'fake_read_dispatches':3,'source_sha256':digests,'live_provider_calls':0,'stdio_started':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    args=parser.parse_args()
    print(json.dumps(asyncio.run(verify()),ensure_ascii=False,indent=2))
