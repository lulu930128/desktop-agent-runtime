"""Consumer regressions for private rendering, partial playback and lossless Display."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_speech_semantic_alignment as fixture
from open_llm_vtuber.conversations.conversation_utils import _natural_speech_chunks
from open_llm_vtuber.conversations.speech_presentation import filter_speech_lane
from open_llm_vtuber.conversations.speech_recovery import (
    recover_speech_lane,
    requested_reading,
)
from open_llm_vtuber.websocket_handler import PrimaryConversationOutput

DEFAULT = fixture.v1.CHAT_SPEECH_DEFAULTS


class SpeechVNextTests(unittest.IsolatedAsyncioTestCase):
    def test_explicit_reading_respects_negation(self):
        self.assertEqual(requested_reading("這次不用全文朗讀，只說重點。"), "summary")
        self.assertEqual(requested_reading("這次請全文朗讀。"), "detailed")
        self.assertIsNone(requested_reading("跟我聊聊今天的事。"))

    def test_central_contract_and_pure_kanji(self):
        self.assertEqual(filter_speech_lane("確認完了", "ja-JP"), ("確認完了", "ready"))
        for text in ("あ" * 2001, "𠮷" * 2000, "未確認、" * 650):
            chunks = _natural_speech_chunks(text)
            self.assertEqual("".join(chunks), text)
            self.assertGreater(len(chunks), 1)
            for chunk in chunks:
                self.assertLessEqual(len(chunk), 2000)
                self.assertLessEqual(
                    len(
                        json.dumps(
                            dict(
                                text=chunk, language="ja", speed_factor=1, voice="kuro"
                            )
                        ).encode()
                    ),
                    16384,
                )

    async def test_skip_raw_only_and_preserve_neighbours(self):
        display = "先休息。https://example.test 明天再見。"
        value = fixture.lane(
            [
                fixture.anchor("a", "先休息"),
                fixture.anchor("b", "https://example.test", "url", "display_only"),
                fixture.anchor("c", "明天再見"),
            ],
            [
                fixture.segment("休みましょう。", "a"),
                fixture.segment("https://example.test", "b"),
                fixture.segment("また明日。", "c"),
            ],
        )
        original = fixture.SemanticParserTests().parse(display, value)
        self.assertEqual(original["state"], "technical_payload")
        agent = Mock()
        result = await recover_speech_lane(
            original,
            display=display,
            settings=DEFAULT,
            agent=agent,
            metrics={},
            send=AsyncMock(),
        )
        self.assertEqual(
            [s["text"] for s in result["speech"]], ["休みましょう。", "また明日。"]
        )
        agent.render_speech_only.assert_not_called()

    async def test_unanchored_japanese_keeps_exact_neighbours_of_raw_url(self):
        display = "外は雨です。https://example.test 傘を持ってね。"
        lane = fixture.lane(
            speech=[
                fixture.segment("外は雨です。"),
                fixture.segment("https://example.test"),
                fixture.segment("傘を持ってね。"),
            ]
        )
        result = await recover_speech_lane(
            fixture.SemanticParserTests().parse(display, lane),
            display=display,
            settings=DEFAULT,
            agent=Mock(),
            metrics={},
            send=AsyncMock(),
        )
        self.assertEqual(
            [s["text"] for s in result["speech"]], ["外は雨です。", "傘を持ってね。"]
        )

    async def test_repair_only_mixed_clause_with_condition(self):
        display = "可以休息。設定錯誤時不能執行。明天再見。"
        value = fixture.lane(
            [
                fixture.anchor("a", "可以休息"),
                fixture.anchor("b", "設定錯誤時不能執行"),
                fixture.anchor("c", "明天再見"),
            ],
            [
                fixture.segment("休みましょう。", "a"),
                fixture.segment("設定が`false`の場合は実行できません。", "b"),
                fixture.segment("また明日。", "c"),
            ],
        )
        calls = []

        class Agent:
            async def render_speech_only(self, source, prompt):
                calls.append(source)
                yield "設定に誤りがある場合は実行できません。"

        result = await recover_speech_lane(
            fixture.SemanticParserTests().parse(display, value),
            display=display,
            settings=DEFAULT,
            agent=Agent(),
            metrics={},
            send=AsyncMock(),
        )
        self.assertEqual(calls, ["設定錯誤時不能執行"])
        self.assertEqual(
            [s["text"] for s in result["speech"]],
            ["休みましょう。", "設定に誤りがある場合は実行できません。", "また明日。"],
        )

    async def test_detailed_complete_japanese_prose_skips_fence_keeps_ending(self):
        text = "今日は静かです。\n```py\nprint(123)\n```\n家の明かりが見えました。"
        agent = Mock()
        result = await recover_speech_lane(
            None,
            display=text,
            settings=dict(DEFAULT, policy="detailed"),
            agent=agent,
            metrics={},
            send=AsyncMock(),
        )
        self.assertEqual(
            [s["text"] for s in result["speech"]],
            ["今日は静かです。", "家の明かりが見えました。"],
        )
        self.assertFalse(result["missing_units"])
        agent.render_speech_only.assert_not_called()

    async def test_prefix_ack_does_not_confirm_tail(self):
        socket = Mock(send_text=AsyncMock())
        output = PrimaryConversationOutput(AsyncMock(), lambda: {"pet": socket})
        for n in (1, 2):
            await output(
                json.dumps(
                    dict(type="audio", audio="fixture", segment_id=n, audio_seconds=60)
                )
            )
        await output('{"type":"backend-synth-complete"}')
        output.acknowledge("pet", output.request_id, "completed", [1])
        response = await output.wait_for_playback()
        self.assertEqual(
            (response["status"], response["missing_segments"]), ("partial", [2])
        )


class CoverageTests(unittest.IsolatedAsyncioTestCase):
    def test_detailed_table_retains_roles_and_signed_percentage(self):
        from open_llm_vtuber.conversations.speech_recovery import reading_units
        from open_llm_vtuber.conversations.speech_presentation import (
            _semantic_prose,
            _critical_values,
        )

        display = "|名稱|價格|停損|比率|\n|---|---|---|---|\n|測試|100.5|95|-5%|"
        (unit,) = reading_units(display)
        self.assertEqual(_semantic_prose(display), unit)
        self.assertTrue({"price:100.5", "stop:95", "-5%"} <= _critical_values(unit))

    async def test_repairs_only_omitted_numeric_role(self):
        display = "目前尚未驗證。停損95。"
        original = dict(state="ready", text="まだ未検証です。")

        class Agent:
            async def render_speech_only(self, source, prompt):
                self.source = source
                yield "損切りは95です。"

        agent = Agent()
        result = await recover_speech_lane(
            original,
            display=display,
            settings=DEFAULT,
            agent=agent,
            metrics={},
            send=AsyncMock(),
        )
        self.assertEqual(agent.source, "停損95。")
        self.assertEqual(result["text"], "まだ未検証です。 損切りは95です。")

    async def test_discovery_success_does_not_mask_failed_or_unknown_tool(self):
        for status, expected in [
            ("failed", "失敗"),
            ("unknown", "未確認"),
            ("cancelled", "取り消"),
        ]:
            result = await recover_speech_lane(
                dict(state="ready", text="あとで確認しましょう。"),
                display="稍後再查。",
                settings=DEFAULT,
                agent=Mock(),
                metrics={},
                send=AsyncMock(),
                evidence=[
                    ("kuro_discover", "completed"),
                    ("omi-search::fixture_read", status),
                ],
            )
            self.assertIn(expected, result["text"])
            self.assertIn("あとで確認しましょう。", result["text"])

    async def test_unknown_tool_result_cannot_be_spoken_as_verified(self):
        class Agent:
            async def render_speech_only(self, source, prompt):
                yield "{}"

        result = await recover_speech_lane(
            dict(state="ready", text="確認しました。"), display="已確認。",
            settings=DEFAULT, agent=Agent(), metrics={}, send=AsyncMock(),
            evidence=[("kuro_discover", "completed"), ("omi-search::fixture_read", "unknown")],
        )
        self.assertEqual(result["text"], "ツールの実行結果は未確認です。")
        self.assertEqual(result["missing_units"], [1])

    async def test_early_stop_accounts_for_a_tail_sent_later(self):
        output = PrimaryConversationOutput(
            AsyncMock(), lambda: {"pet": Mock(send_text=AsyncMock())}
        )
        for segment in [1, 2]:
            await output(
                json.dumps(
                    dict(type="audio", segment_id=segment, audio="wav", audio_seconds=1)
                )
            )
        output.acknowledge("pet", output.request_id, "interrupted", [1])
        await output(
            json.dumps(dict(type="audio", segment_id=3, audio="wav", audio_seconds=1))
        )
        await output('{"type":"backend-synth-complete"}')
        receipt = await output.wait_for_playback()
        self.assertEqual(
            (receipt["status"], receipt["missing_segments"]), ("interrupted", [2, 3])
        )


class CancellationHistoryTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixture.v1.ConversationTests.setUp
    context = fixture.v1.ConversationTests.context
    run_turn = fixture.v1.ConversationTests.run_turn

    async def test_interrupt_after_display_preserves_exactly_one_full_ai_message(self):
        from open_llm_vtuber.conversations.conversation_handler import (
            handle_individual_interrupt,
        )

        display = "完整回答。結果尚未驗證。"
        context, _, _ = self.context(
            [
                [
                    display
                    + fixture.footer(
                        fixture.lane(speech=[fixture.segment("未検証です。")])
                    )
                ]
            ]
        )
        entered = asyncio.Event()

        async def waiting(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        with patch(
            "open_llm_vtuber.conversations.speech_recovery.recover_speech_lane", waiting
        ):
            task = asyncio.create_task(self.run_turn(context))
            await asyncio.wait_for(entered.wait(), 2)
            with patch(
                "open_llm_vtuber.conversations.conversation_handler.store_message"
            ) as interrupt_store:
                await handle_individual_interrupt(
                    "fixture", {"fixture": task}, context, "launcher-interrupt"
                )
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertEqual(
                [
                    c.kwargs["content"]
                    for c in self.stores.call_args_list
                    if c.kwargs.get("role") == "ai"
                ],
                [display],
            )
            self.assertEqual(
                [c.kwargs["role"] for c in interrupt_store.call_args_list], ["system"]
            )
            self.assertEqual(context.agent_engine._memory[-1]["content"], display)
