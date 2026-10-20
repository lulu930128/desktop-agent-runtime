"""Source-only guard against Windows shell loss of UI text (no runtime I/O)."""
import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCES = (
    "kuro_launcher/qt_app.py",
    "kuro_launcher/qt_chat_client.py",
    "kuro_launcher/qt_controller.py",
    "kuro_launcher/qt_web_host.py",
    "kuro_launcher/qt_web_adapter.py",
    "kuro_launcher/qt_web_protocol.py",
    "kuro_launcher/qt_web_release.py",
)


class SourceEncodingTests(unittest.TestCase):
    def test_ui_sources_are_strict_utf8_and_valid_python(self):
        for relative in UI_SOURCES:
            with self.subTest(path=relative):
                source = (ROOT / relative).read_bytes().decode("utf-8-sig", errors="strict")
                compile(source, relative, "exec")
                self.assertNotIn("\ufffd", source, "Unicode replacement character in UI source")

    def test_ui_string_literals_have_no_lossy_question_mark_runs(self):
        for relative in UI_SOURCES:
            source = (ROOT / relative).read_text(encoding="utf-8-sig")
            for node in ast.walk(ast.parse(source, filename=relative)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(path=relative, line=node.lineno):
                        self.assertIsNone(re.search(r"\?{3,}", node.value),
                                          "Possible lossy shell encoding in UI text")



if __name__ == "__main__":
    unittest.main()
