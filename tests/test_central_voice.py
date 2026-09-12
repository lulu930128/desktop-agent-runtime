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
        controller = SimpleNamespace(cfg=self.cfg(), current_run_id='test', log=Mock())
        controller.cfg.logs_dir = Path()
        with patch('kuro_launcher.qt_controller.probe_tts', return_value=(True, 'ok')) as probe, patch('kuro_launcher.qt_controller.start_tts') as start:
            self.assertTrue(LauncherController._restart_tts_runtime(controller, Mock(), {}))
            probe.assert_called_once()
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


if __name__ == '__main__':
    unittest.main()
