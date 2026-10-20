"""Canonical memory/policy owner guards; Web UI coverage is in qt_web_candidate."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import launcher_qt  # runtime import bootstrap
from kuro_launcher.qt_controller import QtLauncherController
from open_llm_vtuber import character_memory_manager as memory
from open_llm_vtuber.character_memory_lifecycle import review_digest




class OwnerTests(unittest.TestCase):
    def test_stale_delete_and_compact_rejected_by_canonical_memory_owner(self):
        store = {"entries": [{"id": "one", "content": "fixture", "status": "active"}]}
        with patch.object(memory, "_load_store", side_effect=lambda _: copy.deepcopy(store)), \
             patch.object(memory, "_save_store") as save:
            with self.assertRaisesRegex(ValueError, "changed since review"):
                memory.delete_character_memory("role", "one", expected_digest="old")
            with self.assertRaisesRegex(ValueError, "changed since review"):
                memory.compact_character_memories("role", expected_digests={})
            save.assert_not_called()
            self.assertTrue(memory.delete_character_memory("role", "one", expected_digest=review_digest(store["entries"][0])))
            self.assertEqual(save.call_args.args, ("role", {"entries": []}))

    def test_controller_role_fence_precedes_any_memory_write(self):
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.selected_character = Mock(return_value=SimpleNamespace(conf_uid="current"))
        with patch("kuro_launcher.qt_controller.add_character_memory") as add:
            with self.assertRaises(ValueError):
                controller.add_memory("fixture", expected_conf_uid="previous")
            add.assert_not_called()

    def test_policy_projection_uses_owner_decisions_and_never_relaxes_confirm(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tool_policy.json").write_text(json.dumps({"default_mode": "blocked", "tools": {
                "fixture::read": {"mode": "read_only"}, "fixture::write": {"mode": "confirm"}}}), encoding="utf-8")
            controller = QtLauncherController.__new__(QtLauncherController)
            controller.cfg = SimpleNamespace(open_llm_dir=root)
            with patch.dict("os.environ", {"KURO_TOOL_POLICY_PATH": ""}):
                result = controller.read_tool_policy_summary()
            self.assertFalse(result["confirmation_available"])
            self.assertEqual(result["runtime_adoption"], "UNVERIFIED")
            self.assertFalse(next(row for row in result["tools"] if row["name"] == "fixture::write")["allowed"])


if __name__ == "__main__":
    unittest.main()
