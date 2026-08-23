import unittest

from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy


class OmiToolPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ToolPolicy.load_default()

    def test_omi_allows_trusted_readonly_llm_flag(self) -> None:
        decision = self.policy.check(
            "omi.ask",
            {
                "question": "請分析 2330",
                "mode": "analysis",
                "allow_llm": True,
                "allow_write": False,
            },
        )

        self.assertTrue(decision.allowed, decision.reason)

    def test_omi_still_blocks_write_and_persisted_report(self) -> None:
        write_decision = self.policy.check(
            "omi.ask",
            {
                "question": "請分析 2330",
                "mode": "analysis",
                "allow_llm": True,
                "allow_write": True,
            },
        )
        report_decision = self.policy.check(
            "omi.ask",
            {
                "question": "請產生 2330 報告",
                "mode": "report",
                "allow_llm": True,
                "allow_write": False,
            },
        )

        self.assertFalse(write_decision.allowed)
        self.assertIn("allow_write", write_decision.reason)
        self.assertFalse(report_decision.allowed)
        self.assertIn("mode", report_decision.reason)

    def test_omi_allows_bounded_external_fetch_budget(self) -> None:
        decision = self.policy.check(
            "omi.ask",
            {
                "question": "??? 2330",
                "mode": "analysis",
                "allow_llm": True,
                "allow_external_fetch": True,
                "allow_write": False,
                "tool_budget": {
                    "max_calls": 5,
                    "max_external_fetches": 3,
                    "max_total_seconds": 25,
                },
            },
        )

        self.assertTrue(decision.allowed, decision.reason)

    def test_omi_blocks_over_budget_external_fetch(self) -> None:
        decision = self.policy.check(
            "omi.ask",
            {
                "question": "??? 2330",
                "mode": "analysis",
                "allow_llm": True,
                "allow_external_fetch": True,
                "allow_write": False,
                "tool_budget": {
                    "max_calls": 6,
                    "max_external_fetches": 4,
                    "max_total_seconds": 30,
                },
            },
        )

        self.assertFalse(decision.allowed)
        self.assertIn("tool_budget.max_calls", decision.reason)


if __name__ == "__main__":
    unittest.main()
