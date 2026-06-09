from __future__ import annotations

import sys
import types
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
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
    _build_speech_digest_source,
    _build_spoken_adapter_source,
    _build_renderer_failure_fallback_ja,
    _choose_renderer_failure_fallback_source,
    _choose_speech_renderer_source,
    _finalize_rendered_japanese_for_tts,
    _is_thin_acknowledgement_source,
    _select_spoken_tts_segments,
    _split_speech_units,
    _translate_only_block_reason,
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
from open_llm_vtuber.conversations.single_conversation import (  # noqa: E402
    BridgeSpeechEngine,
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
                {"surface": "OpenAI", "reading": "オープンエーアイ"},
                {"surface": "Gemini", "reading": "ジェミニ"},
                {"surface": "GPT-5-mini", "reading": "ジーピーティー ファイブ ミニ"},
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

    def test_speech_plan_does_not_label_explanatory_bullets_as_options(self) -> None:
        plan = _build_speech_plan(
            "ADR（美國掛牌版本）原則上和台股走勢高度相關，但有幾個不同點要注意： "
            "- 價格與時差：ADR 在美股時段交易，短線可能出現價格差異或時差反應。"
            "- 匯率與成本：你會承擔美元/台幣匯率風險。"
            "- 流動性與價差：部分時段 ADR 量能可能較小。"
            "要我現在幫你抓最新 ADR 報價、成交量與和台股的價差比較嗎？",
            "",
            self.entries,
        )

        self.assertEqual(
            plan,
            [
                {
                    "kind": "source",
                    "text": "ADR（美國掛牌版本）原則上和台股走勢高度相關，但有幾個不同點要注意：",
                    "reason": "source",
                },
                {
                    "kind": "fixed_ja",
                    "text": SPEECH_POLICY_DETAIL_ITEMS_JA,
                    "reason": "detail_items_displayed",
                },
                {
                    "kind": "source",
                    "text": "要我現在幫你抓最新 ADR 報價、成交量與和台股的價差比較嗎？",
                    "reason": "source",
                },
            ],
        )

    def test_spoken_adapter_rewrites_technical_table_names(self) -> None:
        source = _build_spoken_adapter_source(
            "確認，OMI 目前的聯電資料不完整，缺少最新日收盤價、成交量、法人籌碼與財報等關鍵資料欄位。"
            "缺少 market_daily_price、institutional_trade_daily、margin_trading、shareholding_weekly、"
            "monthly_revenue、quarterly_financial、broker_branch 等資料，會導致動能與籌碼面判讀不可靠。"
            "簡短交易看法：短線風險偏高，保守者可先空手觀察。",
            "",
            self.entries,
        )

        self.assertIn("最新價格與成交量資料", source)
        self.assertIn("法人買賣超資料", source)
        self.assertIn("融資融券資料", source)
        self.assertIn("季報財務資料", source)
        self.assertIn("會導致動能與籌碼面判讀不可靠", source)
        self.assertIn("短線風險偏高", source)
        self.assertNotIn("market_daily_price", source)
        self.assertNotIn("institutional_trade_daily", source)

    def test_spoken_adapter_skips_explicit_choice_lists(self) -> None:
        source = _build_spoken_adapter_source(
            "你想查哪種「數據」？選一項或告訴我想要的細節："
            "1) 最新財報重點。"
            "2) 歷史財務數字。"
            "要我現在開始抓第幾項？",
            "",
            self.entries,
        )

        self.assertEqual(source, "")

    def test_spoken_adapter_keeps_known_foreign_terms_and_removes_visual_artifacts(self) -> None:
        source = _build_spoken_adapter_source(
            "OpenAI 和 Gemini 的比較可以看畫面：https://example.com。"
            "程式碼 `client.responses.create()` 不用念，但結論是兩者要看任務選。",
            "",
            self.entries,
        )

        self.assertIn("OpenAI", source)
        self.assertIn("Gemini", source)
        self.assertIn("結論是兩者要看任務選", source)
        self.assertNotIn("https://example.com", source)
        self.assertNotIn("client.responses.create", source)

    def test_long_benchmark_answer_keeps_substantive_voice_not_heading_only(self) -> None:
        text = (
            "有的，社群與研究團隊都有專門整理分數的 leaderboard，但要注意多數 benchmark "
            "在 2025–2026 年已接近飽和且可能有測試集汙染，所以「絕對數字」要搭配出處與更新日期一起看。"
            "簡短重點："
            "- 哪裡能看到「具體數字」：常見來源有 LiveBench / Artificial Analysis、"
            "Learn-Prompting 的比較整理、LXT 的總覽報告與多個社群 tracker。"
            "- 數據趨勢：GPT-5 系列通常在程式碼、複雜推理上略勝一籌；"
            "Gemini 3 在跨模態、延遲/成本優勢與某些語境整合測試上接近或更好。"
            "- 風險提醒：不同 tracker 的測試集、採樣方式、prompt 設定與去重策略不同，"
            "會導致數值有明顯落差。"
            "要不要我現在去抓最新的 leaderboard 表格並把每個模型的最新分數列成比較表？"
        )

        plan = _build_speech_plan(text, "", self.entries)
        spoken_texts = [item["text"] for item in plan]

        self.assertLessEqual(len(plan), 3)
        self.assertIn("有的，社群與研究團隊都有專門整理分數", spoken_texts[0])
        self.assertIn(SPEECH_POLICY_DETAIL_ITEMS_JA, spoken_texts)
        self.assertIn("要不要我現在去抓最新的 leaderboard 表格", spoken_texts[-1])
        self.assertNotIn("簡短重點：", spoken_texts)

    def test_long_benchmark_answer_uses_digest_source_for_bridge_renderer(self) -> None:
        text = (
            "有的，社群與研究團隊都有專門整理分數的 leaderboard，但要注意多數 benchmark "
            "在 2025–2026 年已接近飽和且可能有測試集汙染，所以「絕對數字」要搭配出處與更新日期一起看。"
            "簡短重點："
            "- 哪裡能看到「具體數字」：常見來源有 LiveBench / Artificial Analysis、"
            "Learn-Prompting 的比較整理、LXT 的總覽報告與多個社群 tracker。"
            "- 數據趨勢：GPT-5 系列通常在程式碼、複雜推理上略勝一籌；"
            "Gemini 3 在跨模態、延遲/成本優勢與某些語境整合測試上接近或更好。"
            "- 風險提醒：不同 tracker 的測試集、採樣方式、prompt 設定與去重策略不同，"
            "會導致數值有明顯落差。"
            "要不要我現在去抓最新的 leaderboard 表格並把每個模型的最新分數列成比較表？"
        )

        adapter_source = _build_spoken_adapter_source(text, "", self.entries)
        digest_source = _build_speech_digest_source(text, "", self.entries)
        renderer_source, source_kind = _choose_speech_renderer_source(
            adapter_source=adapter_source,
            digest_source=digest_source,
        )

        self.assertGreater(len(adapter_source), 240)
        self.assertLessEqual(len(digest_source), 120)
        self.assertEqual(source_kind, "digest")
        self.assertEqual(renderer_source, digest_source)
        self.assertIn("絕對數字", digest_source)
        self.assertNotIn("簡短重點", digest_source)

    def test_medium_image_description_uses_digest_for_bridge_renderer(self) -> None:
        text = (
            "我有看到這張靜態畫面。畫面中有兩個人並排坐在鏡頭前："
            "左邊穿淺色上衣、黑色短髮，視線偏向左側；"
            "右邊穿白色上衣，坐在一張粉色／淺色的電競椅前，視線偏向右下方。"
            "背景可見床鋪、枕頭和蓋毯，牆上有一張動畫風格的海報，"
            "整體像是臥室或工作室的室內場景，燈光為室內白光。"
        )

        adapter_source = _build_spoken_adapter_source(text, "", self.entries)
        digest_source = _build_speech_digest_source(text, "", self.entries)
        renderer_source, source_kind = _choose_speech_renderer_source(
            adapter_source=adapter_source,
            digest_source=digest_source,
        )

        self.assertGreater(len(adapter_source), 120)
        self.assertLessEqual(len(digest_source), 120)
        self.assertEqual(source_kind, "digest")
        self.assertEqual(renderer_source, digest_source)
        self.assertIn("畫面中有兩個人", digest_source)
        self.assertIn("背景可見床鋪", digest_source)

    def test_long_spoken_tts_without_punctuation_is_hard_split(self) -> None:
        long_text = (
            "\u3053\u308c\u306f\u3068\u3066\u3082\u9577\u3044"
            "\u5831\u544a\u306e\u8aac\u660e\u3067\u3059"
            * 20
        )

        segments = _split_speech_units(long_text, max_chars=24)

        self.assertGreater(len(segments), 1)
        self.assertTrue(all(len(segment) <= 24 for segment in segments))

    def test_spoken_tts_budget_adds_display_hint_when_truncated(self) -> None:
        long_text = (
            "\u3053\u308c\u306f\u9577\u3044\u8aac\u660e\u3067\u3059\u3002"
            "\u6b21\u306e\u91cd\u8981\u70b9\u3092\u8a71\u3057\u307e\u3059\u3002"
            "\u3055\u3089\u306b\u8a73\u7d30\u3092\u88dc\u8db3\u3057\u307e\u3059\u3002"
            "\u6700\u5f8c\u306b\u6b21\u306e\u884c\u52d5\u3092\u8a71\u3057\u307e\u3059\u3002"
        )

        segments, truncated = _select_spoken_tts_segments(
            long_text,
            max_content_segments=2,
            max_chars=40,
        )

        self.assertTrue(truncated)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[-1], SPEECH_POLICY_DETAIL_ITEMS_JA)

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

    def test_rendered_ai_terms_are_rewritten_before_tts(self) -> None:
        final, reason, hits = _finalize_rendered_japanese_for_tts(
            "OpenAIとGeminiなら、GPT-5-miniの使い方を先に決めます。",
            self.entries,
        )

        self.assertEqual(reason, "ok")
        self.assertIn("オープンエーアイ", final)
        self.assertIn("ジェミニ", final)
        self.assertIn("ジーピーティー ファイブ ミニ", final)
        self.assertIn("OpenAI", hits)
        self.assertIn("Gemini", hits)

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

        self.assertEqual(
            fallback,
            "内容は確認しました。詳しい内容は画面に表示しています。",
        )
        self.assertEqual(fallback_reason, "renderer_unreadable_fallback")

    def test_renderer_failure_fallback_source_prefers_digest(self) -> None:
        source = _choose_renderer_failure_fallback_source(
            renderer_source="畫面中有兩個人並排坐在鏡頭前。背景可見床鋪與海報。",
            digest_source="畫面中有兩個人並排坐在鏡頭前。背景可見床鋪與海報。",
            adapter_source="我有看到這張靜態畫面。畫面中有兩個人並排坐在鏡頭前。背景可見床鋪與海報。",
            speech_source="我有看到這張靜態畫面。",
            speech_plan=[
                {
                    "kind": "source",
                    "reason": "source",
                    "text": "我有看到這張靜態畫面。",
                }
            ],
        )

        self.assertIn("畫面中有兩個人", source)
        self.assertNotEqual(source, "我有看到這張靜態畫面。")

    def test_thin_acknowledgement_source_is_not_enough_after_digest_failure(self) -> None:
        self.assertTrue(_is_thin_acknowledgement_source("我有看到這張靜態畫面。"))
        self.assertFalse(
            _is_thin_acknowledgement_source(
                "畫面中有兩個人並排坐在鏡頭前，背景可見床鋪與海報。"
            )
        )

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

    def test_bridge_unwraps_nested_json_ja_response(self) -> None:
        bridge = _load_bridge_module()

        obj = bridge._coerce_spoken_render_obj(
            {
                "ja": r"{\"ja\":\"\u753b\u9762\u306b\u306f\u4e8c\u4eba\u304c\u5ea7\u3063\u3066\u3044\u307e\u3059\u3002\",\"emotion\":\"neutral\"}",
                "emotion": "surprise",
            }
        )

        self.assertEqual(obj["ja"], "画面には二人が座っています。")
        self.assertEqual(obj["emotion"], "neutral")
        self.assertEqual(bridge._spoken_japanese_quality_issue(obj["ja"]), "")

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

    def test_translate_only_long_fallback_is_blocked_before_tts(self) -> None:
        reason = _translate_only_block_reason(
            "openai:gpt-5-mini:translate_only",
            "這是一段很長的比較。" * 20,
            "これは長い翻訳です。" * 20,
        )

        self.assertEqual(reason, "translate_only_source_too_long")

    def test_translate_only_short_fallback_can_still_speak(self) -> None:
        reason = _translate_only_block_reason(
            "openai:gpt-5-mini:translate_only",
            "要我現在幫你刷新資料嗎？",
            "今、データを更新しましょうか？",
        )

        self.assertEqual(reason, "")

    def test_bridge_translate_only_fallback_length_gate(self) -> None:
        bridge = _load_bridge_module()

        self.assertTrue(
            bridge._is_short_translate_only_fallback(
                "要我現在刷新資料嗎？",
                "今、データを更新しましょうか？",
            )
        )
        self.assertFalse(
            bridge._is_short_translate_only_fallback(
                "這是一段很長的比較。" * 20,
                "これは長い翻訳です。" * 20,
            )
        )

    def test_bridge_accepts_short_benchmark_translate_only_fallback(self) -> None:
        bridge = _load_bridge_module()
        source = (
            "有的，社群與研究團隊都有專門整理分數的 leaderboard，但要注意多數 benchmark "
            "已接近飽和且可能有測試集汙染，所以絕對數字要搭配出處與更新日期一起看。"
        )
        spoken = (
            "あります。コミュニティや研究チームがスコアを整理したリーダーボードを用意していることもありますが、"
            "多くのベンチマークは既に飽和に近く、出典と更新日を合わせて確認してください。"
        )

        self.assertEqual(bridge._spoken_japanese_quality_issue(spoken), "")
        self.assertTrue(bridge._is_short_translate_only_fallback(source, spoken))

    def test_bridge_quality_allows_japanese_with_taiwan_company_names(self) -> None:
        bridge = _load_bridge_module()
        spoken = (
            "聯華電子は台湾の大手ファウンドリ半導体企業で、1980年に設立され、"
            "本社は台湾にあります。聯電の最新の財務報告をお調べしましょうか？"
        )

        self.assertEqual(bridge._spoken_japanese_quality_issue(spoken), "")

    def test_bridge_speech_engine_does_not_translate_only_fallback_for_long_source(self) -> None:
        engine = BridgeSpeechEngine(
            endpoint="http://bridge/render_spoken",
            translate_endpoint="http://bridge/translate",
        )
        engine.translate_fallback_max_source_chars = 20
        calls: list[str] = []

        def fake_post_json(url: str, _payload: dict[str, object]) -> dict[str, object]:
            calls.append(url)
            return {
                "code": 200,
                "data": "",
                "emotion": "neutral",
                "provider": "blocked-low-quality",
            }

        engine._post_json = fake_post_json  # type: ignore[method-assign]

        out = engine.translate("這是一段太長、不該只靠翻譯補救的助理回答。")

        self.assertEqual(out, "")
        self.assertEqual(calls, ["http://bridge/render_spoken"])

    def test_bridge_speech_engine_allows_translate_only_fallback_for_short_source(self) -> None:
        engine = BridgeSpeechEngine(
            endpoint="http://bridge/render_spoken",
            translate_endpoint="http://bridge/translate",
        )
        engine.translate_fallback_max_source_chars = 20
        calls: list[str] = []

        def fake_post_json(url: str, _payload: dict[str, object]) -> dict[str, object]:
            calls.append(url)
            if url.endswith("/translate"):
                return {
                    "code": 200,
                    "data": "はい、できます。",
                    "provider": "bridge:translate",
                }
            return {
                "code": 200,
                "data": "",
                "emotion": "neutral",
                "provider": "blocked-low-quality",
            }

        engine._post_json = fake_post_json  # type: ignore[method-assign]

        out = engine.translate("可以嗎？")

        self.assertEqual(out, "はい、できます。")
        self.assertEqual(
            calls,
            ["http://bridge/render_spoken", "http://bridge/translate"],
        )


if __name__ == "__main__":
    unittest.main()
