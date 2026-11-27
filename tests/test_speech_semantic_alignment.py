"""Synthetic v2 source fixtures. No real LLM/TTS or semantic-equivalence claim."""
import asyncio
import copy
import base64
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "Open-LLM-VTuber/src"), str(ROOT / "Open-LLM-VTuber")]
import test_multilingual_speech as v1
from open_llm_vtuber.conversations.speech_presentation import (
    SpeechLaneParser, SpeechPolicyEngine, route_speech_lanes,
    SPEECH_LANE_V2_CONTRACT, SPEECH_LANE_V2_MARKER,
)


def anchor(key, source, kind="status", importance="required"):
    return dict(id=key, source=source, kind=kind, importance=importance)


def segment(text, *keys):
    return dict(source_ids=list(keys), text=text)


def lane(anchors=None, speech=None, **kwargs):
    value = dict(contract=SPEECH_LANE_V2_CONTRACT, locale="ja-JP", policy="summary",
                 anchors=anchors or [], speech=speech or [], emotion="joy")
    value.update(kwargs)
    return value


def footer(value):
    return SPEECH_LANE_V2_MARKER + "\n" + json.dumps(value, ensure_ascii=False)


DISPLAY = "工具請求遭阻擋，操作失敗，尚未驗證。\nA：公開網路查詢\nB：先看診斷清單\n價格100.5，停損95。"
VALID = lane([
    anchor("s", "工具請求遭阻擋，操作失敗，尚未驗證"),
    anchor("a", "公開網路查詢", "option"), anchor("b", "先看診斷清單", "option"),
    anchor("p", "價格100.5，停損95", "fact"),
], [segment("ツール要求はブロックされ、操作は失敗しました。未検証です。", "s"),
    segment("公開ウェブを検索するか、先に診断チェックリストを確認できます。", "a", "b"),
    segment("価格は100.5、損切りは95です。", "p")])

TECHNICAL_DISPLAY = ('技術說明：Node.js 接收 API 回應，JSON 與程式細節留在畫面。\n'
                     '```js\nconst result = {"ok": true};\n```\n'
                     'https://example.test/status\nC:\\fixture\\server.js\n/var/fixture/server.log\n'
                     '{"items": []}\n|key|value|\n|ok|true|\n'
                     'Traceback (most recent call last):\nValueError: synthetic\n')
TECHNICAL_SPOKEN = 'Node.js でAPIの応答を受け取ります。JSONやコード、参照リンクとログの詳細は画面にあります。'
OPTION_DISPLAY = 'A：公開網路查詢\nB：先看診斷清單'
OPTION_SPOKEN = 'ウェブ検索か、診断チェックリストの確認ができます。'


def option_lane(text=OPTION_SPOKEN):
    return lane([anchor('a', '公開網路查詢', 'option'), anchor('b', '先看診斷清單', 'option')],
                [segment(text, 'a', 'b')])


class SemanticParserTests(unittest.TestCase):
    def parse(self, display, value, settings=None):
        parser = SpeechLaneParser()
        visible = parser.feed(display + footer(value)) + parser.finish_display()
        self.assertEqual(visible, display)
        return parser.result(settings or v1.CHAT_SPEECH_DEFAULTS)

    def test_natural_technical_names_are_not_raw_filenames(self):
        for text in (TECHNICAL_SPOKEN, 'Next.jsは画面を表示し、設定はJSON形式で保存します。',
                     'TypeScriptとPythonでAPIを呼び出します。URLやパスの詳細は画面にあります。'):
            with self.subTest(text=text):
                self.assertEqual(self.parse(TECHNICAL_DISPLAY, lane(speech=[segment(text)]))['state'], 'ready')

    def test_raw_payloads_still_fail_as_a_whole(self):
        for text in ('server.js', '設定は ./server.js にあります。', r'場所はC:\fixture\server.jsです。',
                     '場所はsrc/server.jsです。', r'場所はsrc\server.jsです。',
                     'ログは/var/fixture/server.logです。', 'https://example.test/status',
                     '```js\nconst result = 1;\n```', '設定は`server.js`です。',
                     '{"ok":true}', '[1, 2]', '|key|value|', 'Traceback (most recent call last):',
                     'ValueError: synthetic', 'INFO: synthetic', 'const result = 1;', 'x = 1'):
            with self.subTest(text=text):
                self.assertEqual(self.parse(TECHNICAL_DISPLAY, lane(speech=[segment('説明します。'), segment(text)]))['state'], 'technical_payload')

    def test_natural_japanese_option_forms_and_shared_affirmative(self):
        for text in (OPTION_SPOKEN,
                     '公開ウェブを検索できるし、診断チェックリストも確認できるよ。',
                     '公開ウェブで調べるか、診断項目をチェックできます。',
                     '公開ウェブを検索する方法と、診断チェックリストを確認する方法から選べます。'):
            with self.subTest(text=text):
                self.assertEqual(self.parse(OPTION_DISPLAY, option_lane(text))['state'], 'ready')

    def test_option_forms_do_not_allow_omission_or_reversed_executability(self):
        for text in ('選択肢は画面にあります。',
                     'ウェブ検索か、診断チェックリストの確認ができません。',
                     'ウェブ検索はできませんが、診断チェックリストの確認ができます。',
                     '公開ウェブを検索できるとは言えません。診断チェックリストは確認できます。',
                     '公開ウェブを検索できるのではありません。診断チェックリストは確認できます。',
                     '公開ウェブでは調べられませんが、診断項目をチェックできます。',
                     '公開ウェブでは調べられないよ。診断項目は確認できるよ。',
                     '公開ウェブを検索できます。診断項目をチェックすることはできません。',
                     '公開ウェブを検索できます。診断項目はチェックできないよ。'):
            with self.subTest(text=text):
                self.assertEqual(self.parse(OPTION_DISPLAY, option_lane(text))['state'], 'option_unverified')

    def test_rejection_diagnostics_count_received_not_only_validated_fields(self):
        value = option_lane('公開ウェブを検索できます。診断チェックリストは確認できません。')
        result = self.parse(OPTION_DISPLAY, value)
        self.assertEqual(result['state'], 'option_unverified')
        self.assertEqual(result['diagnostics'], dict(received_anchors=2, received_semantic_segments=1,
            validated_anchors=2, validated_semantic_segments=1, stage='required_anchor',
            anchor_index=1, rule_id='option_unverified'))
        result = self.parse(TECHNICAL_DISPLAY, lane(speech=[segment('説明します。'), segment('x = 1')]))
        self.assertEqual(result['diagnostics']['segment_index'], 1)
        self.assertEqual(result['diagnostics']['received_semantic_segments'], 2)
        self.assertEqual(result['diagnostics']['validated_semantic_segments'], 1)
        self.assertNotIn('x = 1', json.dumps(result))

    def test_valid_sources_and_all_boundaries(self):
        raw = DISPLAY + footer(VALID)
        for split in range(len(raw) + 1):
            parser = SpeechLaneParser()
            visible = parser.feed(raw[:split]) + parser.feed(raw[split:]) + parser.finish_display()
            self.assertEqual(visible, DISPLAY)
            self.assertEqual(parser.result(v1.CHAT_SPEECH_DEFAULTS)["state"], "ready")

    def test_all_policies_and_anchor_free_multilingual_chat(self):
        for policy in ("brief", "summary", "detailed"):
            for display in ("你好！", "Hello!", "こんにちは！", "這部分可以直接改，沒有其他問題", "這部分是普通技術說明，記憶體不足的定義如下"):
                with self.subTest(policy=policy, display=display):
                    value = lane(speech=[segment("はい、そのまま変更できます。ほかに問題はありません。")], policy=policy)
                    self.assertEqual(self.parse(display, value, dict(v1.CHAT_SPEECH_DEFAULTS, policy=policy))["state"], "ready")

    def test_explicit_status_cannot_be_unanchored_or_display_only(self):
        for display in ("資料部分缺失", "操作失敗", "尚未驗證", "資料過期", "不能下單"):
            for anchors in ([], [anchor("s", display, importance="display_only")]):
                with self.subTest(display=display, anchors=anchors):
                    self.assertIn(self.parse(display, lane(anchors, [segment("確認しました。")]))["state"], {"semantic_unverified", "anchor_status_mismatch"})

    def test_explicit_status_cannot_be_omitted_with_complete_ids(self):
        for display, text in [("資料部分缺失", "データはあります。"), ("操作失敗", "操作しました。"),
                              ("尚未驗證", "確認しました。"), ("工具請求遭阻擋", "データを取得できませんでした。")]:
            self.assertEqual(self.parse(display, lane([anchor("s", display)], [segment(text, "s")]))["state"],
                             "anchor_status_mismatch" if display == "尚未驗證" else "semantic_unverified")

    def test_partial_missing_and_negative_are_preserved(self):
        for display, text in [("資料部分缺失", "データの一部が欠落しています。"), ("操作失敗", "操作は失敗しました。"),
                              ("尚未驗證", "まだ未検証です。"), ("資料過期", "データは古いままです。"),
                              ("不能下單", "注文できません。")]:
            self.assertEqual(self.parse(display, lane([anchor("s", display)], [segment(text, "s")]))["state"], "ready")

    def test_complete_ids_do_not_prove_second_option_translation(self):
        value = copy.deepcopy(VALID)
        value["speech"][1]["text"] = "公開ウェブを検索できます。"
        self.assertEqual(value["speech"][1]["source_ids"], ["a", "b"])
        self.assertEqual(self.parse(DISPLAY, value)["state"], "semantic_unverified")

    def test_option_topic_is_not_action_and_cannot_be_negated(self):
        for text in ("公開ウェブを検索できます。診断チェックリストは画面にあります。",
                     "公開ウェブを検索できます。診断チェックリストは確認できません。"):
            value = copy.deepcopy(VALID); value["speech"][1]["text"] = text
            self.assertEqual(self.parse(DISPLAY, value)["state"], "option_unverified")

    def test_option_action_with_independent_caveat_is_valid(self):
        for text in ("公開ウェブを検索できます。診断チェックリストの確認ができます。ただし結果は保証できません。",
                     "公開ウェブを検索できます。診断チェックリストの確認ができますが、結果は保証できません。"):
            value = copy.deepcopy(VALID); value["speech"][1]["text"] = text
            self.assertEqual(self.parse(DISPLAY, value)["state"], "ready")
        for text in ("公開ウェブを検索できます。診断チェックリストの確認ができません。",
                     "公開ウェブを検索できます。診断チェックリストを確認することはできません。",
                     "ウェブ検索か診断チェックリストの確認ができません。"):
            value = copy.deepcopy(VALID); value["speech"][1]["text"] = text
            self.assertEqual(self.parse(DISPLAY, value)["state"], "option_unverified")

    def test_markdown_bracket_prose_does_not_hide_decision_status(self):
        for display in ("[注意] 工具請求遭阻擋，操作失敗，尚未驗證。",
                        "[詳細](https://example.test/status)：操作失敗，尚未驗證。"):
            self.assertIn(self.parse(display, lane(speech=[segment("処理は成功しました。")]))["state"], {"semantic_unverified", "anchor_status_mismatch"})

    def test_fail_then_success_transition_uses_display_evidence(self):
        text = "最初失敗しましたが、再実行後成功しました。"
        value = lane([anchor("s", "第一次操作失敗")], [segment(text, "s")])
        self.assertEqual(self.parse("第一次操作失敗，重試後成功。", value)["state"], "ready")
        self.assertEqual(self.parse("第一次操作失敗。", value)["state"], "anchor_status_conflict")
        self.assertEqual(self.parse("操作沒有失敗，已完成。", lane([anchor("s", "操作沒有失敗，已完成")],
                         [segment("操作は失敗していません。完了しました。", "s")]))["state"], "ready")

    def test_non_decision_english_negation_does_not_require_status_anchors(self):
        self.assertEqual(self.parse("I can't wait to see you again!", lane(speech=[segment("また会えるのが楽しみです。")]))["state"], "ready")

    def test_options_cannot_be_downgraded_or_replaced_by_screen_notice(self):
        for mode in ("downgrade", "notice", "omit"):
            value = copy.deepcopy(VALID)
            if mode == "downgrade": value["anchors"][2]["importance"] = "display_only"
            elif mode == "omit":
                value["anchors"].pop(2); value["speech"][1]["source_ids"] = ["a"]
            else: value["speech"][1]["text"] = "選択肢は画面に表示しています。"
            self.assertIn(self.parse(DISPLAY, value)["state"], {"semantic_unverified", "option_unverified"})

    def test_unlabelled_or_options_and_unknown_translated_actions(self):
        display = "可以公開網路查詢或先看診斷清單。"
        value = lane([anchor("a", display, "options")], [segment("ウェブ検索か診断チェックリストの確認ができます。", "a")])
        self.assertEqual(self.parse(display, value)["state"], "ready")
        value["speech"][0]["text"] = "ウェブ検索できます。"
        self.assertEqual(self.parse(display, value)["state"], "semantic_unverified")
        value = lane([anchor("a", "折紙を折る", "option")], [segment("We can fold paper.", "a")], locale="en-US")
        result = self.parse("折紙を折る", value, dict(v1.CHAT_SPEECH_DEFAULTS, locale="en-US"))
        self.assertEqual(result["state"], "semantic_unverified")
        self.assertEqual(result["text"], "We can fold paper.")
        self.assertEqual(result["diagnostics"]["soft_failures"][0]["rule_id"], "option_unverified")

    def test_price_digits_roles_signs_and_percentages(self):
        for spoken, state in [("価格は100.50、損切りは95です。", "ready"),
                              ("価格は100.5です。", "anchor_value_mismatch"),
                              ("価格は95、損切りは100.5です。", "anchor_value_mismatch"),
                              ("価格は百点五、損切りは九十五です。", "anchor_value_mismatch")]:
            value = lane([anchor("p", "價格100.5，停損95", "fact")], [segment(spoken, "p")])
            self.assertEqual(self.parse("價格100.5，停損95", value)["state"], state)
        for text in ("比率は5%です。", "比率は5です。"):
            state = self.parse("比率-5%", lane([anchor("p", "比率-5%", "fact")], [segment(text, "p")]))["state"]
            self.assertEqual(state, "anchor_value_mismatch")

    def test_unanchored_or_invented_prices_and_error_code(self):
        self.assertEqual(self.parse("價格100.5", lane(speech=[segment("価格は100.5です。")]))["state"], "unanchored_value")
        self.assertEqual(self.parse("你好", lane(speech=[segment("価格は999です。")]))["state"], "unbacked_value")
        for text, state in [("HTTP403で操作は失敗しました。", "ready"), ("操作は失敗しました。", "anchor_value_mismatch")]:
            display = "操作失敗 HTTP403"
            self.assertEqual(self.parse(display, lane([anchor("s", display)], [segment(text, "s")]))["state"], state)

    def test_negated_failure_and_positive_success_conflict(self):
        for text in ("操作は失敗していません。", "操作は失敗しましたが、成功しました。"):
            self.assertIn(self.parse("操作失敗", lane([anchor("s", "操作失敗")], [segment(text, "s")]))["state"],
                          {"anchor_status_mismatch", "anchor_status_conflict"})

    def test_technical_display_is_lossless_and_does_not_require_all_table_digits(self):
        display = ('技術資料如下。\n````text\n<<<KURO_SPEECH_V1>>>\n<<<KURO_SPEECH_V2>>>\nx={"a":99}\n````\n'
                   '字面 `\n<<<KURO_SPEECH_V2>>>\n`\nhttps://example.test/a\nC:\\project\\test.py\n'
                   '{"key": 1000}\n|價格|狀態|\n|999|stale|\nTraceback (most recent call last):\n  File "x.py", line 45\nValueError: fixture\n')
        value = lane([anchor("c", 'x={"a":99}', "code", "display_only")], [segment("コードや表、参照リンクとログは画面に表示しています。", "c")])
        raw = display + footer(value)
        parser = SpeechLaneParser()
        self.assertEqual("".join(parser.feed(ch) for ch in raw) + parser.finish_display(), display)
        result = parser.result(v1.CHAT_SPEECH_DEFAULTS)
        self.assertEqual(result["state"], "semantic_unverified")
        self.assertIn("unanchored_status", [d["rule_id"] for d in result["diagnostics"]["soft_failures"]])
        self.assertNotIn("999", result["text"])

    def test_technical_speech_is_rejected_before_any_segment_is_queued(self):
        for text in ("https://example.test", "設定は`x`です。", 'x = 12', '{"x":1}', '|a|b|', r'場所はC:\\project\\a.pyです。',
                     "Traceback (most recent call last):", "SELECT x FROM data", "<<<KURO_SPEECH_V1>>>"):
            value = lane(speech=[segment("確認しました。"), segment(text)])
            self.assertEqual(self.parse("技術資料", value)["state"], "technical_payload")

    def test_schema_and_references_fail_closed(self):
        cases = []
        for key, val in [("contract", v1.SPEECH_LANE_CONTRACT), ("locale", "en-US"), ("policy", "brief"),
                         ("emotion", []), ("anchors", {}), ("speech", {})]:
            value = copy.deepcopy(VALID); value[key] = val; cases.append(value)
        value = copy.deepcopy(VALID); value["anchors"].append(value["anchors"][0]); cases.append(value)
        value = copy.deepcopy(VALID); value["anchors"][0]["source"] = "not in Display"; cases.append(value)
        for ids in (["unknown"], ["s", "s"], [None], []):
            value = copy.deepcopy(VALID); value["speech"][0]["source_ids"] = ids; cases.append(value)
        value = copy.deepcopy(VALID); value["speech"][0]["text"] = "This is English."; cases.append(value)
        value = copy.deepcopy(VALID); value["anchors"][0]["source"] = "x" * 401; cases.append(value)
        for value in cases:
            self.assertNotEqual(self.parse(DISPLAY, value)["state"], "ready")

    def test_duplicate_keys_malformed_oversize_and_empty(self):
        for data in ('{broken', json.dumps(VALID)[:-1] + ',"emotion":"joy"}', 'x' * 13000):
            parser = SpeechLaneParser(); self.assertEqual(parser.feed("回答" + SPEECH_LANE_V2_MARKER + data), "回答")
            self.assertIn(parser.result(v1.CHAT_SPEECH_DEFAULTS)["state"], {"malformed", "oversize"})
        self.assertEqual(self.parse("你好", lane())["state"], "silent")

    def test_absolute_bol_footer_and_truncated_marker_are_private(self):
        value = lane(speech=[segment("こんにちは。")])
        for raw, state in ((footer(value).lstrip("\n"), "empty_display"),
                           (SPEECH_LANE_V2_MARKER.lstrip("\n") + "{broken", "malformed"),
                           ("<<<KURO_SPEECH_", "missing")):
            for split in range(len(raw) + 1):
                parser = SpeechLaneParser()
                visible = parser.feed(raw[:split]) + parser.feed(raw[split:]) + parser.finish_display()
                self.assertEqual(visible, "")
                self.assertEqual(parser.result(v1.CHAT_SPEECH_DEFAULTS)["state"], state)
        parser = SpeechLaneParser()
        self.assertEqual(parser.feed(v1.footer().lstrip("\n")) + parser.finish_display(), "")

    def test_prefix_stripping_is_bounded_and_literals_and_legacy_survive(self):
        for prefix in ("[neutral] ", "[joy]\n", "[sadness]\r\n"):
            raw = prefix + "完成。" + footer(lane(speech=[segment("完了しました。")]))
            for split in range(len(raw) + 1):
                parser = SpeechLaneParser()
                self.assertEqual(parser.feed(raw[:split]) + parser.feed(raw[split:]) + parser.finish_display(), "完成。")
        for literal in ("`[neutral]` 是字面。", "```text\n[neutral]\n```", '"[neutral]" 是範例。', "[neutral]", "文字 [neutral] 保留"):
            self.parse(literal, lane(speech=[segment("例は画面にあります。")]))
        for display in ("[neutral] 是參考連結。\n\n[neutral]: https://example.test/reference",
                        "[neutral]\n\n[neutral]: https://example.test/reference", "[neutral] " + "長文字" * 1500):
            raw = display + footer(lane(speech=[segment("例は画面にあります。")]))
            for chunks in ([raw], list(raw)):
                parser = SpeechLaneParser()
                self.assertEqual("".join(parser.feed(chunk) for chunk in chunks) + parser.finish_display(), display)
                self.assertEqual(parser.result(v1.CHAT_SPEECH_DEFAULTS)["state"], "ready")
        parser = SpeechLaneParser()
        self.assertEqual(parser.feed("[neutral] 尚未完成\n<<<KURO_SPEECH_") + parser.finish_display(), "[neutral] 尚未完成")
        parser = SpeechLaneParser(strip_control_prefix=False)
        self.assertEqual(parser.feed("[neutral] 完成。") + parser.finish_display(), "[neutral] 完成。")


class SemanticConversationTests(unittest.IsolatedAsyncioTestCase):
    setUp = v1.ConversationTests.setUp
    context = v1.ConversationTests.context
    run_turn = v1.ConversationTests.run_turn

    async def test_one_llm_complete_display_history_private_emotion_and_no_bridge(self):
        context, llm, _ = self.context([list("[neutral] " + DISPLAY + footer(VALID))])
        self.assertEqual(await self.run_turn(context), DISPLAY)
        self.assertEqual(len(llm.calls), 1)
        self.assertIn("Runtime output contract: kuro.speech-lanes.v2", llm.calls[0]["system"])
        self.assertEqual(context.agent_engine._memory[-1]["content"], DISPLAY)
        self.assertEqual(self.stores.call_args.kwargs["content"], DISPLAY)
        self.assertEqual(self.memories.call_args.args[3]["assistant_text"], DISPLAY)
        self.assertTrue(any(event.get("type") == "emotion" and event["emotion"] == "joy" for event in self.send.events))
        public = json.dumps(self.send.events, ensure_ascii=False)
        self.assertNotIn("source_ids", public); self.assertNotIn("KURO_SPEECH", public)
        self.assertNotIn("[neutral]", public)
        self.assertEqual("".join(event.get("display_text", {}).get("text", "") for event in self.send.events), DISPLAY)
        self.assertIn("診断チェックリスト", "".join(call.kwargs["text"] for call in self.tts.async_generate_audio.await_args_list))

    async def test_chat_without_anchors_reaches_tts(self):
        display = "這部分可以直接改，沒有其他問題"
        context, _, _ = self.context([[display + footer(lane(speech=[segment("そのまま変更できます。ほかに問題はありません。")]))]])
        self.assertEqual(await self.run_turn(context), display)
        self.assertEqual("".join(c.kwargs["text"] for c in self.tts.async_generate_audio.await_args_list), "そのまま変更できます。ほかに問題はありません。")

    async def test_missing_display_never_exposes_private_json_or_generates_voice(self):
        context, llm, _ = self.context([list(footer(lane(speech=[segment("こんにちは。")])).lstrip("\n"))])
        self.assertEqual(await self.run_turn(context), "")
        self.assertEqual(len(llm.calls), 1)
        self.tts.async_generate_audio.assert_not_awaited()
        self.assertNotIn("KURO_SPEECH", json.dumps(self.send.events))
        self.assertTrue(all("KURO_SPEECH" not in msg["content"] for msg in context.agent_engine._memory))

    async def test_unrepairable_option_is_partial_and_independent_facts_survive(self):
        for text in ("ウェブ検索できません。", "https://example.test"):
            self.tts.async_generate_audio.reset_mock()
            self.send.events.clear()
            value = copy.deepcopy(VALID)
            value["speech"][1]["text"] = text
            context, llm, _ = self.context([[DISPLAY + footer(value)]])
            self.assertEqual(await self.run_turn(context), DISPLAY)
            spoken = [call.kwargs["text"] for call in self.tts.async_generate_audio.await_args_list]
            self.assertEqual(spoken, [VALID["speech"][i]["text"] for i in (0, 2)])
            self.assertEqual(len(llm.calls), 2)
            self.assertTrue(any(event.get("missing_units") == [2] for event in self.send.events))

    async def test_tool_continuation_preserves_native_arguments_and_final_only_speech(self):
        tc = v1.ToolCallObject(id="fixture-call", function=v1.ToolCallFunctionObject(name="fixture_read", arguments='{"query":"literal <<<KURO_SPEECH_V2>>>"}'))
        context, llm, executor = self.context([["準備查詢。" + footer(VALID), [tc]], [DISPLAY + footer(VALID)]], tools=True)
        async def execute(**kwargs):
            self.tts.async_generate_audio.assert_not_awaited()
            self.assertEqual(kwargs["tool_calls"][0].function.arguments, tc.function.arguments)
            yield {"type": "tool_call_status", "status": "failed", "tool_name": "fixture_read", "content": "synthetic failure"}
            yield {"type": "final_tool_results", "results": [{"role": "tool", "tool_call_id": "fixture-call", "content": "failed"}]}
        executor.execute_tools = execute
        with patch("open_llm_vtuber.conversations.single_conversation._store_tool_status_event"):
            self.assertEqual(await self.run_turn(context), "準備查詢。" + DISPLAY)
        self.assertEqual(len(llm.calls), 2)
        self.assertTrue(any(event.get("type") == "tool_call_status" for event in self.send.events))
        self.assertTrue(all("KURO_SPEECH" not in msg["content"] for msg in context.agent_engine._memory))

    async def test_cancel_after_footer_before_final_boundary_is_silent(self):
        context, _, _ = self.context([[]]); entered = asyncio.Event()
        async def stream(*args, **kwargs):
            yield DISPLAY + footer(VALID)
            entered.set(); await asyncio.Event().wait()
        context.agent_engine._llm.chat_completion = stream
        task = asyncio.create_task(self.run_turn(context))
        await asyncio.wait_for(entered.wait(), 1); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.tts.async_generate_audio.assert_not_awaited()

    async def test_unanchored_long_sentences_use_independent_chunks(self):
        spoken = "最初の説明です。次の内容を話します。三つ目の内容です。さらに説明します。続けて話します。最後の説明です。"
        for failure in (False, True):
            self.tts.async_generate_audio.reset_mock()
            self.tts.async_generate_audio.return_value = None if failure else "fixture.wav"
            context, llm, _ = self.context([["長い説明。" + footer(lane(speech=[segment(spoken)]))]])
            self.assertEqual(await self.run_turn(context), "長い説明。")
            self.assertEqual(len(llm.calls), 1)
            self.assertEqual(self.tts.async_generate_audio.await_count, 6)
            self.assertIn({"type": "backend-synth-complete"}, self.send.events)
            if not failure:
                self.assertEqual("".join(call.kwargs["text"] for call in self.tts.async_generate_audio.await_args_list), spoken)

    async def test_both_marker_literals_survive_actual_memory(self):
        display = "文件\n```text\n<<<KURO_SPEECH_V1>>>\n<<<KURO_SPEECH_V2>>>\n[neutral]\n```\n`[neutral]` 保留。"
        context, _, _ = self.context([list(display + footer(lane(speech=[segment("例は画面にあります。")])) )])
        self.assertEqual(await self.run_turn(context), display)
        self.assertEqual(context.agent_engine._memory[-1]["content"], display)


class CentralPathRegressionTests(unittest.IsolatedAsyncioTestCase):
    """Real conversation/parser/queue/manager/central adapter/WAV serializer;
    only LLM, HTTP transport, history/memory storage and audio WS are fixtures.
    """
    context = v1.ConversationTests.context
    run_turn = v1.ConversationTests.run_turn

    def setUp(self):
        from open_llm_vtuber.tts.gpt_sovits_tts import TTSEngine
        v1.ConversationTests.setUp(self)
        self.patches[-1].stop()  # Exercise real prepare_audio_payload with valid synthetic PCM.
        self.tts = TTSEngine(api_url='http://central.invalid/tts', voice_id='fixture', text_lang='ja')
        self.tts.generate_cache_file_name = Mock(side_effect=lambda name, ext: str(Path(self.temp.name) / f'{name}.{ext}'))
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
            audio.writeframes(b'\x10\x00\xf0\xff' * 800)
        self.wav = stream.getvalue()
        health = SimpleNamespace(status_code=200, json=lambda: dict(service='voice-runtime', protocol_version=1,
            status='available', voices=[dict(voice_id='fixture')]))
        response = SimpleNamespace(status_code=200, headers={'Content-Type': 'audio/wav'}, content=self.wav)
        self.http_get = Mock(return_value=health)
        self.http_post = Mock(return_value=response)
        for item in (patch('requests.sessions.Session.request', side_effect=AssertionError('unexpected real HTTP')),
                     patch('open_llm_vtuber.tts.gpt_sovits_tts.requests.get', self.http_get),
                     patch('open_llm_vtuber.tts.gpt_sovits_tts.requests.post', self.http_post)):
            item.start(); self.addCleanup(item.stop)

    async def check_turn(self, display, value, ready):
        self.send.events.clear(); self.http_get.reset_mock(); self.http_post.reset_mock()
        context, llm, _ = self.context([list(display + footer(value))])
        with patch('open_llm_vtuber.conversations.tts_manager.logger.info') as timing:
            self.assertEqual(await self.run_turn(context), display)
        metrics = next(json.loads(call.args[1]) for call in timing.call_args_list if call.args[0] == 'speech_timing {}')
        self.assertEqual(metrics['bridge_requests'], 0)
        self.assertEqual(len(llm.calls), 1 if ready else 2)
        self.assertEqual(context.agent_engine._memory[-1]['content'], display)
        self.assertEqual(self.stores.call_args.kwargs['content'], display)
        self.assertEqual(self.memories.call_args.args[3]['assistant_text'], display)
        self.assertEqual(''.join(event.get('display_text', {}).get('text', '') for event in self.send.events), display)
        self.assertNotIn('KURO_SPEECH', json.dumps(self.send.events))
        self.assertNotIn('source_ids', json.dumps(self.send.events))
        self.assertEqual(self.send.events[-1], {'type': 'control', 'text': 'conversation-chain-end'})
        audio = [event for event in self.send.events if event.get('audio')]
        self.assertEqual(bool(audio), ready)
        if ready:
            self.assertEqual(metrics['state'], 'ready')
            self.assertIn({'type': 'backend-synth-complete'}, self.send.events)
            self.assertEqual(self.http_post.call_count, len(audio))
            self.assertEqual(''.join(call.kwargs['json']['text'] for call in self.http_post.call_args_list),
                             ' '.join(item['text'] for item in value['speech']))
            for call in self.http_post.call_args_list:
                self.assertEqual(call.args, ('http://central.invalid/tts',))
                self.assertEqual(call.kwargs['json']['voice'], 'fixture')
                self.assertEqual(call.kwargs['json']['language'], 'ja')
            messages = [call.args[0] for call in timing.call_args_list]
            for event in ('tts_request', 'tts_complete', 'websocket_audio_sent'):
                self.assertEqual(sum(f'event={event} ' in message for message in messages), len(audio))
            for payload in audio:
                with wave.open(io.BytesIO(base64.b64decode(payload['audio'])), 'rb') as decoded:
                    self.assertEqual(decoded.getnframes(), 1600)
                self.assertEqual(payload['display_text']['text'], '')
                self.assertTrue(payload['volumes'])
            self.assertFalse(list(Path(self.temp.name).glob('*.wav')))
        else:
            self.http_get.assert_not_called(); self.http_post.assert_not_called()
            self.assertIsNone(metrics['anchors'])
            self.assertIsNone(metrics['semantic_segments'])
            status = next(event for event in self.send.events if event['type'] == 'speech-status' and event.get('status') != 'preparing')
            self.assertEqual(status['reason'], metrics['state'])
            self.assertEqual(status['validation']['received_semantic_segments'], len(value['speech']))
            self.assertEqual(status['validation']['received_anchors'], len(value['anchors']))

    async def test_natural_technical_speech_reaches_mock_central_and_audio_ws(self):
        await self.check_turn(TECHNICAL_DISPLAY, lane(speech=[segment(TECHNICAL_SPOKEN)]), True)

    async def test_natural_options_reach_mock_central_and_audio_ws(self):
        await self.check_turn(OPTION_DISPLAY, option_lane(), True)

    async def test_blocked_payload_missing_option_and_reversals_never_call_central(self):
        cases = [(TECHNICAL_DISPLAY, lane(speech=[segment('説明します。'), segment('https://example.test')])),
                 (OPTION_DISPLAY, option_lane('公開ウェブを検索できません。')),
                 (OPTION_DISPLAY, option_lane('ウェブ検索か、診断チェックリストの確認ができません。'))]
        for text in ('処理は成功しました。', '操作は失敗しましたが、成功しました。'):
            cases.append(('操作失敗，尚未驗證', lane([anchor('s', '操作失敗，尚未驗證')], [segment(text, 's')])))
        for display, value in cases:
            with self.subTest(display=display):
                await self.check_turn(display, value, False)


if __name__ == "__main__":
    unittest.main()
