"""Synthetic long inventories through the real parser/conversation/TTS queue."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'Open-LLM-VTuber/src'), str(ROOT / 'Open-LLM-VTuber')]
import test_multilingual_speech as fixtures
from open_llm_vtuber.conversations.speech_presentation import (
    SpeechLaneParser, SPEECH_LANE_V2_MARKER, SPEECH_POLICY_DETAIL_ITEMS_JA,
)

DISPLAY = '工具清單與技術說明如下。\n\n' + ''.join(
    f'- `fixture_tool_{chr(97 + i)}`：讀取匿名資料並保留來源；詳細欄位與參數、回傳格式、呼叫方式與用途請看畫面。\n'
    for i in range(20))
SPOKEN = 'ツールの一覧を画面にまとめました。用途や引数の詳しい説明は画面で確認できます。'
LANE = dict(contract='kuro.speech-lanes.v2', locale='ja-JP', policy='summary',
            anchors=[dict(id='inventory', source='工具清單與技術說明如下。', importance='required', kind='fact')],
            speech=[dict(source_ids=['inventory'], text=SPOKEN)], emotion='neutral')
FOOTER = SPEECH_LANE_V2_MARKER + '\n' + json.dumps(LANE, ensure_ascii=False)


class InventoryParserTests(unittest.TestCase):
    def test_missing_reproduction_keeps_full_display_and_explicit_missing(self):
        parser = SpeechLaneParser()
        self.assertEqual(parser.feed(DISPLAY) + parser.finish_display(), DISPLAY)
        self.assertEqual(parser.result(fixtures.CHAT_SPEECH_DEFAULTS)['state'], 'missing')

    def test_v2_ready_short_japanese_with_hidden_anchors_at_every_boundary(self):
        raw = DISPLAY + FOOTER
        for split in range(len(raw) + 1):
            parser = SpeechLaneParser()
            visible = parser.feed(raw[:split]) + parser.feed(raw[split:]) + parser.finish_display()
            self.assertEqual(visible, DISPLAY)
            result = parser.result(fixtures.CHAT_SPEECH_DEFAULTS)
            self.assertEqual(result['state'], 'ready')
            self.assertEqual(result['text'], SPOKEN)
            self.assertLess(len(result['text']), 120)

    def test_primary_prompt_requires_current_private_v2_schema(self):
        response = (ROOT / 'Open-LLM-VTuber/prompts/utils/response_contract_prompt.txt').read_text(encoding='utf-8')
        self.assertNotIn('kuro.speech-lanes.v1', response)
        self.assertIn('kuro.speech-lanes.v2', response)
        self.assertIn('anchors', response)
        self.assertIn('speech', response)


class InventoryConversationTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.ConversationTests.setUp
    context = fixtures.ConversationTests.context
    run_turn = fixtures.ConversationTests.run_turn

    async def test_complete_inventory_uses_one_llm_short_tts_and_one_display(self):
        context, llm, _ = self.context([list(DISPLAY + FOOTER)])
        context.agent_engine._system = (ROOT / 'Open-LLM-VTuber/prompts/utils/response_contract_prompt.txt').read_text(encoding='utf-8')
        self.assertEqual(await self.run_turn(context, '列出匿名工具'), DISPLAY)
        self.assertEqual(len(llm.calls), 1)
        self.assertNotIn('kuro.speech-lanes.v1', llm.calls[0]['system'])
        self.assertIn('Speech locale is ja-JP', llm.calls[0]['system'])
        self.tts.async_generate_audio.assert_awaited_once()
        self.assertEqual(self.tts.async_generate_audio.await_args.kwargs['text'], SPOKEN)
        self.assertEqual(''.join(e.get('display_text', {}).get('text', '') for e in self.send.events), DISPLAY)
        self.assertEqual(self.stores.call_args.kwargs['content'], DISPLAY)
        self.assertEqual(self.memories.call_args.kwargs['assistant_text'], DISPLAY)
        self.assertNotIn('KURO_SPEECH', json.dumps(self.send.events))

    async def test_missing_complete_long_list_only_queues_honest_screen_ack(self):
        context, llm, _ = self.context([list(DISPLAY)])
        with patch('open_llm_vtuber.conversations.single_conversation.logger') as log:
            self.assertEqual(await self.run_turn(context), DISPLAY)
        self.assertEqual(len(llm.calls), 2)
        self.tts.async_generate_audio.assert_awaited_once()
        self.assertEqual(self.tts.async_generate_audio.await_args.kwargs['text'], SPEECH_POLICY_DETAIL_ITEMS_JA)
        self.assertEqual(''.join(e.get('display_text', {}).get('text', '') for e in self.send.events), DISPLAY)
        status = [e for e in self.send.events if e.get('type') == 'speech-status']
        self.assertTrue(any(e.get('reason') == 'missing' and e.get('delivery') == 'display_acknowledgment' for e in status))
        metrics = [c.args[1] for c in log.info.call_args_list if c.args[0] == 'speech_timing {}'][0]
        self.assertEqual(json.loads(metrics)['lane_state'], 'missing')

    async def test_malformed_rejected_empty_short_and_incomplete_stay_silent(self):
        for chunks in ([DISPLAY + SPEECH_LANE_V2_MARKER + '{broken'],
                       ['短い回答。'], [DISPLAY, RuntimeError('synthetic interrupted stream')],
                       [DISPLAY + SPEECH_LANE_V2_MARKER + '\n' + json.dumps(dict(LANE, speech=[]))]):
            self.tts.async_generate_audio.reset_mock()
            context, llm, _ = self.context([chunks])
            await self.run_turn(context)
            self.tts.async_generate_audio.assert_not_awaited()
            self.assertEqual(len(llm.calls), 1 if any(isinstance(c, Exception) for c in chunks) else 2)

    async def test_missing_long_prose_or_unverified_locale_never_uses_ack(self):
        context, _, _ = self.context([['匿名技術說明。' * 200]])
        await self.run_turn(context)
        self.tts.async_generate_audio.assert_not_awaited()
        first = fixtures.read_chat_speech_settings(self.settings)
        fixtures.update_chat_speech_settings(self.settings, dict(fixtures.CHAT_SPEECH_DEFAULTS, locale='en-US'), first['revision'])
        context, _, _ = self.context([[DISPLAY]])
        await self.run_turn(context)
        self.tts.async_generate_audio.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
