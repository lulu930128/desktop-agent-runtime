"""Source/config/policy/history fixtures; no external server, provider or DB."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import yaml

RUNTIME = Path(__file__).resolve().parents[1]
ROOT = RUNTIME.parent
sys.path.insert(0, str(ROOT))
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog
from open_llm_vtuber.mcpp.tool_identity import legacy_canonical
from kuro_launcher.tool_policy_settings import CATALOG, GROUPS, ToolPolicySettings
from kuro_launcher.runtime_conf import build_runtime_conf

TOOLS = {'workspace_info', 'list_dir', 'find_files', 'search_text', 'read_file', 'read_files', 'project_context'}
OLD = {'list_allowed_roots', 'list_directory', 'search_files', 'read_text_file'}


class WorkspaceCutoverTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((RUNTIME / 'mcp_servers.json').read_text(encoding='utf-8'))
        self.policy = ToolPolicy(json.loads((RUNTIME / 'tool_policy.json').read_text(encoding='utf-8')))

    def test_registry_exact_read_scope_and_roles(self):
        servers = self.config['mcp_servers']
        self.assertEqual(servers['kuro-filesystem']['allowed_tools'], ['search_past_conversations'])
        workspace = servers['project-workspace']
        self.assertEqual(workspace['command'], 'node')
        self.assertEqual(workspace['args'], [r'C:\GPT_MCPtool\project_reading\dist\src\index.js'])
        self.assertNotIn("allowed_tools", workspace)
        self.assertNotIn("WORKSPACE_MCP_MAX_READ_LINES", workspace["env"])
        self.assertEqual(workspace['env']['WORKSPACE_MCP_ROOTS'], r'projects=C:\project;mcp_tools=C:\GPT_MCPtool;work=C:\work')
        self.assertTrue(Path(workspace['env']['WORKSPACE_MCP_WRITE_POLICY']).is_file())
        role = yaml.safe_load((RUNTIME / 'characters/kuro.yaml').read_text(encoding='utf-8'))
        agent = role['character_config']['agent_config']['agent_settings']['basic_memory_agent']
        self.assertTrue(set(servers).issubset(agent['mcp_enabled_servers']))
        self.assertIn('kuro-filesystem::search_past_conversations', CATALOG)
        self.assertEqual(set(CATALOG), set(self.policy.tools))
        self.assertTrue(set(servers).issubset(GROUPS))
        snapshot = ToolPolicySettings(RUNTIME / 'tool_policy.json').read()
        for row in snapshot['tools']:
            self.assertTrue(any('\u4e00' <= c <= '\u9fff' for c in row['label']))
            self.assertTrue(any('\u4e00' <= c <= '\u9fff' for c in row['description']))

    def test_formal_launcher_derives_servers_from_character_without_live_write(self):
        character = RUNTIME / 'characters/kuro.yaml'
        role = yaml.safe_load(character.read_text(encoding='utf-8'))
        # Exercise the formal builder with an empty base and no secret injection.
        with patch('kuro_launcher.runtime_conf.find_base_conf', return_value=Path('fixture-base.yaml')), \
             patch('kuro_launcher.runtime_conf.read_yaml_file', side_effect=[{}, role]), \
             patch.dict('os.environ', {}, clear=True):
            merged, _ = build_runtime_conf(RUNTIME, character, None, '127.0.0.1', 23456,
                'http://127.0.0.1/fixture', '127.0.0.1', 18890,
                'FIXTURE_PROVIDER', 'openai_llm', 'FIXTURE_MODEL', 'fixture',
                'FIXTURE_TEMP', 'FIXTURE_INJECT', 'FIXTURE_KEY', 'FIXTURE_FALLBACK')
        actual = merged['character_config']['agent_config']['agent_settings']['basic_memory_agent']
        self.assertEqual(actual['mcp_enabled_servers'], role['character_config']['agent_config']['agent_settings']['basic_memory_agent']['mcp_enabled_servers'])
        settings = yaml.safe_load((ROOT / 'kuro_launcher.settings.yaml').read_text(encoding='utf-8'))
        self.assertTrue(settings['paths']['runtime_conf_path'].endswith('conf.launcher_runtime.yaml'))

    def test_retired_aliases_stay_original_owner_and_fail_closed(self):
        for name in OLD:
            identity = 'kuro-filesystem::' + name
            self.assertEqual(legacy_canonical(name), identity)
            for candidate in (name, identity):
                self.assertFalse(self.policy.check(candidate, {}).allowed)
        self.assertEqual(legacy_canonical('search_past_conversations'), 'kuro-filesystem::search_past_conversations')
        for name in ('write_file', 'apply_patch', 'run_command', 'git_commit'):
            from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
            from open_llm_vtuber.mcpp.tool_manager import ToolManager
            executor = ToolExecutor(Mock(), ToolManager([], [], {}))
            self.assertEqual(executor.check_call('project-workspace::' + name, {}).reason_code, 'tool_unavailable')

    def test_explicit_legacy_single_and_batch_path_policy(self):
        self.policy = ToolPolicy(json.loads((RUNTIME / 'tests/fixtures/legacy_tool_grants.json').read_text(encoding='utf-8')))
        for args, name in (({'path': '.env'}, 'read_file'), ({'project': '.ssh'}, 'project_context'),
                           ({'files': [{'path': 'README.md'}, {'path': '.git/config'}]}, 'read_files'),
                           ({'files': [{'path': '.env'}]}, 'read_files'),
                           ({'files': 'invalid'}, 'read_files'), ({'files': [None]}, 'read_files')):
            self.assertFalse(self.policy.check('project-workspace::' + name, args).allowed)
        self.assertTrue(self.policy.check('project-workspace::read_files', {'root': 'projects', 'files': [{'path': 'demo/README.md'}]}).allowed)

    def test_catalog_routes_only_new_owner_for_files(self):
        catalog = ToolCatalog.load_default()
        local = catalog.categories['local_files']
        self.assertEqual({row['name'] for row in local['tools']}, {'project-workspace::' + n for n in TOOLS})
        for query in ('讀取專案 README.md 檔案', '搜尋檔案與資料夾結構'):
            route = catalog.route(query, [row["name"] for row in local["tools"]])
            self.assertTrue(any(n.startswith('project-workspace::') for n in route.tool_names))
            self.assertFalse(any(n.startswith('kuro-filesystem::') for n in route.tool_names))
        prompt = (ROOT / 'projects/desktop-agent-runtime/prompts/tool_prompt.txt').read_text(encoding='utf-8')
        for name in OLD:
            self.assertNotIn('`' + name + '`', prompt)

    def test_history_only_registration_and_exact_original_scope(self):
        spec = importlib.util.spec_from_file_location('history_cutover_fixture', RUNTIME / 'local_mcp/filesystem_tools_server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual([tool.name for tool in asyncio.run(module.mcp.list_tools())], ['search_past_conversations'])
        search = Mock(return_value=[{'history_uid': 'past', 'message_index': 2, 'content': 'fixture result'}])
        with patch.object(module, '_search_past_conversations', search):
            result = module.search_past_conversations('query', 'character-A', 'current-history', 99)
        search.assert_called_once_with('character-A', 'query', exclude_history_uid='current-history',
                                      include_current_history=False, max_snippets=12, token_budget=1200)
        self.assertIn('past#2', result)
        self.assertIn('conf_uid: character-A', result)


if __name__ == '__main__':
    unittest.main()
