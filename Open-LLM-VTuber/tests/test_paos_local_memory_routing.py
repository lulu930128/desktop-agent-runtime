"""Formal Kuro registry/catalog with captured schemas; no external service/data IO."""
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mcp.types import Tool
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.server_registry import ServerRegistry, HTTP_READ_TOOLS
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.types import DiscoveryResult

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "Open-LLM-VTuber"
CASES = (
    ("幫我看看個人資產系統是否正常", "get_asset_system_status"),
    ("PAOS 服務狀態如何", "get_asset_system_status"),
    ("我的資產總額有多少", "get_asset_overview"),
    ("查帳戶餘額", "list_asset_accounts"),
    ("看看投資部位", "list_asset_positions"),
    ("近期交易紀錄", "list_recent_asset_transactions"),
    ("有什麼待處理財務事件", "get_pending_financial_events"),
    ("對帳狀況", "get_reconciliation_status"),
    ("我的資產配置如何", "get_asset_overview"),
    ("看看持倉", "list_asset_positions"),
    ("檢查帳務一致性", "get_reconciliation_status"),
)


class PaosLocalMemoryRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ServerRegistry(RUNTIME / "mcp_servers.json")
        cls.catalog = ToolCatalog(json.loads((RUNTIME / "tool_catalog.json").read_text(encoding="utf-8")))
        cls.policy = ToolPolicy(json.loads((RUNTIME / "tool_policy.json").read_text(encoding="utf-8")))
        captured = json.loads((ROOT / "docs/agent-runs/kuro-conversation-mcp-20261024/Discovery.json").read_text(encoding="utf-8"))
        http = json.loads((ROOT / "docs/agent-runs/kuro-http-mcp-20261024/LiveMetadata.json").read_text(encoding="utf-8"))
        cls.snapshots = {**captured, **http}
        cls.discovered = []

        async def discover(_client, server):
            cls.discovered.append(server)
            if server == "kuro-filesystem":
                # History owner/routing fixture only; never query private history.
                tools = [Tool(name="search_past_conversations", inputSchema={"type": "object"})]
            else:
                snapshot = cls.snapshots[server]
                assert snapshot["complete"]
                tools = [Tool.model_validate(row) for row in snapshot["tools"]]
            return DiscoveryResult(server_id=server, complete=True, tools=tools)

        async def build():
            adapter = ToolAdapter(cls.registry)
            names = [name for name in cls.registry.servers if name in cls.snapshots or name == "kuro-filesystem"]
            with patch.object(MCPClient, "discover_tools", discover):
                _, openai, claude = await adapter.get_tools(names)
            assert not adapter.schema_errors
            cls.manager = ToolManager(openai, claude, adapter.get_last_formatted_tools_dict(), tool_catalog=cls.catalog)
        asyncio.run(build())

    def route(self, question):
        tools = self.manager.get_formatted_tools("OpenAI", request_text=question)
        return [self.manager.resolve_tool_name(row["function"]["name"]) for row in tools]

    def test_memory_core_eight_absent_and_local_history_retained(self):
        self.assertNotIn("memory-core", self.registry.servers)
        self.assertNotIn("memory-core", self.discovered)
        absent = {"memory-core::" + name for name in HTTP_READ_TOOLS["memory-core"]}
        self.assertEqual(len(absent), 8)
        self.assertTrue(absent.isdisjoint(self.manager.tools))
        exposed = {self.manager.resolve_tool_name(row["function"]["name"])
                   for row in self.manager.get_formatted_tools("OpenAI")}
        self.assertTrue(absent.isdisjoint(exposed))
        history = "kuro-filesystem::search_past_conversations"
        self.assertIn(history, self.manager.tools)
        self.assertIn("memory", self.catalog.categories)
        self.assertEqual(self.route("幫我搜尋過去聊天記憶")[0], history)
        self.assertTrue(self.policy.check(history, {}).allowed)

    def test_paused_memory_canonical_definitions_remain_restorable(self):
        retained = {row["name"] for row in self.catalog.categories["memory_core"]["tools"]}
        self.assertEqual(retained, {"memory-core::" + name for name in HTTP_READ_TOOLS["memory-core"]})
        self.assertTrue(retained.issubset(self.policy.tools))
        self.assertIn("接線目前暫停", self.catalog.categories["memory_core"]["description"])

    def test_paos_seven_visible_readonly_with_owner_permissions(self):
        expected = {"personal-asset-os::" + name for name in HTTP_READ_TOOLS["personal-asset-os"]}
        actual = {name for name in self.manager.tools if name.startswith("personal-asset-os::")}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 7)
        self.assertNotIn("max_candidate_tools", json.loads((RUNTIME / "tool_catalog.json").read_text(encoding="utf-8"))["routing"])
        self.assertTrue(self.registry.servers["personal-asset-os"].require_read_only)
        for name in actual:
            self.assertEqual(self.policy.tools[name]["mode"], "read_only")

    def test_paos_natural_requests_rank_intended_tool_first(self):
        for question, name in CASES:
            with self.subTest(question=question):
                tools = self.route(question)
                self.assertEqual(tools[0], "personal-asset-os::" + name)
                self.assertEqual(len(tools), len(set(tools)))

    def test_general_system_health_does_not_route_paos(self):
        for question in ("一般電腦系統是否正常", "Windows 連線是否正常", "Python 服務健康嗎"):
            with self.subTest(question=question):
                self.assertFalse(any(name.startswith("personal-asset-os::") for name in self.route(question)))

    def test_omi_and_study_listening_routes_remain_available(self):
        for question, expected in (
            ("可以幫我看看昨天美股的大致狀況嗎", "omi-search::omi_ask"),
            ("幫我看目前日文學習進度摘要", "japanese-study::study_get_summary"),
            ("幫我看看英文學習進度摘要", "english-study::english_get_summary"),
            ("聽力練習服務目前正常嗎", "listening-audio::listening_health"),
        ):
            with self.subTest(question=question):
                self.assertEqual(self.route(question)[0], expected)


if __name__ == "__main__":
    unittest.main()
