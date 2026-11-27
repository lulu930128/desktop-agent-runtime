"""Cold-start/first-chunk contracts. Only fixtures; no live LLM, models or services."""
import ast
import asyncio
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import launcher_qt  # Bootstrap the existing runtime imports.
from kuro_launcher import voice_client
from kuro_launcher.qt_controller import QtLauncherController
from open_llm_vtuber.agent.output_types import DisplayText
from open_llm_vtuber.conversations.conversation_utils import _natural_speech_chunks, queue_generated_speech, finalize_conversation_turn
from open_llm_vtuber.conversations.tts_manager import TTSTaskManager


ROOT = Path(__file__).resolve().parents[1]
SPOKEN = '結論は未検証です。価格は100.5です。損切りは95です。成功したとは言えません。データは古い可能性があります。確認が必要です。追加の注文はしません。'


class PreloadHookTests(unittest.TestCase):
    def test_profile_hooks_fire_once_per_successful_fresh_or_hot_start_not_polling(self):
        # Exercise the real lifecycle branch without creating processes or files.
        for hot in (False, True):
            with self.subTest(hot=hot):
                character = SimpleNamespace(yaml_path=Path('kuro.yaml'))
                cfg = SimpleNamespace(tts_mode='central', voice_ids=(('kuro', 'kuro'),),
                    voice_url='http://127.0.0.1:18890', bridge_host='fixture', bridge_port=1,
                    llm_host='fixture', llm_port=2, tts_host='fixture', tts_port=3, logs_dir=Path('.'), llm_url='fixture')
                controller = Mock(cfg=cfg, current_run_id='fixture', lifecycle=SimpleNamespace(voice={}))
                controller.selected_character.return_value = character
                controller.selected_project.return_value = Mock()
                controller._prepare_runtime_profile.return_value = ({}, {})
                controller._try_hot_switch_profile.return_value = True
                controller._wait_for_port_closed.return_value = (True, '')
                controller._wait_for_service_ready.return_value = (True, '')
                controller.launch_pet_electron.return_value = {}
                controller._apply_history_choice_after_start.return_value = {}
                controller._preload_profile_voice = lambda char: QtLauncherController._preload_profile_voice(controller, char)
                def port(host, number, *args):
                    return True if number == 1 else hot
                with patch('kuro_launcher.qt_controller.port_is_open', side_effect=port), \
                     patch('kuro_launcher.qt_controller.get_listening_pid_windows', return_value=None), \
                     patch('kuro_launcher.qt_controller.start_llm'), \
                     patch('kuro_launcher.voice_client.preload_async') as preload:
                    result = QtLauncherController._start_profile_impl(controller)
                    self.assertTrue(result['ok'])
                    preload.assert_called_once_with(cfg.voice_url, 'kuro', controller.log)
        tree = ast.parse((ROOT / 'kuro_launcher/qt_controller.py').read_text(encoding='utf-8-sig'))
        polling = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_check_voice_capability')
        self.assertNotIn('preload', ast.unparse(polling))

    def test_legacy_profile_never_preloads(self):
        with patch.object(voice_client, 'preload_async') as preload:
            QtLauncherController._preload_profile_voice(SimpleNamespace(cfg=SimpleNamespace(tts_mode='legacy')), Mock())
        preload.assert_not_called()

    def test_async_preload_returns_before_network_and_has_no_retry(self):
        entered, release = threading.Event(), threading.Event()
        log = Mock()
        def blocked(*args):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('fixture timeout')
            raise OSError('private model path')
        with patch.object(voice_client, 'preload', side_effect=blocked) as preload:
            worker = voice_client.preload_async('fixture', 'kuro', log)
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(worker.is_alive())
                log.assert_not_called()
            finally:
                release.set()
                worker.join(2)
            preload.assert_called_once()
        self.assertEqual(log.call_count, 1)
        self.assertNotIn('private', log.call_args.args[0])

    def test_preload_receipt_and_old_service_capability(self):
        health = dict(capabilities=['model_preload_v1'], service_version='fixture')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"voice":"kuro","state":"loading","request_id":"fixture"}'
        with patch.object(voice_client, 'require_voice', return_value=health), \
             patch.object(voice_client, '_open', return_value=response) as request:
            receipt, version = voice_client.preload('http://127.0.0.1:1', 'kuro')
        self.assertEqual((receipt['state'], version), ('loading', 'fixture'))
        self.assertEqual(request.call_args.args[0].full_url, 'http://127.0.0.1:1/preload')
        self.assertEqual(json.loads(request.call_args.args[0].data), {'voice': 'kuro'})
        with patch.object(voice_client, 'require_voice', return_value={}), patch.object(voice_client, '_open') as request:
            with self.assertRaisesRegex(RuntimeError, 'update required'):
                voice_client.preload('fixture', 'kuro')
        request.assert_not_called()

    def test_formal_qt_log_callback_queues_to_owner_thread(self):
        from PySide6.QtCore import QCoreApplication, QObject, Signal, Slot
        from kuro_launcher.qt_app import KuroQtLauncherWindow
        app = QCoreApplication.instance() or QCoreApplication([])
        owner_thread = threading.get_ident()
        received = []
        class Relay(QObject):
            log_signal = Signal(str)
            @Slot(str)
            def receive(self, text):
                received.append((threading.get_ident(), text))
        relay = Relay()
        relay.log_signal.connect(relay.receive)
        callback = lambda message: KuroQtLauncherWindow._append_log_threadsafe(relay, message)
        with patch.object(voice_client, 'preload', return_value=({'state': 'loading'}, 'fixture')):
            worker = voice_client.preload_async('fixture', 'kuro', callback)
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(received, [])
        app.processEvents()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], owner_thread)
        self.assertIn('state=loading', received[0][1])


class ChunkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = TTSTaskManager()
        self.addCleanup(self.manager.clear)
        self.events, self.calls = [], []
        self.release = asyncio.Event()
        self.first_sent = asyncio.Event()
        self.active = self.max_active = 0
        self.cleaned = []
        async def generate(text, **kwargs):
            self.calls.append(text)
            self.active += 1
            self.max_active = max(self.active, self.max_active)
            try:
                if len(self.calls) > 1:
                    await self.release.wait()
                return f'fixture-{len(self.calls)}.wav'
            finally:
                self.active -= 1
        self.engine = SimpleNamespace(async_generate_audio=generate, remove_file=self.cleaned.append)
        def payload(audio_path, display_text, actions):
            return {'type': 'audio', 'audio': audio_path, 'display_text': display_text.to_dict()}
        patcher = patch('open_llm_vtuber.conversations.tts_manager.prepare_audio_payload', side_effect=payload)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def send(self, raw):
        event = json.loads(raw)
        self.events.append(event)
        if event.get('audio'):
            self.first_sent.set()

    async def queue(self):
        await queue_generated_speech(lane={'state': 'ready', 'text': SPOKEN, 'emotion': 'neutral'},
            settings={'locale': 'ja-JP'}, tts_manager=self.manager, tts_engine=self.engine,
            live2d_model=Mock(), websocket_send=self.send)

    async def test_first_chunk_sent_before_rest_finishes_serial_order_and_timing(self):
        with patch('open_llm_vtuber.conversations.tts_manager.logger.info') as log:
            await self.queue()
            await asyncio.wait_for(self.first_sent.wait(), 1)
            self.assertEqual(self.events[-1]['audio'], 'fixture-1.wav')
            self.assertFalse(all(task.done() for task in self.manager.task_list))
            self.release.set()
            await asyncio.gather(*self.manager.task_list)
            await self.manager._payload_queue.join()
        self.assertEqual(self.max_active, 1)
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(self.calls[0], '結論は未検証です。')
        self.assertEqual(''.join(self.calls), SPOKEN)
        audio = [event for event in self.events if event.get('audio')]
        self.assertEqual([event['audio'] for event in audio], [f'fixture-{i}.wav' for i in range(1, 8)])
        self.assertTrue(all(event['display_text']['text'] == '' for event in audio))
        timings = [call for call in log.call_args_list if 'event=tts_complete' in call.args[0]]
        self.assertEqual(len(timings), 7)
        self.assertTrue(all(call.args[3] >= 0 for call in timings))

    async def test_cancel_discards_late_audio_cleans_cache_and_unsent_chunks(self):
        await self.queue()
        await asyncio.wait_for(self.first_sent.wait(), 1)
        # Wait until the second synthesis is in flight, then cancel all queued work.
        for _ in range(20):
            if len(self.calls) == 2:
                break
            await asyncio.sleep(0)
        self.assertEqual(len(self.calls), 2)
        tasks = list(self.manager.task_list)
        self.manager.clear()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.release.set()
        for _ in range(20):
            await asyncio.sleep(0)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([e['audio'] for e in self.events if e.get('audio')], ['fixture-1.wav'])
        self.assertEqual(self.cleaned, ['fixture-1.wav', 'fixture-2.wav'])
        self.assertTrue(self.manager._payload_queue.empty())

    async def test_failed_chunk_still_finishes_ordered_queue_and_completion_ack(self):
        self.release.set()
        calls = 0
        async def generate(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('fixture')
            return f'fixture-{calls}.wav'
        self.engine.async_generate_audio = generate
        await self.queue()
        await asyncio.gather(*self.manager.task_list)
        await self.manager._payload_queue.join()
        class Sender:
            async def __call__(other, raw):
                await self.send(raw)
            async def wait_for_playback(other):
                return True
        await asyncio.wait_for(finalize_conversation_turn(self.manager, Sender(), 'fixture'), 1)
        audio = [e for e in self.events if e['type'] == 'audio']
        self.assertEqual([e['speech_status'] for e in audio], ['available', 'unavailable'] + ['available'] * 5)
        self.assertEqual(calls, 7)
        self.assertTrue(any(e.get("status") == "partial" and e.get("missing_segments") == [2] for e in self.events))
        self.assertIn({'type': 'backend-synth-complete'}, self.events)
        self.assertEqual(self.events[-1], {'type': 'control', 'text': 'conversation-chain-end'})

    async def test_first_chunk_failure_stops_remaining_group_but_legacy_still_runs(self):
        async def failed(**kwargs):
            self.calls.append(kwargs['text'])
            raise RuntimeError('fixture first chunk')
        self.engine.async_generate_audio = failed
        await self.queue()
        await asyncio.gather(*self.manager.task_list)
        await self.manager._payload_queue.join()
        self.assertEqual(''.join(self.calls), SPOKEN)
        audio = [e for e in self.events if e['type'] == 'audio']
        self.assertEqual([e['speech_status'] for e in audio], ['unavailable'] * 7)
        self.assertFalse(any(e.get('audio') for e in audio))
        self.release.set()
        async def legacy(**kwargs):
            return 'legacy.wav'
        self.engine.async_generate_audio = legacy
        await self.manager.speak('別の単独発声です。', DisplayText(''), None, Mock(), self.engine, self.send)
        await asyncio.gather(*self.manager.task_list)
        await self.manager._payload_queue.join()
        self.assertEqual(self.events[-1]['audio'], 'legacy.wav')

    def test_sentence_boundaries_preserve_quotes_prices_and_negation(self):
        text = '「価格は100.5。買いではありません」と伝えました。損切りは95です。未検証です。古い可能性があります。失敗しました。再確認します。'
        chunks = _natural_speech_chunks(text)
        self.assertEqual(chunks[0], '「価格は100.5。買いではありません」と伝えました。')
        self.assertEqual(''.join(chunks), text)
        for text in ('短い返事です。', '「閉じていない。' * 10):
            self.assertEqual(_natural_speech_chunks(text), [text])
        long_clause = '句点なし' * 300
        self.assertGreater(len(_natural_speech_chunks(long_clause)), 1)
        self.assertEqual(''.join(_natural_speech_chunks(long_clause)), long_clause)
        numeric = '100.5。損切りは95です。未検証です。古い可能性があります。失敗しました。再確認します。'
        self.assertEqual(_natural_speech_chunks(numeric), [numeric])


if __name__ == '__main__':
    unittest.main()
