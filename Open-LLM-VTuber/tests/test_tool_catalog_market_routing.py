import unittest

from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog


AVAILABLE_TOOLS = [
    "omi-search::omi_ask",
    "advanced_search_web",
    "smart_search_web",
    "search_web",
    "fetch_content",
]


class ToolCatalogMarketRoutingTest(unittest.TestCase):
    def test_capability_and_freshness_question_exposes_both_read_tools(self):
        catalog = ToolCatalog.load_default()
        available = [tool['name'] for category in catalog.categories.values()
                     for tool in category.get('tools', [])]
        question = '你可以用 OMI 工具嗎？請實際查能力狀態與台灣資料新鮮度，告訴我目前能分析到什麼程度。只讀快取，不刷新或產生付費報告。'
        for depth in ('normal', 'deep'):
            selected = catalog.route(question, available, thinking_power=depth).tool_names
            self.assertIn('omi-search::omi_read_capability_status', selected)
            self.assertIn('omi-search::omi_read_data_freshness', selected)

    def setUp(self) -> None:
        self.catalog = ToolCatalog.load_default()

    def route_tools(self, request_text: str) -> list[str]:
        return self.catalog.route(request_text, AVAILABLE_TOOLS).tool_names

    def test_stock_status_uses_omi_first_without_web(self) -> None:
        self.assertEqual(
            self.route_tools("可以幫我查2330這支股票狀況嗎"),
            ["omi-search::omi_ask"],
        )

    def test_us_market_requests_use_omi_first(self) -> None:
        for text in (
            "可以幫我看看昨天美股的大致狀況嗎",
            "美股昨天收盤如何",
            "昨天美國股市大盤",
            "昨天美國股市收盤如何",
            "How did the US market close yesterday?",
            "U.S. equities yesterday",
            "NASDAQ yesterday",
            "S&P 500 yesterday",
            "道瓊昨天收盤如何",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.route_tools(text), ["omi-search::omi_ask"])

    def test_time_and_close_without_market_context_do_not_route_omi(self) -> None:
        for text in ("昨天過得如何", "昨天", "收盤", "這家店昨天收盤後幾點打掃", "yesterday", "close the window"):
            with self.subTest(text=text):
                self.assertNotIn("omi-search::omi_ask", self.route_tools(text))

    def test_explicit_no_tools_still_wins_for_us_market(self) -> None:
        self.assertEqual(self.route_tools("不用工具，昨天美股的大致狀況"), [])

    def test_current_stock_status_keeps_web_fallback(self) -> None:
        tools = self.route_tools("可以幫我看今天2303這支股票的狀況嗎")
        self.assertEqual(tools[0], "omi-search::omi_ask")
        self.assertIn("advanced_search_web", tools)

    def test_cjk_adjacent_stock_code_keeps_omi_before_web(self) -> None:
        tools = self.route_tools("2330今天最新消息")
        self.assertGreaterEqual(len(tools), 2)
        self.assertEqual(tools[0], "omi-search::omi_ask")
        self.assertIn("advanced_search_web", tools)

    def test_stock_realtime_quote_keeps_web_as_enrichment(self) -> None:
        tools = self.route_tools("2330即時股價")
        self.assertEqual(tools[0], "omi-search::omi_ask")
        self.assertIn("advanced_search_web", tools)

    def test_non_market_latest_query_stays_web_first(self) -> None:
        tools = self.route_tools("請查最新OpenAI文件")
        self.assertNotIn("omi-search::omi_ask", tools)
        self.assertEqual(tools[0], "advanced_search_web")

    def test_confirmation_followup_keeps_market_route_from_context(self) -> None:
        tools = self.route_tools(
            "user: 可以幫我查查台積電的數據嗎\n"
            "assistant: 想要哪個期間的歷史財報？\n"
            "user: 幫我查近五年的吧\n"
            "assistant: 我就抓最近五個完整會計年度，這樣可以嗎？\n"
            "user: 可以"
        )
        self.assertEqual(tools[0], "omi-search::omi_ask")


if __name__ == "__main__":
    unittest.main()
