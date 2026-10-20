"""Prior G7 deletion invariant retained after W10 Widgets retirement."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class SourceCutoverTests(unittest.TestCase):
    def test_g7_retired_paths_remain_absent(self):
        manifest = json.loads((ROOT / "docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json").read_text(encoding="utf-8-sig"))
        paths = [item["path"] for item in manifest["files"]]
        self.assertEqual(len(paths), 35)
        for relative in paths:
            self.assertFalse((ROOT / relative).exists(), relative)
