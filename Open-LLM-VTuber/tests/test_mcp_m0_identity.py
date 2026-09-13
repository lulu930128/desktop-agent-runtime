import unittest
from open_llm_vtuber.mcpp.tool_identity import canonical_id, legacy_canonical, provider_alias
from open_llm_vtuber.mcpp.tool_adapter import _openai_api_tool_name


class ToolIdentityTests(unittest.TestCase):
    def test_alias_stable_and_unique_in_both_orders(self):
        identities = [canonical_id(server, name) for server, name in (
            ('a', 'read'), ('b', 'read'), ('a', 'a.b'), ('a', 'a_b'), ('a', 'x'*200), ('a::b', 'c'))]
        first = {i: _openai_api_tool_name(i, set()) for i in identities}
        used = set()
        second = {i: _openai_api_tool_name(i, used) for i in reversed(identities)}
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), len(identities))
        for name in first.values():
            self.assertLessEqual(len(name), 64)
            self.assertRegex(name, r'^[a-zA-Z0-9_-]+$')

    def test_legacy_owner_never_follows_another_server(self):
        self.assertEqual(legacy_canonical('omi.ask'), 'omi-market::omi.ask')
        self.assertNotEqual(legacy_canonical('omi.ask'), canonical_id('other','omi.ask'))

    def test_alias_collision_refused(self):
        name = canonical_id('a','b')
        with self.assertRaises(ValueError):
            _openai_api_tool_name(name, {provider_alias(name)})
