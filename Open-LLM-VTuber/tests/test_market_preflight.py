import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from open_llm_vtuber.mcpp.market_preflight import (
    build_autonomous_omi_args,
    extract_omi_resolution_from_tool_results,
    format_omi_response_for_llm,
)


class MarketPreflightTest(unittest.TestCase):
    def test_builds_readonly_omi_question_without_stock_parsing(self) -> None:
        args = build_autonomous_omi_args(
            current_text="幫我查2330近五年財報",
            route_text="user: 幫我查2330近五年財報",
        )

        self.assertEqual(args["contract_version"], "omi.ai.ask.v2")
        self.assertEqual(args["target"], {"type": "auto"})
        self.assertEqual(args["mode"], "auto")
        self.assertEqual(args["caller_profile"], "kuro_readonly")
        self.assertTrue(args["allow_llm"])
        self.assertFalse(args["allow_write"])
        self.assertTrue(args["allow_external_fetch"])
        self.assertEqual(args["tool_budget"]["max_calls"], 5)
        self.assertEqual(args["tool_budget"]["max_external_fetches"], 3)
        self.assertNotIn("refresh_policy", args)
        self.assertIn("conversation_context", args)
        self.assertNotIn("scope_id", args)
        self.assertNotIn("scope_type", args)
        self.assertNotIn("strategy_profile", args)
        self.assertIn("2330", args["question"])

    def test_keeps_recent_context_for_omi_to_resolve_followup(self) -> None:
        args = build_autonomous_omi_args(
            current_text="可以",
            route_text=(
                "user: 可以幫我查查台積電的數據嗎\n"
                "assistant: 想要哪個期間的歷史財報？\n"
                "user: 幫我查近五年的吧\n"
                "assistant: 我就抓最近五個完整會計年度，這樣可以嗎？\n"
                "user: 可以"
            ),
        )

        self.assertEqual(args["target"], {"type": "auto"})
        self.assertNotIn("scope_id", args)
        self.assertIn("台積電", args["question"])
        self.assertIn("可以", args["question"])

    def test_includes_last_omi_resolution_for_followup(self) -> None:
        last_resolution = {
            "target": {"type": "tw_stock", "id": "2330", "label": "台積電", "market": "TW"},
            "confidence": "high",
        }

        args = build_autonomous_omi_args(
            current_text="那 ADR 呢",
            route_text="user: 那 ADR 呢",
            last_resolution=last_resolution,
        )

        self.assertEqual(
            args["conversation_context"]["last_resolution"],
            last_resolution,
        )

    def test_formats_omi_v2_response_for_llm_context(self) -> None:
        raw = (
            '{"contract_version":"omi.ai.ask.v2","target":{"type":"tw_stock","id":"2330",'
            '"label":"台積電","market":"TW"},"mode":{"requested":"auto","effective":"brief"},'
            '"resolution":{"target":{"type":"tw_stock","id":"2330","label":"台積電","market":"TW"},'
            '"confidence":"high","assumption":"以台股 2330 台積電為主","candidates":[]},'
            '"clarification":{"required":false},"answer_ready":true,"report_level":"brief",'
            '"next_actions":[{"type":"refresh_data"}],"missing":["margin_trading_daily"],'
            '"warnings":["Local data is incomplete."],"tool_plan":{"provider":"openai"},'
            '"tool_runs":[{"tool":"us.read_intraday_trend","status":"success"}],'
            '"result":{"kind":"stock_brief"}}'
        )

        formatted = format_omi_response_for_llm(raw)

        self.assertIn("OMI v2 result summary", formatted)
        self.assertIn("tw_stock 2330 台積電", formatted)
        self.assertIn("next_actions: refresh_data", formatted)
        self.assertIn("tool_plan_provider: openai", formatted)
        self.assertIn("tool_runs: us.read_intraday_trend:success", formatted)
        self.assertIn("Raw OMI v2 JSON", formatted)

    def test_extracts_omi_resolution_from_tool_results(self) -> None:
        content = (
            '{"contract_version":"omi.ai.ask.v2","resolution":{"target":{"type":"tw_stock",'
            '"id":"2330","label":"台積電","market":"TW"},"confidence":"high"}}'
        )

        resolution = extract_omi_resolution_from_tool_results(
            [{"tool_id": "autonomous_omi_preflight", "content": content}]
        )

        self.assertIsNotNone(resolution)
        self.assertEqual(resolution["target"]["id"], "2330")


if __name__ == "__main__":
    unittest.main()
