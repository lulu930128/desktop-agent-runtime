"""Exercise the real controller projection without constructing Qt/runtime."""
import ast
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Open-LLM-VTuber/src'))
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy


class LauncherPolicyTests(unittest.TestCase):
    def test_real_projection_uses_runtime_policy_rules_and_configured_scope(self):
        tree=ast.parse((ROOT/'kuro_launcher/qt_controller.py').read_text(encoding='utf-8-sig'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='work_panel_tool_policy_state')
        module=ast.Module(body=[method],type_ignores=[])
        ns={'json':json,'ToolPolicy':ToolPolicy}
        exec(compile(module,'qt_controller.py','exec'),ns)
        with tempfile.TemporaryDirectory() as folder:
            cfg={'tools':{'x':{'mode':'confrim'},'y':{'mode':'scoped_auto'},'z':{'mode':'read_only'}}}
            (Path(folder)/'tool_policy.json').write_text(json.dumps(cfg),encoding='utf-8')
            controller=SimpleNamespace(cfg=SimpleNamespace(open_llm_dir=Path(folder)))
            result=ns['work_panel_tool_policy_state'](controller)
            tools={t['name']:t for t in result['tools']}
            self.assertFalse(tools['x']['allowed'])
            self.assertFalse(tools['y']['allowed'])
            self.assertTrue(tools['z']['configured_allowed'])
            self.assertIsNone(tools['z']['effective_allowed'])
            self.assertEqual(result['view'],'configured')
            self.assertIsNone(result['effective_digest'])
            self.assertEqual(result['configured_digest'],ToolPolicy(cfg).digest)
