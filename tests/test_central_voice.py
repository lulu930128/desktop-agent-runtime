import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from kuro_launcher.config import load_config
from kuro_launcher.services import start_tts, validate_profile_assets
import launcher_qt  # Bootstrap the vendored runtime import path.
from kuro_launcher.qt_controller import QtLauncherController as LauncherController


class CentralVoiceTests(unittest.TestCase):
    def cfg(self):
        return SimpleNamespace(tts_mode='central', voice_ids=(('kuro', 'kuro'),),
                               voice_url='http://127.0.0.1:18890', tts_port=18890)

    def test_start_requires_identity_and_never_spawns(self):
        with patch('kuro_launcher.voice_client.require_voice') as check, patch('kuro_launcher.services.spawn_process') as spawn:
            self.assertIsNone(start_tts(self.cfg(), Mock(), character_name='kuro', logs_root=Path(), run_id='test'))
            check.assert_called_once_with('http://127.0.0.1:18890', 'kuro')
            spawn.assert_not_called()

    def test_unavailable_does_not_fall_back_to_legacy(self):
        with patch('kuro_launcher.voice_client.require_voice', side_effect=RuntimeError('offline')), patch('kuro_launcher.services.spawn_process') as spawn:
            with self.assertRaises(RuntimeError):
                start_tts(self.cfg(), Mock(), character_name='kuro', logs_root=Path(), run_id='test')
            spawn.assert_not_called()

    def test_shared_stop_cannot_kill_port_owner(self):
        controller = SimpleNamespace(cfg=self.cfg(), proc_tts=Mock())
        with patch('kuro_launcher.qt_controller.taskkill_tree') as kill:
            LauncherController._stop_tts_impl(controller, kill_external=True)
            kill.assert_not_called()
            controller.proc_tts.stop.assert_not_called()

    def test_shared_profile_switch_only_probes(self):
        controller = SimpleNamespace(cfg=self.cfg(), current_run_id='test', log=Mock(), _check_voice_capability=Mock(return_value=False))
        controller.cfg.logs_dir = Path()
        with patch('kuro_launcher.qt_controller.probe_tts', return_value=(True, 'ok')) as probe, patch('kuro_launcher.qt_controller.start_tts') as start:
            self.assertTrue(LauncherController._restart_tts_runtime(controller, Mock(), {}))
            probe.assert_not_called()
            controller._check_voice_capability.assert_called_once()
            start.assert_not_called()

    def test_runtime_conf_has_voice_identity_without_reference(self):
        from kuro_launcher.runtime_conf import build_runtime_conf
        cfg = load_config(Path(__file__).resolve().parents[1] / 'kuro_launcher.settings.yaml')
        _, char = build_runtime_conf(open_llm_dir=cfg.open_llm_dir,
            character_yaml=cfg.characters_dir / 'kuro.yaml', project_yaml=None,
            llm_host=cfg.llm_host, llm_port=cfg.llm_port, bridge_translate_url=cfg.bridge_translate_url,
            tts_host='127.0.0.1', tts_port=18890, voice_id='kuro',
            **{k: getattr(cfg, k) for k in ('llm_provider_env', 'llm_default_provider', 'openai_model_env',
                'openai_default_model', 'openai_temp_env', 'openai_inject_key_env', 'openai_api_key_env', 'openai_fallback_key_env')})
        tts = char['tts_config']['gpt_sovits_tts']
        self.assertEqual(tts['voice_id'], 'kuro')
        self.assertEqual(tts['ref_audio_path'], '')
        self.assertEqual(tts['api_url'], 'http://127.0.0.1:18890/tts')

    def test_yumi_resolves_to_yuki_without_local_model_ownership(self):
        from kuro_launcher.runtime_conf import build_runtime_conf
        cfg = load_config(Path(__file__).resolve().parents[1] / 'kuro_launcher.settings.yaml')
        voice = dict(cfg.voice_ids)['yumi']
        self.assertEqual(voice, 'yuki')
        _, char = build_runtime_conf(open_llm_dir=cfg.open_llm_dir,
            character_yaml=cfg.characters_dir / 'yumi.yaml', project_yaml=None,
            llm_host=cfg.llm_host, llm_port=cfg.llm_port, bridge_translate_url=cfg.bridge_translate_url,
            tts_host='127.0.0.1', tts_port=18890, voice_id=voice,
            **{k: getattr(cfg, k) for k in ('llm_provider_env', 'llm_default_provider', 'openai_model_env',
                'openai_default_model', 'openai_temp_env', 'openai_inject_key_env', 'openai_api_key_env', 'openai_fallback_key_env')})
        tts = char['tts_config']['gpt_sovits_tts']
        self.assertEqual(tts['voice_id'], 'yuki')
        self.assertEqual(tts['ref_audio_path'], '')

    def test_readiness_requires_current_model_and_successful_inference(self):
        from kuro_launcher.voice_client import readiness
        for loaded, inference, status, expected in (
            (None, 'not_run', 'available', 'cold'),
            ('kuro', 'not_run', 'available', 'cold'),
            ('yuki', 'passed', 'available', 'cold'),
            ('kuro', 'passed', 'available', 'available'),
            ('kuro', 'passed', 'busy', 'busy'),
            (None, 'failed', 'available', 'unavailable'),
        ):
            with self.subTest(loaded=loaded, inference=inference, status=status):
                data = {'status': status, 'model_loaded': loaded,
                        'voices': [{'voice_id': 'kuro', 'last_inference': inference}]}
                with patch('kuro_launcher.voice_client.require_voice', return_value=data), \
                     patch('kuro_launcher.voice_client.synthesize') as synth:
                    result = readiness('http://127.0.0.1:18890', 'kuro')
                    self.assertEqual(result['state'], expected)
                    self.assertEqual(result['voiceId'], 'kuro')
                    synth.assert_not_called()

    def test_launcher_does_not_promote_cold_or_busy_voice_to_available(self):
        controller = SimpleNamespace(cfg=self.cfg(), lifecycle=SimpleNamespace(voice={}),
                                     selected_character=lambda: SimpleNamespace(yaml_path=Path('kuro.yaml')))
        for state in ('cold', 'busy', 'unavailable', 'available'):
            with self.subTest(state=state), patch('kuro_launcher.voice_client.readiness',
                                                  return_value={'state': state, 'reason': 'fixture'}):
                ready = LauncherController._check_voice_capability(controller)
                self.assertEqual(ready, state == 'available')
                self.assertEqual(controller.lifecycle.voice['state'], state)

    def test_launcher_reports_offline_and_recovers_on_next_probe(self):
        controller = SimpleNamespace(cfg=self.cfg(), lifecycle=SimpleNamespace(voice={}),
                                     selected_character=lambda: SimpleNamespace(yaml_path=Path('kuro.yaml')))
        with patch('kuro_launcher.voice_client.readiness',
                   side_effect=[OSError('offline'), {'state': 'available', 'reason': 'ready'}]):
            self.assertFalse(LauncherController._check_voice_capability(controller))
            self.assertEqual(controller.lifecycle.voice['state'], 'unavailable')
            self.assertTrue(LauncherController._check_voice_capability(controller))


if __name__ == '__main__':
    unittest.main()
