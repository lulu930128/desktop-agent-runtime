"""Isolated formal registry, retirement, routing and annotation regression tests."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from mcp.types import Tool, ToolAnnotations
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog
from open_llm_vtuber.mcpp.tool_identity import legacy_canonical
from open_llm_vtuber.mcpp.types import DiscoveryResult

RUNTIME = Path(__file__).resolve().parents[1]
NEW = {'omi-search': 15, 'japanese-study': 10, 'english-study': 10, 'listening-audio': 3}


class ConversationMcpTests(unittest.TestCase):
    def test_formal_inventory_and_discovery_are_consistent(self):
        config = json.loads((RUNTIME / 'mcp_servers.json').read_text(encoding='utf-8'))['mcp_servers']
        discovery = json.loads((RUNTIME.parent / 'docs/agent-runs/kuro-conversation-mcp-20261024/Discovery.json').read_text(encoding='utf-8'))
        policy = ToolPolicy.load_default()
        self.assertNotIn('omi-market', config)
        self.assertEqual(legacy_canonical('omi.ask'), 'omi-market::omi.ask')
        for server in NEW:
            self.assertNotIn("allowed_tools", config[server])
            self.assertFalse(config[server].get("require_read_only", False))
            self.assertIn(server, policy.owner_services)
            self.assertTrue(discovery[server]["complete"])
            for row in discovery[server]["tools"]:
                self.assertTrue(policy.check(server + "::" + row["name"], {}).allowed)

    def test_retired_registry_cannot_spawn_from_stale_config(self):
        with tempfile.TemporaryDirectory(dir=RUNTIME.parent / '.tmp') as temp:
            path = Path(temp) / 'servers.json'
            path.write_text(json.dumps({'mcp_servers': {'omi-market': {'command': 'never-start', 'args': []}}}))
            self.assertIsNone(ServerRegistry(path).get_server('omi-market'))

    def test_no_production_market_transport_or_autorun(self):
        package = RUNTIME / 'src/open_llm_vtuber'
        helper = (package / 'mcpp/market_preflight.py').read_text(encoding='utf-8')
        agent = (package / 'agent/agents/basic_memory_agent.py').read_text(encoding='utf-8')
        for forbidden in ('stream_omi_ask_events', 'build_autonomous_omi_args', 'should_autorun_omi', '/api/ai/ask/stream', 'OMI_API_BASE_URL'):
            self.assertNotIn(forbidden, helper + agent)
        imports = [node for node in ast.walk(ast.parse(helper)) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any('urllib' in ast.unparse(node) or 'httpx' in ast.unparse(node) for node in imports))
        self.assertNotIn('omi-market', (RUNTIME / 'tool_catalog.json').read_text(encoding='utf-8'))

    def test_lookup_routing_reaches_each_read_subset(self):
        catalog = ToolCatalog.load_default()
        available = [row["name"] for group in catalog.categories.values() for row in group["tools"]]
        for text, expected in (
            ('台股市場股票', 'omi-search::omi_ask'),
            ('日文練習紀錄', 'japanese-study::study_list_practice_sessions'),
            ('英文參考資料', 'english-study::english_search_reference_entries'),
            ('英文雅思進度', 'english-study::english_get_ielts_progress'),
            ('日文待複習', 'japanese-study::study_get_due_reviews'),
            ('聽力題目', 'listening-audio::listening_get_question'),
        ):
            with self.subTest(text=text):
                self.assertIn(expected, catalog.route(text, available).tool_names)

    def test_full_inventory_keeps_explicit_news_enrichment(self):
        catalog = ToolCatalog.load_default()
        available = [row['name'] for group in catalog.categories.values() for row in group['tools']]
        route = catalog.route('TSMC stock latest news', available)
        self.assertEqual(route.tool_names[0], 'omi-search::omi_ask')
        self.assertIn('kuro-web::advanced_search_web', route.tool_names)
        self.assertEqual(len(route.tool_names), len(set(route.tool_names)))


class AnnotationDriftTests(unittest.IsolatedAsyncioTestCase):
    async def test_readonly_annotation_drift_blocks_adapter_and_client(self):
        config = {'mcp_servers': {'fixture': {'command': 'never-start', 'args': [], 'allowed_tools': ['lookup'], 'require_read_only': True}}}
        with tempfile.TemporaryDirectory(dir=RUNTIME.parent / '.tmp') as temp:
            path = Path(temp) / 'servers.json'
            path.write_text(json.dumps(config))
            registry = ServerRegistry(path)
            for annotations in (None, ToolAnnotations(readOnlyHint=False)):
                tool = Tool(name='lookup', inputSchema={'type': 'object'}, annotations=annotations)
                result = DiscoveryResult(server_id='fixture', complete=True, tools=[tool])
                with patch.object(MCPClient, 'discover_tools', AsyncMock(return_value=result)):
                    adapter = ToolAdapter(registry)
                    await adapter.get_tools(['fixture'])
                    self.assertFalse(adapter.get_last_formatted_tools_dict())
                    async with MCPClient(registry) as client:
                        with patch.object(client, '_ensure_server_running_and_get_session', AsyncMock()) as connect:
                            outcome = await client.call_tool('fixture', 'lookup', {})
                            self.assertTrue(outcome.is_error)
                            self.assertFalse(outcome.may_have_executed)
                            connect.assert_not_awaited()
