import math
import unittest
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy


class PolicyTests(unittest.TestCase):
    def test_unknown_modes_and_confirmation_fail_closed(self):
        for mode, code in [('confrim','unknown_policy_mode'),('unknown','unknown_policy_mode'),('scoped_auto','unsupported_policy_mode'),('confirm','confirmation_required'),('disabled','policy_disabled'),('deny','policy_disabled')]:
            decision=ToolPolicy({'tools':{'x':{'mode':mode}}}).check('x',{})
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.status,'blocked')
            self.assertEqual(decision.reason_code,code)
        self.assertFalse(ToolPolicy({'tools':{}}).check('x',{}).allowed)

    def test_defaults_and_malformed_rules(self):
        self.assertTrue(ToolPolicy({'default_mode':'read_only','tools':{'x':{}}}).check('x',{}).allowed)
        for cfg in ({'path_args':'path'}, {'max_numeric_args':[]}, {'url_args':[{}]}, {'allow_hidden':'false'}, {'max_numeric_args':{'limit':float('inf')}}, {'deny_values':{'mode':{}}}, {'max_numerik_args':{'limit':1}}):
            self.assertFalse(ToolPolicy({'tools':{'x':{'mode':'read_only',**cfg}}}).check('x',{}).allowed)
        self.assertFalse(ToolPolicy({'tools':{'x':{'mode':'read_only'}},'filesystem':[]}).check('x',{}).allowed)
        self.assertFalse(ToolPolicy({'tools':{'x':{'mode':'read_only','deny_values':{'value':[math.nan]}}}}).check('x',{}).allowed)

    def test_numeric_bounds_and_nonfinite_args(self):
        policy=ToolPolicy({'tools':{'x':{'mode':'read_only','max_numeric_args':{'budget.max':5}}}})
        for value in (6, math.nan, math.inf, -math.inf, True, 'invalid'):
            self.assertFalse(policy.check('x',{'budget':{'max':value}}).allowed)
        self.assertTrue(policy.check('x',{'budget':{'max':5}}).allowed)

    def test_canonical_deny_and_fixed_owner(self):
        policy=ToolPolicy({'tools':{'omi.ask':{'mode':'read_only'},'omi-market::omi.ask':{'mode':'deny'}}})
        self.assertFalse(policy.check('omi.ask',{}).allowed)
        self.assertFalse(policy.check('other::omi.ask',{}).allowed)
        policy=ToolPolicy({'tools':{'omi.ask':{'mode':'read_only'}}})
        self.assertTrue(policy.check('omi-market::omi.ask',{}).allowed)
        self.assertFalse(policy.check('other::omi.ask',{}).allowed)

    def test_policy_snapshot_is_not_mutated_by_caller(self):
        cfg={'tools':{'x':{'mode':'deny'}}}
        policy=ToolPolicy(cfg)
        cfg['tools']['x']['mode']='read_only'
        self.assertFalse(policy.check('x',{}).allowed)
