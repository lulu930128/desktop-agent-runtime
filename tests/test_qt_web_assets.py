"""Round-trip the actual Vite output; tampering is tested only in disposable copies."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from kuro_launcher.qt_web_host import AssetBundle, ENTRY

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "devtools/original-git-web-host-20261010/.runtime/candidate-dist"


class AssetTests(unittest.TestCase):
    def test_actual_build_roundtrip_has_final_html_and_every_asset(self):
        bundle = AssetBundle(DIST)
        self.assertTrue(bundle.allowed(ENTRY))
        actual = {"/" + p.relative_to(DIST).as_posix() for p in DIST.rglob("*") if p.is_file() and p.name != "candidate-manifest.json"}
        self.assertEqual(set(bundle.assets), actual)
        self.assertIn("/work-panel.html", bundle.assets)
        self.assertTrue(any(p.endswith(".js") for p in bundle.assets))
        self.assertFalse(any(p.endswith(".map") for p in bundle.assets))
        for data in bundle.assets.values():
            self.assertNotIn(b"SYNTHETIC preview", data)
            self.assertNotIn(b"fixture.context", data)

    def test_every_asset_tamper_is_rejected(self):
        for name in AssetBundle(DIST).assets:
            with self.subTest(asset=name), tempfile.TemporaryDirectory(prefix=".validation-web-assets-", dir=ROOT) as folder:
                target = Path(folder) / "dist"
                shutil.copytree(DIST, target)
                path = target / name.lstrip("/")
                path.write_bytes(path.read_bytes() + b"tampered")
                with self.assertRaisesRegex(ValueError, "hash mismatch"): AssetBundle(target)

    def test_renderer_cannot_request_files_network_or_traversal(self):
        bundle = AssetBundle(DIST)
        for url in ("https://example.com", "file:///C:/private.txt", "kuro-work://evil/work-panel.html",
                    "kuro-work://app/../private", "kuro-work://app/%2e%2e/private", ENTRY+"?x=1", ENTRY+"#x", "qrc:///private"):
            self.assertFalse(bundle.allowed(url), url)

    def test_manifest_escape_rejected(self):
        with tempfile.TemporaryDirectory(prefix=".validation-web-assets-", dir=ROOT) as folder:
            root = Path(folder); (root / "dist").mkdir(); (root / "escape.js").write_text("x")
            (root / "dist/candidate-manifest.json").write_text(json.dumps({"contract": "kuro.qt.assets.v1", "files": {"../escape.js": hashlib.sha256(b"x").hexdigest()}}))
            with self.assertRaisesRegex(ValueError, "allowlist"): AssetBundle(root / "dist")


if __name__ == "__main__": unittest.main()
