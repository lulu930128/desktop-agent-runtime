"""Consumer recovery contracts; no real model, network, or speech in unit tests."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

import requests

import launcher_qt  # Bootstrap the vendored runtime import path.
from open_llm_vtuber.tts import gpt_sovits_tts as client


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(32000)
        audio.writeframes(b'\x00\x01' * 640)
    return output.getvalue()


def health_response(status='available', model=None):
    return Mock(status_code=200, json=Mock(return_value={
        'service': 'voice-runtime', 'protocol_version': 1, 'status': status,
        'model_loaded': model, 'voices': [{'voice_id': 'kuro', 'last_inference': 'not_run'}],
    }))


def audio_response():
    return Mock(status_code=200, headers={'Content-Type': 'audio/wav'}, content=wav_bytes())


class CentralVoiceClientTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'launcher_logs')
        self.addCleanup(directory.cleanup)
        self.path = str(Path(directory.name) / 'audio.wav')
        self.engine = client.TTSEngine(api_url='http://127.0.0.1:18890/tts', voice_id='kuro', text_lang='ja')
        cache = patch.object(self.engine, 'generate_cache_file_name', return_value=self.path)
        self.addCleanup(cache.stop)
        cache.start()
        health = patch.object(client.requests, 'get', return_value=health_response())
        self.addCleanup(health.stop)
        self.health = health.start()
        post = patch.object(client.requests, 'post', return_value=audio_response())
        self.addCleanup(post.stop)
        self.post = post.start()

    def test_cold_and_warm_requests_allow_model_switch_during_discovery(self):
        for loaded in (None, 'kuro', 'yuki'):
            with self.subTest(model_loaded=loaded):
                self.health.return_value = health_response(model=loaded)
                self.assertEqual(self.engine.generate_audio('new utterance'), self.path)
                kwargs = self.post.call_args.kwargs
                self.assertEqual(kwargs['timeout'], (1, 180))
                self.assertFalse(kwargs['allow_redirects'])
                self.assertEqual(set(kwargs['json']), {'voice', 'text', 'language', 'speed_factor'})
                self.assertEqual(Path(self.path).read_bytes(), wav_bytes())

    def test_busy_health_does_not_cool_down_the_next_utterance(self):
        self.health.side_effect = [health_response(status='busy'), health_response()]
        self.assertIsNone(self.engine.generate_audio('busy utterance'))
        self.post.assert_not_called()
        self.assertEqual(self.engine.generate_audio('next utterance'), self.path)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.post.call_args.kwargs['json']['text'], 'next utterance')

    def test_post_busy_race_does_not_retry_or_open_circuit(self):
        self.post.side_effect = [Mock(status_code=429), audio_response()]
        self.assertIsNone(self.engine.generate_audio('busy utterance'))
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.engine.generate_audio('next utterance'), self.path)
        self.assertEqual(self.post.call_count, 2)

    def test_timed_out_utterance_is_not_replayed_and_next_utterance_can_recover(self):
        self.post.side_effect = [requests.ReadTimeout('private text must not be logged'), audio_response()]
        self.assertIsNone(self.engine.generate_audio('timed out utterance'))
        self.assertEqual(self.post.call_count, 1)
        self.health.return_value = health_response(status='busy')
        self.assertIsNone(self.engine.generate_audio('still busy'))
        self.assertEqual(self.post.call_count, 1)
        self.health.return_value = health_response()
        self.assertEqual(self.engine.generate_audio('new utterance'), self.path)
        self.assertEqual([call.kwargs['json']['text'] for call in self.post.call_args_list],
                         ['timed out utterance', 'new utterance'])

    def test_offline_circuit_expires_without_restarting_engine(self):
        with patch.object(client.time, 'monotonic', return_value=100) as clock:
            self.health.side_effect = requests.ConnectionError('offline')
            self.assertIsNone(self.engine.generate_audio('first'))
            self.assertIsNone(self.engine.generate_audio('second'))
            self.health.assert_called_once()
            self.post.assert_not_called()
            clock.return_value = 106
            self.health.side_effect = None
            self.assertEqual(self.engine.generate_audio('recovered'), self.path)

    def test_failed_inference_has_short_cooldown_and_can_recover(self):
        with patch.object(client.time, 'monotonic', return_value=100) as clock:
            self.post.side_effect = [Mock(status_code=503), audio_response()]
            self.assertIsNone(self.engine.generate_audio('first'))
            self.assertIsNone(self.engine.generate_audio('suppressed'))
            self.assertEqual(self.post.call_count, 1)
            clock.return_value = 106
            self.assertEqual(self.engine.generate_audio('recovered'), self.path)

    def test_discovery_timeout_never_sends_speech(self):
        self.health.side_effect = requests.ReadTimeout()
        self.assertIsNone(self.engine.generate_audio('first'))
        self.assertIsNone(self.engine.generate_audio('suppressed'))
        self.health.assert_called_once()
        self.post.assert_not_called()

    def test_post_connect_timeout_uses_offline_cooldown(self):
        self.post.side_effect = requests.ConnectTimeout()
        self.assertIsNone(self.engine.generate_audio('first'))
        self.assertIsNone(self.engine.generate_audio('suppressed'))
        self.post.assert_called_once()

    def test_malformed_or_wrong_identity_fails_closed(self):
        valid = health_response().json()
        for body in ([], {**valid, 'service': 'other'}, {**valid, 'voices': None},
                     {**valid, 'voices': [None]}, {**valid, 'voices': []},
                     {**valid, 'status': 'offline'}):
            with self.subTest(body=body):
                self.engine._voice_retry_at = 0
                self.health.return_value = Mock(status_code=200, json=Mock(return_value=body))
                self.assertIsNone(self.engine.generate_audio('first'))
        self.post.assert_not_called()

    def test_redirects_are_not_followed_or_treated_as_audio(self):
        self.health.return_value = Mock(status_code=302)
        self.assertIsNone(self.engine.generate_audio('first'))
        self.post.assert_not_called()
        self.engine._voice_retry_at = 0
        self.health.return_value = health_response()
        self.post.return_value = Mock(status_code=302)
        self.assertIsNone(self.engine.generate_audio('second'))
        self.assertFalse(Path(self.path).exists())

    def test_invalid_wav_preserves_text_fallback_without_cache_file(self):
        self.post.return_value = Mock(status_code=200, headers={'Content-Type': 'audio/wav'}, content=b'not wav')
        self.assertIsNone(self.engine.generate_audio('first'))
        self.assertFalse(Path(self.path).exists())

    def test_failure_diagnostics_exclude_text_and_response_body(self):
        self.post.side_effect = requests.ReadTimeout('private response body')
        with patch.object(client.logger, 'warning') as log:
            self.assertIsNone(self.engine.generate_audio('private utterance'))
        message = log.call_args.args[0].format(*log.call_args.args[1:])
        self.assertIn('reason=timeout phase=synthesis', message)
        self.assertNotIn('private', message)


if __name__ == '__main__':
    unittest.main()
