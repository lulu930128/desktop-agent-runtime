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


if __name__ == "__main__":
    unittest.main()
