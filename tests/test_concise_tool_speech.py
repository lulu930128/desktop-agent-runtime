"""Regression of the actual speech pipeline; all external IO is synthetic."""
import asyncio
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import test_speech_semantic_alignment as semantic
from test_central_voice_client import health_response, audio_response
from open_llm_vtuber.conversations import speech_recovery as recovery
from open_llm_vtuber.tts import gpt_sovits_tts as central
from open_llm_vtuber.utils import stream_audio
from pydub import AudioSegment


class ConciseSemantics(unittest.TestCase):
    def test_natural_status_paraphrases_are_not_contradictions(self):
        for source, text in [('尚未驗證', 'まだ検証していません。'),
                             ('資料不完整', 'データはまだ揃っていません。'),
                             ('可以稍後等待', '少し待ってください。')]:
            value = semantic.lane([semantic.anchor('a', source, 'option' if '等待' in source else 'status')],
                                  [semantic.segment(text, 'a')])
            result = semantic.SemanticParserTests().parse(source, value)
            self.assertIn(result['state'], {'ready', 'semantic_unverified'})
            self.assertEqual(result['text'], text)

    def test_negated_error_is_not_an_actual_failure(self):
        from open_llm_vtuber.conversations.speech_presentation import _semantic_flags
        self.assertFalse(_semantic_flags('不是權限拒絕'))
        self.assertFalse(_semantic_flags('エラーはありません。'))

    def test_summary_may_omit_incidental_number_but_cannot_invent_one(self):
        display = '等待10分鐘後可以檢查'
        value = semantic.lane([semantic.anchor('a', display, 'fact')],
                              [semantic.segment('しばらく待ってから確認できます。', 'a')])
        self.assertEqual(semantic.SemanticParserTests().parse(display, value)['state'], 'ready')
        value['speech'][0]['text'] = '20分待ってから確認できます。'
        self.assertEqual(semantic.SemanticParserTests().parse(display, value)['state'], 'unbacked_value')
        value['anchors'][0]['importance'] = 'display_only'
        self.assertEqual(semantic.SemanticParserTests().parse(display, value)['state'], 'unbacked_value')

    def test_summary_can_leave_incidental_measurements_in_display(self):
        display = '服務已啟動。參考價格100.5，詳細數據列於畫面。'
        value = semantic.lane([semantic.anchor('a', '服務已啟動', 'fact')],
                              [semantic.segment('サービスが起動しました。詳しい数字は画面にあります。', 'a')])
        self.assertEqual(semantic.SemanticParserTests().parse(display, value)['state'], 'ready')

    def test_full_display_caveat_does_not_mute_equivalent_summary(self):
        display = '已讀取快取，但無法確認整體是否最新。不能將資料庫時間當成全部資料的截止日。'
        value = semantic.lane([semantic.anchor('a', '已讀取快取，但無法確認整體是否最新')],
                              [semantic.segment('キャッシュは読めましたが、全体が最新かはまだ確認できていません。', 'a')])
        self.assertEqual(semantic.SemanticParserTests().parse(display, value)['state'], 'semantic_unverified')


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_lane_has_no_extra_request(self):
        agent = Mock()
        original = {'state': 'ready', 'text': '確認しました。'}
        result = await recovery.recover_speech_lane(original, display='已確認', settings=semantic.v1.CHAT_SPEECH_DEFAULTS,
                                                   agent=agent, metrics={}, send=AsyncMock())
        self.assertIs(result, original)
        agent.render_speech_only.assert_not_called()

    async def test_missing_or_rejected_lane_repair_is_once_and_validated(self):
        display = '尚未驗證，詳細程式留在畫面。'
        value = semantic.lane([semantic.anchor('a', '尚未驗證')],
                              [semantic.segment('まだ検証していません。詳しいコードは画面にあります。', 'a')])
        calls = []
        class Agent:
            async def render_speech_only(self, source, prompt):
                calls.append((source, prompt))
                yield json.dumps(value, ensure_ascii=False)
        for state in ['missing', 'malformed', 'technical_payload', 'anchor_status_mismatch']:
            calls.clear(); metrics = {}
            result = await recovery.recover_speech_lane({'state': state, 'text': ''}, display=display,
                settings=semantic.v1.CHAT_SPEECH_DEFAULTS, agent=Agent(), metrics=metrics, send=AsyncMock())
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], display)
            self.assertEqual(metrics['repair_requests'], 1)
            self.assertIn(result['state'], {'ready', 'semantic_unverified'})
            self.assertNotIn('http', result['text'])
        value['speech'][0]['text'] = '確認しました。'
        original = {'state': 'missing', 'text': ''}
        result = await recovery.recover_speech_lane(original, display=display,
            settings=semantic.v1.CHAT_SPEECH_DEFAULTS, agent=Agent(), metrics={}, send=AsyncMock())
        self.assertIs(result, original)

    async def test_timeout_and_interrupt_close_stream_without_retry(self):
        entered = asyncio.Event(); closed = asyncio.Event(); calls = []
        class Agent:
            async def render_speech_only(self, *args):
                calls.append(1); entered.set()
                try:
                    await asyncio.Event().wait()
                    yield ''
                finally:
                    closed.set()
        async def run(metrics):
            return await recovery.recover_speech_lane(None, display='完整結論',
                settings=semantic.v1.CHAT_SPEECH_DEFAULTS, agent=Agent(), metrics=metrics, send=AsyncMock())
        metrics = {}
        async def timed_out(*args):
            try:
                raise asyncio.TimeoutError()
                yield ""
            finally:
                closed.set()
        with patch.object(Agent, "render_speech_only", timed_out):
            self.assertIsNone(await run(metrics))
        self.assertEqual(metrics['repair_state'], 'timeout'); self.assertTrue(closed.is_set())
        closed.clear(); entered.clear()
        task = asyncio.create_task(run({})); await entered.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(closed.is_set()); self.assertEqual(len(calls), 1)


class BusyRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_confirmed_busy_retries_and_cancel_stops_wait(self):
        engine = central.TTSEngine(voice_id='kuro')
        with patch.object(engine, '_generate_attempt', side_effect=[central.CentralVoiceBusy(), 'fixture.wav']) as generate, \
             patch.object(central, 'CENTRAL_BUSY_RECHECK_SECONDS', .001):
            self.assertEqual(await engine.async_generate_audio('same utterance'), 'fixture.wav')
            self.assertEqual(generate.call_count, 2)
        with patch.object(engine, '_generate_attempt', return_value=None) as generate:
            self.assertIsNone(await engine.async_generate_audio('unknown timeout'))
            generate.assert_called_once()
        with patch.object(engine, '_generate_attempt', side_effect=central.CentralVoiceBusy) as generate, \
             patch.object(central, 'CENTRAL_BUSY_RECHECK_SECONDS', .001):
            self.assertIsNone(await engine.async_generate_audio('busy'))
            self.assertEqual(generate.call_count, 3)
        reached = asyncio.Event()
        async def wait(_): reached.set(); await asyncio.Event().wait()
        with patch.object(engine, '_generate_attempt', side_effect=central.CentralVoiceBusy) as generate, \
             patch.object(central.asyncio, 'sleep', wait):
            task = asyncio.create_task(engine.async_generate_audio('cancel'))
            await reached.wait(); task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            generate.assert_called_once()


class AudioPreparationTests(unittest.TestCase):
    def test_lip_sync_failure_does_not_drop_valid_audio(self):
        audio = AudioSegment(data=b'\x00\x10' * 3200, sample_width=2, frame_rate=32000, channels=1)
        with patch.object(stream_audio.AudioSegment, 'from_file', return_value=audio), \
             patch.object(stream_audio, '_get_volume_by_chunks', side_effect=RuntimeError('envelope')):
            result = stream_audio.prepare_audio_payload('fixture.wav')
        self.assertTrue(result['audio']); self.assertEqual(result['volumes'], [])

    def test_silent_audio_still_rejected(self):
        with patch.object(stream_audio.AudioSegment, 'from_file', return_value=AudioSegment.silent(100)):
            with self.assertRaises(ValueError): stream_audio.prepare_audio_payload('fixture.wav')


if __name__ == '__main__':
    unittest.main()
