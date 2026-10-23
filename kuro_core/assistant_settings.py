"""Core-owned assistant preferences; no provider, speech or scheduler side effects.

The existing Core database lease also owns this adjacent settings file. Reads do
not create state. G1 persists intent; execution admission stays closed until G2.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

from .api_server import ApiConflict

CONTRACT = 'kuro.core.assistant-settings.v1'
DEFAULTS = {'proactiveVoice': False,
            'omi': {'enabled': False, 'intervalMinutes': 30, 'dailyQueryBudget': 12}}
LIMITS = {'intervalMinutes': {'min': 5, 'max': 1440},
          'dailyQueryBudget': {'min': 0, 'max': 24}}


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != {'proactiveVoice', 'omi'}:
        raise ValueError('assistant_settings_fields')
    if type(value['proactiveVoice']) is not bool:
        raise ValueError('proactive_voice_boolean_required')
    omi = value['omi']
    if not isinstance(omi, dict) or set(omi) != {'enabled', *LIMITS}:
        raise ValueError('omi_settings_fields')
    if type(omi['enabled']) is not bool:
        raise ValueError('omi_enabled_boolean_required')
    for key, bounds in LIMITS.items():
        if type(omi[key]) is not int or not bounds['min'] <= omi[key] <= bounds['max']:
            raise ValueError('omi_' + key + '_out_of_range')
    return copy.deepcopy(value)


def encoded(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


class AssistantSettings:
    def __init__(self, db_path):
        self.path = Path(db_path).absolute().with_suffix('.settings.json')
        self.lock = threading.RLock()

    def _record(self):
        if self.path.resolve() != self.path or self.path.is_symlink():
            raise ValueError('assistant_settings_redirect_rejected')
        try:
            with self.path.open('rb') as stream:
                data = stream.read(4097)
        except FileNotFoundError:
            return {'schema': 1, 'generation': 0, 'settings': copy.deepcopy(DEFAULTS)}
        if len(data) > 4096:
            raise ValueError('assistant_settings_too_large')
        record = json.loads(data.decode('utf-8'))
        if (not isinstance(record, dict) or set(record) != {'schema', 'generation', 'settings'}
                or type(record['schema']) is not int or record['schema'] != 1
                or type(record['generation']) is not int or not 1 <= record['generation'] <= 2**53 - 1):
            raise ValueError('assistant_settings_schema_invalid')
        validate_settings(record['settings'])
        return record

    @staticmethod
    def _admission(settings, action):
        if action not in {'omi-observation', 'proactive-voice'}:
            return {'allowed': False, 'reason': 'unknown_action'}
        requested = settings['proactiveVoice'] if action == 'proactive-voice' else settings['omi']['enabled']
        reason = 'disabled' if not requested else 'execution_not_available_g1'
        if action == 'omi-observation' and requested and settings['omi']['dailyQueryBudget'] == 0:
            reason = 'query_budget_zero'
        return {'allowed': False, 'requestedEnabled': requested, 'reason': reason}

    def admission(self, action):
        """Backend decision boundary; an enabled preference never starts work in G1."""
        with self.lock:
            try:
                return self._admission(self._record()['settings'], action)
            except (OSError, ValueError, UnicodeError):
                return {'allowed': False, 'reason': 'settings_unavailable'}

    def runtime_policy(self):
        # Read persisted owner policy for every backend status/admission decision.
        return {'consumer': 'kuro-core', 'executionAvailable': False,
                'omi': self.admission('omi-observation'),
                'proactiveVoice': self.admission('proactive-voice'),
                'access': 'read_only', 'writes': 'confirmation_required',
                'providerRefresh': False, 'paidLlm': False,
                'queriesUsedToday': None, 'lastObservationAt': None}

    def read(self, query):
        if query:
            raise ValueError('assistant_settings_query_not_supported')
        with self.lock:
            record = self._record()
            return {'contract': CONTRACT, 'revision': hashlib.sha256(encoded(record)).hexdigest(),
                    'persisted': record['generation'] > 0, 'settings': record['settings'],
                    'limits': copy.deepcopy(LIMITS), 'runtime': self.runtime_policy()}

    def update(self, payload):
        if (not isinstance(payload, dict)
                or set(payload) != {'settings', 'expectedRevision', 'confirmed'}):
            raise ValueError('assistant_settings_command_fields')
        if payload['confirmed'] is not True:
            raise PermissionError('assistant_settings_confirmation_required')
        settings = validate_settings(payload['settings'])
        revision = payload['expectedRevision']
        if not isinstance(revision, str) or len(revision) != 64 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('assistant_settings_revision_required')
        with self.lock:
            current = self._record()
            if hashlib.sha256(encoded(current)).hexdigest() != revision:
                raise ApiConflict('Assistant settings changed; read again before confirming.')
            if current['generation'] >= 2**53 - 1:
                raise ValueError('assistant_settings_generation_exhausted')
            record = {'schema': 1, 'generation': current['generation'] + 1, 'settings': settings}
            temporary = None
            try:
                # Parent is already owned/created by the Core service lease.
                with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.assistant-settings-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(encoded(record))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            result = self.read({})
            if result['settings'] != settings:
                raise RuntimeError('assistant_settings_readback_mismatch')
            return result

    def register_routes(self, api):
        api.register('GET', '/v1/assistant-settings', self.read)
        api.register('POST', '/v1/assistant-settings', self.update)
