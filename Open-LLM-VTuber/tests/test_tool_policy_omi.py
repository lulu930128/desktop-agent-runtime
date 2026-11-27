import unittest
import json
from pathlib import Path
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy

class OmiPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = ToolPolicy(json.loads((Path(__file__).parent / "fixtures/legacy_tool_grants.json").read_text(encoding="utf-8")))
        self.name = 'omi-search::omi_ask'

    def test_cache_only_v4_data_queries(self):
        self.assertTrue(self.policy.check(self.name, {'question': 'fixture', 'target': {'type': 'auto'},
            'mode': 'data_only', 'refresh_if_missing': False, 'contract_version': 'omi.decision.v4',
            'tool_budget': {'max_calls': 5, 'max_external_fetches': 0, 'max_total_seconds': 25}}).allowed)
        self.assertTrue(self.policy.check(self.name, {'question': 'fixture'}).allowed)

    def test_retired_aliases_never_remap_even_with_old_policy(self):
        for policy in (self.policy, ToolPolicy({'tools': {'omi.ask': {'mode': 'read_only'}, 'omi-market::omi.ask': {'mode': 'read_only'}}})):
            for name in ('omi.ask', 'omi.ask_stream', 'omi-market::omi.ask', 'omi-market::omi.ask_stream'):
                self.assertFalse(policy.check(name, {}).allowed)

    def test_privileged_and_old_arguments_fail_closed(self):
        for args in ({'mode': 'brief'}, {'mode': 'full'}, {'mode': 'analysis'}, {'mode': 'report'}, {'mode': 'auto'},
                     {'caller_profile': 'kuro_readonly'}, {'allow_llm': False}, {'allow_write': False},
                     {'allow_external_fetch': False}, {'contract_version': 'omi.decision.v3'}, {'query': 'fixture'},
                     {'refresh_if_missing': True}, {'refresh_if_missing': 'false'}, {'refresh_if_missing': 0},
                     {'tool_budget': {'max_calls': 6}}, {'tool_budget': {'max_external_fetches': 1}},
                     {'tool_budget': {'max_total_seconds': 26}}):
            with self.subTest(args=args):
                self.assertFalse(self.policy.check(self.name, args).allowed)

    def test_invalid_policy_rules_fail_closed(self):
        for rules in ({'allow_values': []}, {'allow_values': {'mode': 'data_only'}}, {'deny_present_args': 'allow_llm'}):
            policy = ToolPolicy({'tools': {self.name: {'mode': 'read_only', **rules}}})
            self.assertFalse(policy.check(self.name, {}).allowed)
