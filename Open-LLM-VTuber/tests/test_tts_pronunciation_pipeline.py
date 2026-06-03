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
    _build_speech_plan,
    _build_speech_source,
    _build_renderer_failure_fallback_ja,
    _finalize_rendered_japanese_for_tts,
)
from open_llm_vtuber.conversations.speech_presentation import (  # noqa: E402
    SPEECH_POLICY_CODE_JA,
    SPEECH_POLICY_DETAIL_ITEMS_JA,
    SPEECH_POLICY_OPTIONS_JA,
    SPEECH_POLICY_STOCK_NUMBERS_JA,
    SPEECH_POLICY_TABLE_JA,
    SPEECH_POLICY_URL_JA,
    SPEECH_ROUTE_RENDER_THEN_TTS,
    SPEECH_ROUTE_SILENT_DISPLAY,
    SpeechPolicyEngine,
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

    def test_latin_parentheticals_stay_display_only_for_speech(self) -> None:
        source = _build_speech_source(
            "日月光（ASE Technology）主要是做半導體的後段製程服務，",
            "",
            self.entries,
        )

        self.assertNotIn("ASE", source)
        self.assertNotIn("Technology", source)
        self.assertIn("日月光", source)
        self.assertIn("半導體", source)

    def test_latin_terms_outside_parentheses_are_not_overfiltered(self) -> None:
        source = _build_speech_source(
            "主要業務包含IC封裝、flip-chip、晶片測試。",
            "",
            self.entries,
        )

        self.assertIn("IC封裝", source)
        self.assertIn("flip-chip", source)
        self.assertIn("晶片測試", source)

    def test_split_latin_parenthetical_fragments_are_removed(self) -> None:
        first = _build_speech_source(
            "京元電子（King Yuan Electronics，",
            "",
            self.entries,
        )
        second = _build_speech_source(
            "KYEC）主要以半導體測試為核心業務。",
            "",
            self.entries,
        )

        self.assertEqual(first, "")
        self.assertEqual(second, "主要以半導體測試為核心業務。")

    def test_complete_latin_parentheticals_are_removed(self) -> None:
        source = _build_speech_source(
            "晶圓探針（wafer probe）、燒機/燒錄（burn-in）是主要服務。",
            "",
            self.entries,
        )

        self.assertNotIn("wafer", source)
        self.assertNotIn("burn", source)
        self.assertIn("晶圓探針", source)
        self.assertIn("燒機/燒錄", source)

    def test_company_name_parenthetical_normalizes_to_speakable_sentence(self) -> None:
        source = _build_speech_source(
            "京元電子（King Yuan Electronics，KYEC）主要以半導體測試為核心業務",
            "",
            self.entries,
        )

        self.assertEqual(source, "京元電子主要以半導體測試為核心業務")

    def test_speech_plan_cuts_normal_sentences_without_compression(self) -> None:
        plan = _build_speech_plan(
            "京元電子（King Yuan Electronics，KYEC）主要以半導體測試為核心業務。和日月光相比，京元較專注測試服務。",
            "",
            self.entries,
        )

        source_items = [item["text"] for item in plan if item["kind"] == "source"]
        self.assertEqual(
            source_items,
            [
                "京元電子主要以半導體測試為核心業務。",
                "和日月光相比，京元較專注測試服務。",
            ],
        )

    def test_speech_plan_replaces_code_block_with_fixed_tts_line(self) -> None:
        plan = _build_speech_plan(
            "```python\nprint('hello')\n```",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_CODE_JA,
                    "reason": "code_block",
                }
            ],
        )

    def test_speech_plan_replaces_url_only_line(self) -> None:
        plan = _build_speech_plan(
            "https://example.com/report",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_URL_JA,
                    "reason": "inline_url",
                }
            ],
        )

    def test_speech_plan_replaces_only_code_block_not_whole_answer(self) -> None:
        plan = _build_speech_plan(
            "先建立設定檔。\n```yaml\napi_url: http://127.0.0.1:9981/tts\n```\n然後重啟服務。",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {"kind": "source", "text": "先建立設定檔。", "reason": "source"},
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_CODE_JA,
                    "reason": "code_block",
                },
                {"kind": "source", "text": "然後重啟服務。", "reason": "source"},
            ],
        )

    def test_speech_plan_replaces_inline_code_without_dropping_surrounding_text(
        self,
    ) -> None:
        plan = _build_speech_plan(
            "先執行 `npm run dev`，確認成功後再重啟桌寵。",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {"kind": "source", "text": "先執行", "reason": "source"},
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_CODE_JA,
                    "reason": "inline_code",
                },
                {
                    "kind": "source",
                    "text": "確認成功後再重啟桌寵。",
                    "reason": "source",
                },
            ],
        )

    def test_speech_plan_replaces_markdown_table(self) -> None:
        plan = _build_speech_plan(
            "| 股票 | 收盤 |\n| --- | --- |\n| 2303 | 48.2 |",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_TABLE_JA,
                    "reason": "markdown_table",
                }
            ],
        )

    def test_speech_plan_skips_raw_data_and_tokens(self) -> None:
        plan = _build_speech_plan(
            'raw data: {"id":"550e8400-e29b-41d4-a716-446655440000","data":[1,2,3]}',
            "",
            self.entries,
        )

        self.assertEqual(plan, [])

    def test_speech_plan_replaces_dense_stock_numbers(self) -> None:
        plan = _build_speech_plan(
            "股價 48.2、成交量 123,456、外資 -12,300、投信 3,200、漲幅 2.1%。",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_STOCK_NUMBERS_JA,
                    "reason": "dense_stock_numbers",
                }
            ],
        )

    def test_speech_plan_keeps_option_lists_on_display(self) -> None:
        plan = _build_speech_plan(
            "你想查哪種「數據」？我可以幫你抓幾種不同層次的資料，選一項或告訴我想要的細節： "
            "1) 最新財報重點＋當日股價與市值（建議） — 包含營收、毛利率、EPS、資本支出與簡短評語。"
            "2) 歷史財務數字（近幾年營收、毛利、EPS、資本支出趨勢）。"
            "3) 製程／產能／技術節點與研發動態（例如5nm/3nm進度、產能佈局）。"
            "要我現在開始抓第幾項？",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {"kind": "source", "text": "你想查哪種「數據」？", "reason": "source"},
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_OPTIONS_JA,
                    "reason": "choice_options_displayed",
                },
                {
                    "kind": "source",
                    "text": "要我現在開始抓第幾項？",
                    "reason": "source",
                },
            ],
        )

    def test_speech_plan_replaces_inline_detail_items_not_whole_sentence(self) -> None:
        plan = _build_speech_plan(
            "建議抓最近5年（年報）並列出每年：營收、毛利率、EPS、資本支出；或要延長到10年／包含季報？",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {
                    "kind": "source",
                    "text": "建議抓最近5年（年報）。",
                    "reason": "source",
                },
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_DETAIL_ITEMS_JA,
                    "reason": "detail_items_displayed",
                },
                {
                    "kind": "source",
                    "text": "或要延長到10年／包含季報？",
                    "reason": "source",
                },
            ],
        )

    def test_presentation_envelope_keeps_display_while_routing_speech(self) -> None:
        raw = "[happy]請看 https://example.com/a/b，結論是可以。"
        display = "請看 https://example.com/a/b，結論是可以。"
        source = _build_speech_source(display, "", self.entries)

        self.assertNotIn("https://example.com", source)
        self.assertIn("結論是可以", source)

        engine = SpeechPolicyEngine()
        envelope = engine.create_envelope(response_type="chat")
        envelope.append_display(raw_text=raw, display_text=display)
        engine.set_source(envelope, source)
        envelope.attach_speech_result(
            rendered_text="これはできます。",
            spoken_text="これはできます。",
            guard_reason="ok",
            provider="test",
            pronunciation_hits=[],
            speech_repaired=False,
        )

        self.assertEqual(envelope.raw_content, raw)
        self.assertEqual(envelope.display_text, display)
        self.assertEqual(envelope.speech_route, SPEECH_ROUTE_RENDER_THEN_TTS)
        self.assertEqual(envelope.spoken_text, "これはできます。")
        self.assertEqual(envelope.speech_segments[0].source_text, source)

    def test_presentation_envelope_routes_empty_source_to_silent_display(self) -> None:
        engine = SpeechPolicyEngine()
        envelope = engine.create_envelope(response_type="chat")

        engine.set_source(envelope, "")

        self.assertEqual(envelope.speech_route, SPEECH_ROUTE_SILENT_DISPLAY)
        self.assertEqual(envelope.speech_guard_reason, "empty_source")

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

    def test_japanese_with_kanji_company_terms_is_allowed_before_tts(self) -> None:
        final, reason, _hits = _finalize_rendered_japanese_for_tts(
            "TSMCは台湾の重要な半導体企業です。",
            self.entries,
        )

        self.assertEqual(reason, "ok")
        self.assertEqual(final, "TSMCは台湾の重要な半導体企業です。")

    def test_renderer_unreadable_placeholder_uses_safe_fallback(self) -> None:
        final, reason, _hits = _finalize_rendered_japanese_for_tts(
            "テキストが読み取れません",
            self.entries,
        )

        self.assertEqual(final, "")
        self.assertEqual(reason, "renderer_unreadable")

        fallback, fallback_reason, _hits = _build_renderer_failure_fallback_ja(
            reason,
            "總部在台灣，是全球最大的封測廠商之一。",
            self.entries,
        )

        self.assertEqual(fallback, "詳しい内容は画面に表示しています。")
        self.assertEqual(fallback_reason, "renderer_unreadable_fallback")

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

    def test_bridge_parses_escaped_json_before_quality_check(self) -> None:
        bridge = _load_bridge_module()

        obj = bridge._safe_json_parse(
            r"{\"ja\":\"\u3053\u308c\u306f\u305d\u306e\u307e\u307e\u76f4\u305b\u307e\u3059\u3002\",\"emotion\":\"neutral\"}"
        )

        self.assertEqual(obj["ja"], "これはそのまま直せます。")
        self.assertEqual(
            bridge._spoken_japanese_quality_issue(
                r"{\"ja\":\"\u3053\u308c\u306f\u305d\u306e\u307e\u307e\u76f4\u305b\u307e\u3059\u3002\"}"
            ),
            "json_artifact",
        )

    def test_json_artifacts_and_single_kanji_are_rejected_before_tts(self) -> None:
        final, reason, _hits = _finalize_rendered_japanese_for_tts(
            r"{\"ja\":\"\u3053\u308c\u306f\u305d\u306e\u307e\u307e\u76f4\u305b\u307e\u3059\u3002\"}",
            self.entries,
        )

        self.assertEqual(final, "")
        self.assertEqual(reason, "json_artifact")

        final, reason, _hits = _finalize_rendered_japanese_for_tts(
            "\u4e00",
            self.entries,
        )

        self.assertEqual(final, "")
        self.assertEqual(reason, "no_kana")


if __name__ == "__main__":
    unittest.main()
