from __future__ import annotations

import sys
import types
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(SRC))

try:
    import loguru  # noqa: F401
except ModuleNotFoundError:
    class _TestLogger:
        def __getattr__(self, _name: str):
            return lambda *args, **kwargs: None

    sys.modules["loguru"] = types.SimpleNamespace(logger=_TestLogger())

from open_llm_vtuber.conversations.conversation_utils import (  # noqa: E402
    _build_speech_source,
    _finalize_rendered_japanese_for_tts,
)
from open_llm_vtuber.speech_pronunciation import (  # noqa: E402
    apply_pronunciation,
    contains_pronunciation_surface,
    normalize_pronunciation_entries,
)


def _load_bridge_module():
    spec = importlib.util.spec_from_file_location(
        "deeplx_bridge_test",
        REPO_ROOT / "bridges" / "deeplx_bridge.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TTSPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = normalize_pronunciation_entries(
            [
                {"surface": "Thomas", "reading": "トーマス", "aliases": ["thomas"]},
                {"surface": "LLM", "reading": "エルエルエム"},
            ]
        )

    def test_pronunciation_dictionary_replaces_known_names(self) -> None:
        text, hits = apply_pronunciation("Thomas と LLM", self.entries)

        self.assertEqual(text, "トーマス と エルエルエム")
        self.assertIn("Thomas", hits)
        self.assertIn("LLM", hits)

    def test_known_name_line_can_enter_speech_source(self) -> None:
        source = _build_speech_source("Thomas。", "", self.entries)

        self.assertEqual(source, "Thomas。")
        self.assertTrue(contains_pronunciation_surface(source, self.entries))

    def test_rendered_english_name_is_rewritten_before_tts(self) -> None:
        final, reason, hits = _finalize_rendered_japanese_for_tts(
            "Thomas、これはそのまま直せます。",
            self.entries,
        )

        self.assertEqual(reason, "ok")
        self.assertEqual(final, "トーマス、これはそのまま直せます。")
        self.assertIn("Thomas", hits)

    def test_raw_chinese_is_rejected_before_tts(self) -> None:
        final, reason, _hits = _finalize_rendered_japanese_for_tts(
            "這段可以直接改。",
            self.entries,
        )

        self.assertEqual(final, "")
        self.assertIn(reason, {"no_kana", "looks_chinese"})

    def test_sigh_tokens_are_removed_before_tts(self) -> None:
        final, reason, _hits = _finalize_rendered_japanese_for_tts(
            "はぁ、これはそのまま直せます。",
            self.entries,
        )

        self.assertEqual(reason, "ok")
        self.assertEqual(final, "これはそのまま直せます。")

    def test_bridge_quality_check_rejects_fragmented_japanese(self) -> None:
        bridge = _load_bridge_module()

        self.assertEqual(
            bridge._spoken_japanese_quality_issue("トーマス 修正 可能 設定"),
            "not_sentence_like",
        )
        self.assertEqual(
            bridge._spoken_japanese_quality_issue("これはそのまま直せます。"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
