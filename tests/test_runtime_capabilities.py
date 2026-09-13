import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import launcher_qt
from kuro_launcher.runtime_lifecycle import RuntimeLifecycle
from kuro_launcher.presentation import presentation_descriptor
from kuro_launcher.qt_controller import QtLauncherController

ROOT = Path(__file__).resolve().parents[1]


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.state = RuntimeLifecycle(ROOT, Mock())

    def test_recovery_budget_does_not_reset_on_short_success(self):
        self.state.start(lambda: {'ok': True})
        for _ in range(2):
            self.state.start(lambda: {'ok': True}, automatic=True)
        operation = Mock()
        self.state.start(operation, automatic=True)
        operation.assert_not_called()
        self.assertTrue(self.state.snapshot()['recoveryExhausted'])
        self.state.desired_running = False
        self.state.start(operation, automatic=True)
        operation.assert_not_called()

    def test_failures_cool_down_and_manual_retry_resets_budget(self):
        with self.assertRaises(ValueError):
            self.state.start(lambda: (_ for _ in ()).throw(ValueError('fixture failure')))
        operation = Mock(return_value={'ok': True})
        self.state.start(operation, automatic=True)
        operation.assert_not_called()
        self.assertEqual(self.state.phase, 'failed')
        self.state.start(operation)
        operation.assert_called_once()

    def test_concurrent_start_is_coalesced(self):
        entered, release = threading.Event(), threading.Event()
        worker = threading.Thread(target=lambda: self.state.start(lambda: (entered.set(), release.wait(3))))
        worker.start()
        self.assertTrue(entered.wait(1))
        operation = Mock()
        try:
            self.assertTrue(self.state.start(operation)['pending'])
            operation.assert_not_called()
        finally:
            release.set()
            worker.join(3)

    def test_source_revision_reports_pending_adoption(self):
        self.state.disk_revision = 'changed'
        self.assertTrue(self.state.snapshot()['restartRequired'])

    def test_central_outage_does_not_block_llm_spawn(self):
        c = QtLauncherController.__new__(QtLauncherController)
        c.cfg = SimpleNamespace(bridge_host='localhost', bridge_port=1188, llm_host='localhost', llm_port=23456,
                               tts_host='localhost', tts_port=18890, tts_mode='central', logs_dir=ROOT / 'launcher_logs')
        c.lifecycle, c.log, c.current_run_id = self.state, Mock(), 'fixture'
        c.cfg.llm_url = 'http://localhost:23456'
        character = SimpleNamespace(yaml_path=Path('kuro.yaml'))
        c.selected_character, c.selected_project = Mock(return_value=character), Mock(return_value=object())
        c._prepare_runtime_profile = Mock(return_value=({}, {}))
        c.stop_profile = Mock()
        c._check_voice_capability = Mock(return_value=False)
        c._wait_for_port_closed = Mock(return_value=(True, 'closed'))
        c._wait_for_service_ready = Mock(return_value=(True, 'ready'))
        c.launch_pet_electron = Mock(return_value={'pid': 123, 'instanceId': 'fixture'})
        c.apply_outfit, c._apply_history_choice_after_start = Mock(), Mock(return_value={'ok': True})
        with patch('kuro_launcher.qt_controller.port_is_open', side_effect=[True, False]), patch('kuro_launcher.qt_controller.get_listening_pid_windows', return_value=None), patch('kuro_launcher.qt_controller.start_llm') as llm, patch('kuro_launcher.qt_controller.start_tts') as tts:
            self.assertTrue(c._start_profile_impl()['ok'])
            llm.assert_called_once()
            tts.assert_not_called()

    def test_model_path_must_stay_in_canonical_root(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'launcher_logs') as directory:
            root = Path(directory)
            (root / 'live2d-models').mkdir()
            character = SimpleNamespace(live2d_model_name='fixture', conf_uid='fixture', conf_name='fixture')
            (root / 'outside.model3.json').write_text('{}')
            (root / 'model_dict.json').write_text(json.dumps([{'name': 'fixture', 'url': '/live2d-models/../outside.model3.json'}]))
            with self.assertRaises(ValueError):
                presentation_descriptor(root, character)


class SpeechFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_silent_turn_delivers_text_and_never_waits_for_playback(self):
        from open_llm_vtuber.conversations.tts_manager import TTSTaskManager
        from open_llm_vtuber.conversations.conversation_utils import finalize_conversation_turn
        from open_llm_vtuber.agent.output_types import DisplayText
        manager = TTSTaskManager()
        send = AsyncMock()
        engine = SimpleNamespace(async_generate_audio=AsyncMock(return_value=None))
        try:
            await manager.speak('Hello', DisplayText(text='visible text', name='fixture', avatar=''), None, None, engine, send)
            with patch('open_llm_vtuber.conversations.conversation_utils.message_handler.wait_for_response', new_callable=AsyncMock) as wait:
                await asyncio.wait_for(finalize_conversation_turn(manager, send, 'fixture'), timeout=2)
                wait.assert_not_called()
            messages = [json.loads(call.args[0]) for call in send.call_args_list]
            self.assertEqual(messages[0]['display_text']['text'], 'visible text')
            self.assertEqual(messages[0]['speech_status'], 'unavailable')
            self.assertEqual(messages[-1]['text'], 'conversation-chain-end')
        finally:
            manager.clear()

    async def test_voice_outage_opens_circuit_without_resending_text(self):
        from open_llm_vtuber.tts.gpt_sovits_tts import TTSEngine
        import requests
        engine = TTSEngine(api_url='http://localhost:18890/tts', voice_id='fixture')
        with patch.object(engine, 'generate_cache_file_name', return_value='unused.wav'), patch('open_llm_vtuber.tts.gpt_sovits_tts.requests.get', side_effect=requests.ConnectionError) as health, patch('open_llm_vtuber.tts.gpt_sovits_tts.requests.post') as post:
            self.assertIsNone(engine.generate_audio('first'))
            self.assertIsNone(engine.generate_audio('second'))
            health.assert_called_once()
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
