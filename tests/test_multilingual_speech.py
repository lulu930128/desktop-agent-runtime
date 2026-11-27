"""G0-G4 fixtures: no cloud, production runtime, model, history or TTS IO."""
import asyncio
import copy
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Open-LLM-VTuber/src"), str(ROOT / "Open-LLM-VTuber")]

from loguru import logger
from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
from open_llm_vtuber.agent.output_types import SentenceOutput, DisplayText
from open_llm_vtuber.conversations.single_conversation import process_single_conversation, BridgeSpeechEngine
from open_llm_vtuber.conversations.conversation_utils import process_user_input
from open_llm_vtuber.conversations.speech_presentation import (
    SpeechLaneParser, SPEECH_LANE_MARKER, SPEECH_LANE_CONTRACT, filter_speech_lane,
)
from open_llm_vtuber.conversations.tts_manager import TTSTaskManager
from open_llm_vtuber.mcpp.types import ToolCallObject, ToolCallFunctionObject
from kuro_launcher.config import read_chat_speech_settings, update_chat_speech_settings, CHAT_SPEECH_DEFAULTS


def footer(text="結果は未検証です。価格は100.5、損切りは95です。データは古いままです。", **overrides):
    value = dict(contract=SPEECH_LANE_CONTRACT, locale="ja-JP", policy="summary", text=text, emotion="neutral")
    value.update(overrides)
    return SPEECH_LANE_MARKER + "\n" + json.dumps(value, ensure_ascii=False)


class ParserTests(unittest.TestCase):
    def test_every_chunk_boundary_preserves_display_and_hides_footer(self):
        display = '結論：未驗證。\n```python\nx = {"key": 1}\n```\n|價位|狀態|\n|100.5|stale|\nhttps://example.test\n'
        raw = display + footer()
        for split in range(len(raw) + 1):
            parser = SpeechLaneParser()
            visible = parser.feed(raw[:split]) + parser.feed(raw[split:]) + parser.finish_display()
            self.assertEqual(visible, display)
            self.assertEqual(parser.result(CHAT_SPEECH_DEFAULTS)["state"], "ready")

    def test_missing_and_malformed_footer_never_lose_display(self):
        for raw, state in [('完整回答 {"broken":', "missing"), ("完整回答" + SPEECH_LANE_MARKER + '{"bad":', "malformed"),
                           ("完整回答" + footer(locale="en-US"), "malformed"),
                           ("完整回答" + SPEECH_LANE_MARKER + "x" * 13000, "malformed")]:
            with self.subTest(state=state):
                parser = SpeechLaneParser(); visible = parser.feed(raw) + parser.finish_display()
                self.assertEqual(visible, raw if state == "missing" else "完整回答")
                self.assertEqual(parser.result(CHAT_SPEECH_DEFAULTS)["state"], state)

    def test_truncated_control_line_not_displayed(self):
        parser = SpeechLaneParser()
        self.assertEqual(parser.feed("回答\n<<<KURO_SPEECH_") + parser.finish_display(), "回答")

    def test_literal_markers_in_fences_inline_code_and_escaped_prose(self):
        examples = ["文件\n```text\n<<<KURO_SPEECH_V1>>>\n{broken}\n```\n後續完整回答。",
                    "文件\n~~~~text\n<<<KURO_SPEECH_V1>>>\n~~~\n仍在四字元 fence\n~~~~\n後續回答。",
                    "字面內容 `\n<<<KURO_SPEECH_V1>>>\n` 之後也保留。",
                    "文件\n\\<<<KURO_SPEECH_V1>>>\n後續回答。"]
        for display in examples:
            raw = display + footer()
            for split in range(len(raw) + 1):
                parser = SpeechLaneParser()
                visible = parser.feed(raw[:split]) + parser.feed(raw[split:]) + parser.finish_display()
                self.assertEqual(visible, display)
                self.assertEqual(parser.result(CHAT_SPEECH_DEFAULTS)["state"], "ready")
            parser = SpeechLaneParser()
            self.assertEqual("".join(parser.feed(ch) for ch in raw) + parser.finish_display(), display)

    def test_truncated_marker_in_unclosed_literal_preserved_and_unescaped_line_reserved(self):
        display = "```text\n<<<KURO_SPEECH_"
        parser = SpeechLaneParser()
        self.assertEqual(parser.feed(display) + parser.finish_display(), display)
        self.assertEqual(parser.result(CHAT_SPEECH_DEFAULTS)["state"], "missing")
        parser = SpeechLaneParser()
        self.assertEqual(parser.feed("prose" + SPEECH_LANE_MARKER + "reserved") + parser.finish_display(), "prose")

    def test_duplicate_fields_and_trailing_data_are_rejected(self):
        for extra in [',"text":"conflicting"}', '} trailing']:
            parser = SpeechLaneParser(); parser.feed("回答" + footer()[:-1] + extra)
            self.assertEqual(parser.result(CHAT_SPEECH_DEFAULTS)["state"], "malformed")

    def test_technical_payloads_rejected_without_cutting_conditions(self):
        for text in ['結論です。```py\nx=1\n```', '失敗です。`x` が必要です。', 'https://example.test',
                     '{"price": 100}', '| price | stale |', 'Traceback (most recent call last):',
                     r'失敗です。C:\project\test.py を確認してください。', '2026-10-31T12:00 ERROR failed',
                     '失敗です。ログは/tmp/server.logにあります。', 'def foo(): return 1', 'SELECT price FROM data']:
            with self.subTest(text=text):
                self.assertEqual(filter_speech_lane(text, "ja-JP")[0], "")

    def test_prices_negation_freshness_and_locale_are_not_truncated(self):
        for locale, text in [("ja-JP", "価格100.5、損切り95です。未検証でデータは古いため、成功とは言えません。"),
                             ("zh-Hant", "價格100.5，停損95；資料過期、來源缺失且未驗證，不能判定成功。"),
                             ("en-US", "Price 100.5, stop loss 95. Data is stale and unverified; success is unknown.")]:
            self.assertEqual(filter_speech_lane(text, locale), (text, "ready"))
        self.assertEqual(filter_speech_lane("結果は未検証です。", "en-US")[1], "locale_mismatch")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "launcher.yaml"
        self.before = b"# fixture\r\npaths:\r\n  root: fixture\r\n# preserved comment\r\nother: true\r\n"
        self.path.write_bytes(self.before)

    def test_defaults_write_readback_reopen_and_preserve_other_bytes(self):
        for policy, locale in [("brief", "ja-JP"), ("summary", "zh-Hant"), ("detailed", "en-US")]:
            first = read_chat_speech_settings(self.path)
            desired = dict(locale=locale, policy=policy, route="dual_lane")
            written = update_chat_speech_settings(self.path, desired, first["revision"])
            self.assertTrue(written["persisted"])
            self.assertEqual(read_chat_speech_settings(Path(str(self.path))), written)
            self.assertEqual(written["settings"], desired)
            self.assertTrue(self.path.read_bytes().startswith(self.before))

    def test_conflict_and_invalid_settings_do_not_write(self):
        initial = read_chat_speech_settings(self.path)
        update_chat_speech_settings(self.path, dict(CHAT_SPEECH_DEFAULTS, policy="brief"), initial["revision"])
        before = self.path.read_bytes()
        for desired, revision in [(CHAT_SPEECH_DEFAULTS, initial["revision"]),
                                  (dict(CHAT_SPEECH_DEFAULTS, locale="fr-FR"), read_chat_speech_settings(self.path)["revision"]),
                                  (dict(CHAT_SPEECH_DEFAULTS, route="legacy_bridge", locale="en-US"), read_chat_speech_settings(self.path)["revision"])]:
            with self.assertRaises(ValueError): update_chat_speech_settings(self.path, desired, revision)
            self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_failure_keeps_original(self):
        first = read_chat_speech_settings(self.path)
        with patch("kuro_launcher.config.os.replace", side_effect=PermissionError("fixture")):
            with self.assertRaises(PermissionError):
                update_chat_speech_settings(self.path, CHAT_SPEECH_DEFAULTS, first["revision"])
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(list(self.path.parent.glob(".chat-speech-*")), [])

    def test_rollback_round_trip(self):
        first = read_chat_speech_settings(self.path)
        result = update_chat_speech_settings(self.path, dict(CHAT_SPEECH_DEFAULTS, route="legacy_bridge"), first["revision"])
        self.assertEqual(result["settings"]["route"], "legacy_bridge")


class FixtureLLM(AsyncLLM):
    def __init__(self, turns):
        self.turns, self.calls = turns, []  # Never initialize an OpenAI client.

    async def chat_completion(self, messages, system=None, tools=None):
        self.calls.append(dict(messages=copy.deepcopy(messages), system=system, tools=tools))
        for item in self.turns[len(self.calls) - 1]:
            if isinstance(item, BaseException): raise item
            yield item


class SendFixture:
    def __init__(self): self.events = []
    async def __call__(self, raw): self.events.append(json.loads(raw))
    async def wait_for_playback(self): return True


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".tmp"); self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name) / "launcher.yaml"; self.settings.write_text("fixture: true\n", encoding="utf-8")
        self.live2d = SimpleNamespace(extract_emotion=lambda _: [])
        self.tts = SimpleNamespace(async_generate_audio=AsyncMock(return_value="fixture.wav"), remove_file=Mock())
        self.send = SendFixture()
        self.stores, self.memories = Mock(return_value={}), Mock(return_value=(False, []))
        def payload(audio_path, display_text, actions):
            return {"type": "audio", "audio": "synthetic-audio" if audio_path else None, "display_text": display_text.to_dict()}
        self.patches = [patch.dict(os.environ, {"KURO_LAUNCHER_SETTINGS_FILE": str(self.settings)}),
                        patch("open_llm_vtuber.conversations.single_conversation._load_tts_pronunciation_entries", return_value=[]),
                        patch("open_llm_vtuber.conversations.single_conversation._load_speech_style_prompt", return_value=""),
                        patch("open_llm_vtuber.conversations.single_conversation.store_message", self.stores),
                        patch("open_llm_vtuber.conversations.single_conversation.finish_pending_turns", self.memories),
                        patch("open_llm_vtuber.conversations.single_conversation.BridgeSpeechEngine._post_json", side_effect=AssertionError("unexpected Bridge IO")),
                        patch("open_llm_vtuber.conversations.tts_manager.prepare_audio_payload", side_effect=payload)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)

    def context(self, turns, tools=False):
        llm = FixtureLLM(turns)
        manager = Mock(); manager.get_formatted_tools.return_value = [{"type": "function"}]; manager.get_last_route.return_value = None
        manager.get_last_route_prompt.return_value = ""
        from contextlib import nullcontext
        executor = Mock()
        executor.turn_session.side_effect = nullcontext
        agent = BasicMemoryAgent(llm, "fixture display policy", self.live2d, use_mcpp=tools,
                                 tool_manager=manager if tools else None, tool_executor=executor if tools else None,
                                 tts_preprocessor_config=SimpleNamespace(remove_special_char=False, ignore_brackets=True,
                                     ignore_parentheses=True, ignore_asterisks=True, ignore_angle_brackets=True),
                                 segment_method="regex")
        return SimpleNamespace(agent_engine=agent, character_config=SimpleNamespace(character_name="Fixture", avatar="", human_name="User", conf_uid="fixture"),
                               asr_engine=SimpleNamespace(async_transcribe_np=AsyncMock(return_value="中文 and English 日本語")),
                               history_uid="fixture-history", live2d_model=self.live2d, tts_engine=self.tts), llm, executor

    async def run_turn(self, context, text="中文 and English 日本語"):
        return await process_single_conversation(context, self.send, "fixture", text, session_emoji="fixture")

    async def test_failed_history_write_preserves_completed_display(self):
        self.stores.side_effect=[{},OSError("fixture unavailable")]
        display="仍可讀取這個回覆。"
        context,_,_=self.context([list(display+footer())])
        self.assertEqual(await self.run_turn(context),display)
        self.memories.assert_not_called()
        self.assertTrue(any("歷史保存失敗" in e.get("message","") for e in self.send.events))

    async def test_one_sequence_zero_bridge_complete_display_history_memory(self):
        display = '尚未驗證。價格100.5、停損95；stale。\n```python\nx = {"a": 1}\n```\n|欄位|值|\nhttps://example.test'
        raw = display + footer()
        context, llm, _ = self.context([list(raw)])
        result = await self.run_turn(context)
        self.assertEqual(result, display)
        self.assertEqual(len(llm.calls), 1)
        self.assertGreater(self.tts.async_generate_audio.await_count, 0)
        self.assertEqual(llm.calls[0]["messages"][-1]["content"][0]["text"], "中文 and English 日本語")
        self.assertEqual(context.agent_engine._memory[-1]["content"], display)
        self.assertEqual(self.stores.call_args.kwargs["content"], display)
        self.assertEqual(self.memories.call_args.args[3]["assistant_text"], display)
        visible = "".join(v.get("display_text", {}).get("text", "") for v in self.send.events)
        self.assertEqual(visible, display)
        self.assertNotIn("KURO_SPEECH", json.dumps(self.send.events))
        self.assertNotIn("損切り", json.dumps(self.send.events, ensure_ascii=False))

    async def test_long_single_character_stream_coalesces_but_still_progresses(self):
        display = "技術回答與限制內容" * 1500  # 13500 one-character chunks.
        context, llm, _ = self.context([list(display + footer())])
        result = await self.run_turn(context)
        display_events = [e for e in self.send.events if e.get("display_text", {}).get("text")]
        self.assertEqual(result, display)
        self.assertEqual("".join(e["display_text"]["text"] for e in display_events), display)
        self.assertGreater(len(display_events), 1)
        self.assertLessEqual(len(display_events), len(display) // 100)
        print(json.dumps({"fixture": "long_token_stream", "input_chunks": len(display), "display_ws_payloads": len(display_events), "bridge_requests": 0}))

    async def test_literal_footer_example_survives_actual_chat_history_memory(self):
        display = "技術文件\n```text\n<<<KURO_SPEECH_V1>>>\nJSON example\n```\n後續文字也保留。"
        context, _, _ = self.context([list(display + footer())])
        self.assertEqual(await self.run_turn(context), display)
        self.assertEqual(self.memories.call_args.args[3]["assistant_text"], display)
        self.assertEqual(context.agent_engine._memory[-1]["content"], display)

    async def test_multilingual_text_and_asr_are_passed_through(self):
        import numpy as np
        for text in ["請說明限制", "Explain the limits", "制限を教えて", "stale 資料を explain"]:
            context, llm, _ = self.context([["好的。" + footer("承知しました。")]])
            await self.run_turn(context, text)
            self.assertEqual(llm.calls[0]["messages"][-1]["content"][0]["text"], text)
        context, llm, _ = self.context([["好的。" + footer("承知しました。")]])
        await self.run_turn(context, np.zeros(160, dtype=np.float32))
        self.assertEqual(llm.calls[0]["messages"][-1]["content"][0]["text"], "中文 and English 日本語")

    async def test_settings_next_turn_all_policies_and_unverified_locale(self):
        context, llm, _ = self.context([["結論。" + footer("確認しました。", policy=p)] for p in ["brief", "summary", "detailed"]])
        for policy in ["brief", "summary", "detailed"]:
            first = read_chat_speech_settings(self.settings)
            update_chat_speech_settings(self.settings, dict(CHAT_SPEECH_DEFAULTS, policy=policy), first["revision"])
            await self.run_turn(context)
            self.assertIn(f"Speech policy is {policy}", llm.calls[-1]["system"])
        first = read_chat_speech_settings(self.settings)
        update_chat_speech_settings(self.settings, dict(CHAT_SPEECH_DEFAULTS, locale="en-US"), first["revision"])
        context, llm, _ = self.context([["完整文字。" + footer("Unverified result.", locale="en-US")]])
        self.tts.async_generate_audio.reset_mock()
        self.assertEqual(await self.run_turn(context), "完整文字。")
        self.assertIn("Speech locale is en-US", llm.calls[0]["system"])
        self.tts.async_generate_audio.assert_not_awaited()
        self.assertEqual(self.send.events[-3]["reason"], "locale_voice_unverified")

    async def test_tool_loop_never_speaks_interim_claim_and_preserves_arguments_status(self):
        tc = ToolCallObject(id="fixture-call", function=ToolCallFunctionObject(name="fixture_read", arguments='{"query":"中文 日本語 code"}'))
        context, llm, executor = self.context([["工具前文字。" + footer("成功しました。"), [tc]], ["工具失敗，資料仍 unknown。" + footer("失敗しました。データは不明です。")]], tools=True)
        async def execute(**kwargs):
            self.tts.async_generate_audio.assert_not_awaited()
            self.assertEqual(kwargs["tool_calls"][0].function.arguments, tc.function.arguments)
            yield {"type": "tool_call_status", "status": "failed", "tool_name": "fixture_read", "content": "fixture failure"}
            yield {"type": "final_tool_results", "results": [{"role": "tool", "tool_call_id": "fixture-call", "content": "failed; unknown"}]}
        executor.execute_tools = execute
        with patch("open_llm_vtuber.conversations.single_conversation._store_tool_status_event"):
            result = await self.run_turn(context)
        self.assertEqual(result, "工具前文字。工具失敗，資料仍 unknown。")
        self.assertEqual(len(llm.calls), 2)  # One conversation sequence, required tool continuation.
        self.assertEqual(llm.calls[1]["messages"][-1]["role"], "tool")
        self.assertEqual("".join(call.kwargs["text"] for call in self.tts.async_generate_audio.await_args_list), "失敗しました。データは不明です。")
        self.assertTrue(any(e["type"] == "tool_call_status" for e in self.send.events))
        self.assertTrue(all("KURO_SPEECH" not in m["content"] for m in context.agent_engine._memory))

    async def test_missing_malformed_technical_empty_or_stream_error_is_silent(self):
        cases = [["完整文字 {broken"], ["完整文字" + SPEECH_LANE_MARKER + "{broken"],
                 ["完整文字" + footer("URLはhttps://example.testです。")], ["完整文字" + footer("")],
                 ["完整文字" + footer(), RuntimeError("fixture failure")]]
        for chunks in cases:
            self.tts.async_generate_audio.reset_mock()
            context, llm, _ = self.context([chunks])
            result = await self.run_turn(context)
            self.assertTrue(result.startswith("完整文字"))
            self.tts.async_generate_audio.assert_not_awaited()
            self.assertEqual(len(llm.calls), 1 if any(isinstance(c, Exception) for c in chunks) else 2)

    async def test_voice_unavailable_keeps_text_and_completes(self):
        self.tts.async_generate_audio.return_value = None
        context, _, _ = self.context([["完整文字。" + footer("本文を確認しましょう。")]])
        self.assertEqual(await self.run_turn(context), "完整文字。")
        self.assertTrue(any(e.get("speech_status") == "unavailable" for e in self.send.events))
        self.assertEqual(self.send.events[-1]["text"], "conversation-chain-end")

    async def test_missing_voice_engine_and_invalid_yaml_stay_display_only(self):
        for mode in ["engine_missing", "invalid_settings"]:
            context, llm, _ = self.context([["完整文字。" + footer()]])
            if mode == "engine_missing": context.tts_engine = None
            else: self.settings.write_text("malformed: [\n", encoding="utf-8")
            self.assertEqual(await self.run_turn(context), "完整文字。")
            self.assertEqual(len(llm.calls), 1)
            self.tts.async_generate_audio.assert_not_awaited()

    async def test_explicit_rollback_uses_old_renderer_with_one_request(self):
        first = read_chat_speech_settings(self.settings)
        update_chat_speech_settings(self.settings, dict(CHAT_SPEECH_DEFAULTS, route="legacy_bridge"), first["revision"])
        context, llm, _ = self.context([["你好。"]])
        with patch("open_llm_vtuber.conversations.single_conversation.BridgeSpeechEngine._post_json",
                   return_value={"data":"こんにちは。", "emotion":"joy", "provider":"fixture:render_spoken"}) as post:
            self.assertEqual(await self.run_turn(context), "你好。")
        self.assertEqual(post.call_count, 1)
        self.assertNotIn("Runtime output contract: kuro.speech-lanes.v1", llm.calls[0]["system"])
        self.assertEqual(self.tts.async_generate_audio.await_args.kwargs["text"], "こんにちは。")

    async def test_cancel_during_stream_no_voice_or_history_answer(self):
        context, _, _ = self.context([[]]); entered = asyncio.Event()
        async def stream(*args, **kwargs):
            yield "部分回答。"
            entered.set(); await asyncio.Event().wait()
        context.agent_engine._llm.chat_completion = stream
        task = asyncio.create_task(self.run_turn(context))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.tts.async_generate_audio.assert_not_awaited()
        self.assertEqual(self.stores.call_count, 1)  # User only.

    async def test_unsupported_tool_api_does_not_retry_or_change_provider(self):
        context, llm, _ = self.context([["__API_NOT_SUPPORT_TOOLS__"]], tools=True)
        self.assertIn("未執行工具", await self.run_turn(context))
        self.assertEqual(len(llm.calls), 1)
        self.assertFalse(context.agent_engine.prompt_mode_flag)
        self.tts.async_generate_audio.assert_not_awaited()

    async def test_cancel_clears_pending_tts_task(self):
        manager = TTSTaskManager(); entered = asyncio.Event()
        async def blocked(*args, **kwargs): entered.set(); await asyncio.Event().wait()
        self.tts.async_generate_audio.side_effect = blocked
        await manager.speak("確認しました。", DisplayText(""), None, self.live2d, self.tts, self.send)
        await asyncio.wait_for(entered.wait(), 1)
        tasks = list(manager.task_list); manager.clear()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertTrue(all(task.cancelled() for task in tasks))

    async def test_pronunciation_is_japanese_only_and_does_not_change_display(self):
        with patch("open_llm_vtuber.conversations.single_conversation._load_tts_pronunciation_entries", return_value=[{"surface": "LLM", "reading": "エルエルエム", "aliases": []}]):
            context, _, _ = self.context([["LLM 未驗證。" + footer("LLMは未検証です。")]])
            self.assertEqual(await self.run_turn(context), "LLM 未驗證。")
        self.assertIn("エルエルエム", self.tts.async_generate_audio.await_args.kwargs["text"])

    async def test_long_speech_chunks_keep_one_complete_chat_history_and_tool_result(self):
        display = '完整回答：價格100.5、停損95，工具失敗，尚未驗證，資料可能過期。\n```python\nprint(1)\n```'
        spoken = '価格は100.5です。損切りは95です。操作は失敗しました。未検証です。成功したとは言えません。データは古い可能性があります。確認が必要です。追加の注文はしません。'
        tc = ToolCallObject(id='fixture-call', function=ToolCallFunctionObject(name='fixture_read', arguments='{}'))
        context, llm, executor = self.context([[[tc]], [display + footer(spoken)]], tools=True)
        async def execute(**kwargs):
            self.tts.async_generate_audio.assert_not_awaited()
            yield {'type': 'tool_call_status', 'status': 'failed', 'tool_name': 'fixture_read', 'content': 'fixture failure'}
            yield {'type': 'final_tool_results', 'results': [{'role': 'tool', 'tool_call_id': 'fixture-call', 'content': 'failed; unknown'}]}
        executor.execute_tools = execute
        with patch('open_llm_vtuber.conversations.single_conversation._store_tool_status_event'):
            result = await self.run_turn(context)
        self.assertEqual(result, display)
        self.assertEqual(len(llm.calls), 2)  # Existing tool continuation, no speech LLM.
        self.assertEqual(sum(call.kwargs.get('role') == 'ai' for call in self.stores.call_args_list), 1)
        self.assertEqual(self.stores.call_args.kwargs['content'], display)
        self.assertEqual(context.agent_engine._memory[-1]['content'], display)
        self.assertEqual(''.join(call.kwargs['text'] for call in self.tts.async_generate_audio.await_args_list), spoken)
        self.assertEqual(self.tts.async_generate_audio.await_count, len(spoken.split("。")) - 1)
        self.assertTrue(any(event['type'] == 'tool_call_status' for event in self.send.events))

    async def test_first_chunk_unavailable_keeps_full_chat_history_and_final_ack(self):
        display = '完整回答：價格100.5、停損95，未驗證。資料可能過期。'
        spoken = '未検証です。価格は100.5です。損切りは95です。成功ではありません。データは古い可能性があります。確認が必要です。'
        self.tts.async_generate_audio.return_value = None
        context, llm, _ = self.context([[display + footer(spoken)]])
        self.assertEqual(await self.run_turn(context), display)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(self.tts.async_generate_audio.await_count, len(spoken.split("。")) - 1)
        self.assertEqual(sum(call.kwargs.get('role') == 'ai' for call in self.stores.call_args_list), 1)
        self.assertEqual(self.stores.call_args.kwargs['content'], display)
        self.assertEqual(context.agent_engine._memory[-1]['content'], display)
        self.assertFalse(any(event.get('audio') for event in self.send.events))
        self.assertIn({'type': 'backend-synth-complete'}, self.send.events)


class RollbackTests(unittest.TestCase):
    def test_legacy_bridge_budget_is_one_render_request(self):
        engine = BridgeSpeechEngine()
        with patch.object(engine, "_post_json", return_value={"data": "確認しました。", "emotion": "neutral"}) as post:
            self.assertTrue(engine.translate("fixture"))
            self.assertEqual(engine.translate("second"), "")
        self.assertEqual(post.call_count, 1)

    def test_formal_start_llm_environment_imports_launcher_in_child_cwd(self):
        from kuro_launcher.services import start_llm
        cfg = SimpleNamespace(env_llm=ROOT / "envs/kuro-llm310", config_path=ROOT / "kuro_launcher.settings.yaml",
                              runtime_conf_path=ROOT / ".tmp/unused-fixture.yaml", open_llm_dir=ROOT / "Open-LLM-VTuber", root=ROOT)
        def probe(name, command, cwd, logs_root, **kwargs):
            self.assertEqual(name, "llm")
            self.assertEqual(Path(cwd), cfg.open_llm_dir)
            env = kwargs["env"]
            self.assertEqual(env["KURO_LAUNCHER_SETTINGS_FILE"], str(cfg.config_path.resolve()))
            code = "import json,os; import kuro_launcher.config as c; print(json.dumps({'module':c.__file__,'cwd':os.getcwd()}))"
            process = subprocess.run([command[0], "-B", "-c", code], cwd=cwd, env=env,
                                     capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(Path(result["module"]).resolve(), ROOT / "kuro_launcher/config.py")
            self.assertEqual(Path(result["cwd"]), cfg.open_llm_dir)
            print(json.dumps({"fixture":"formal_start_llm_child_import", **result}))
            return SimpleNamespace(combined_path="synthetic-no-runtime-started")
        with patch("kuro_launcher.services._probe_llm_import"), patch("kuro_launcher.services.spawn_process", side_effect=probe):
            start_llm(cfg, lambda _: None, logs_root=ROOT / ".tmp", run_id="fixture")


if __name__ == "__main__": unittest.main()
