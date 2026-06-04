import unittest

from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog


AVAILABLE_TOOLS = [
    "omi.ask",
    "advanced_search_web",
    "smart_search_web",
    "search_web",
    "fetch_content",
]


class ToolCatalogMarketRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ToolCatalog.load_default()

    def route_tools(self, request_text: str) -> list[str]:
        return self.catalog.route(request_text, AVAILABLE_TOOLS).tool_names

    def test_stock_status_uses_omi_first_without_web(self) -> None:
        self.assertEqual(
            self.route_tools("可以幫我查2330這支股票狀況嗎"),
            ["omi.ask"],
        )

    def test_current_stock_status_keeps_web_fallback(self) -> None:
        tools = self.route_tools("可以幫我看今天2303這支股票的狀況嗎")
        self.assertEqual(tools[0], "omi.ask")
        self.assertIn("advanced_search_web", tools)

    def test_cjk_adjacent_stock_code_keeps_omi_before_web(self) -> None:
        tools = self.route_tools("2330今天最新消息")
        self.assertGreaterEqual(len(tools), 2)
        self.assertEqual(tools[0], "omi.ask")
        self.assertIn("advanced_search_web", tools)

    def test_stock_realtime_quote_keeps_web_as_enrichment(self) -> None:
        tools = self.route_tools("2330即時股價")
        self.assertEqual(tools[0], "omi.ask")
        self.assertIn("advanced_search_web", tools)

    def test_non_market_latest_query_stays_web_first(self) -> None:
        tools = self.route_tools("請查最新OpenAI文件")
        self.assertNotIn("omi.ask", tools)
        self.assertEqual(tools[0], "advanced_search_web")

    def test_confirmation_followup_keeps_market_route_from_context(self) -> None:
        tools = self.route_tools(
            "user: 可以幫我查查台積電的數據嗎\n"
            "assistant: 想要哪個期間的歷史財報？\n"
            "user: 幫我查近五年的吧\n"
            "assistant: 我就抓最近五個完整會計年度，這樣可以嗎？\n"
            "user: 可以"
        )
        self.assertEqual(tools[0], "omi.ask")


if __name__ == "__main__":
    unittest.main()
