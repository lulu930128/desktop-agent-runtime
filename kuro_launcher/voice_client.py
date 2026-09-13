"""Read-only service discovery and bounded synthesis; never owns shared processes."""
import io
import json
import urllib.request
import wave


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _open(request, timeout):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)


def health(base_url, timeout=3):
    with _open(base_url + '/health', timeout) as response:
        data = json.loads(response.read(65536))
    if data.get('service') != 'voice-runtime' or data.get('protocol_version') != 1:
        raise RuntimeError('Unexpected voice runtime identity')
    if data.get('status') not in {'available', 'busy'}:
        raise RuntimeError('Voice runtime unavailable')
    return data


def require_voice(base_url, voice, timeout=3):
    data = health(base_url, timeout=timeout)
    if not any(item.get('voice_id') == voice for item in data.get('voices', [])):
        raise RuntimeError(f'Voice runtime does not provide {voice}')
    return data


def synthesize(base_url, voice, text, language='ja', speed=1.2, timeout=120):
    require_voice(base_url, voice)
    request = urllib.request.Request(base_url + '/tts',
        data=json.dumps(dict(voice=voice, text=text, language=language, speed_factor=speed)).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with _open(request, timeout) as response:
        body = response.read(32 * 1024 * 1024 + 1)
        if response.headers.get_content_type() != 'audio/wav' or len(body) > 32 * 1024 * 1024:
            raise RuntimeError('Invalid voice audio response')
    with wave.open(io.BytesIO(body), 'rb') as audio:
        count = audio.getnframes()
        if count <= 0 or len(audio.readframes(count)) != count * audio.getsampwidth() * audio.getnchannels():
            raise RuntimeError('Empty or truncated voice audio')
    return body
