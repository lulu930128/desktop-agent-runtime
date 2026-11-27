"""Anonymous Qt display fixtures; no GUI, services or private history."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from web_candidate_fixtures import ChatFixture, controller_fixture

ROOT = Path(__file__).resolve().parents[1]
PARTS = ['工具清單：\n', '\n', '- alpha：讀取\n', '  說明保留兩個空格\n',
         '- beta：查詢\r\n', '重複', '重複', '\n```python\n', 'x = 1\n', '```\n']
DISPLAY = ''.join(PARTS)


def fixture():
    events = []
    chat = ChatFixture()
    adapter = QtOwnerAdapter(controller_fixture(), chat, lambda work, done: done(work()),
                             window_action=Mock(), event=lambda *args: events.append(args))
    adapter.state = 'idle'
    return adapter, chat, events


def receive(adapter, kind, **values):
    scope = dict(zip(('client_uid', 'conf_uid', 'context_id', 'history_uid'), adapter.chat.history_identity()))
    adapter.receive(dict(type=kind, conversation_scope=scope, **values))


def delta(adapter, value):
    receive(adapter, 'audio', display_text={'text': value}, display_append=True,
            display_contract='kuro.speech-lanes.v1')


class DisplayStreamTests(unittest.TestCase):
    def test_speech_status_is_visible_scoped_and_cleared_on_next_turn(self):
        adapter, _, events = fixture()
        receive(adapter, 'speech-status', status='failed')
        self.assertEqual(adapter.chat_state()['speechStatus'], 'failed')
        self.assertEqual(events[-1][0], 'onChatState')
        adapter.receive(dict(type='speech-status', status='completed', conversation_scope={}))
        self.assertEqual(adapter.chat_state()['speechStatus'], 'failed')
        receive(adapter, 'control', text='conversation-chain-start')
        self.assertEqual(adapter.chat_state()['speechStatus'], '')
        receive(adapter, 'audio', audio=None, display_text={'text':''}, speech_status='unavailable')
        self.assertEqual(events[-1][1]['speechStatus'], 'unavailable')

    def test_ordered_deltas_are_lossless_including_repeat_and_whitespace(self):
        adapter, _, _ = fixture()
        for part in PARTS:
            delta(adapter, part)
        self.assertEqual(adapter.chat_state()['latestAssistantText'], DISPLAY)

    def test_full_text_is_authoritative_and_idempotent_without_duplicate_events(self):
        adapter, _, events = fixture()
        delta(adapter, '舊的暫存文字')
        receive(adapter, 'full-text', text=DISPLAY)
        self.assertEqual(adapter.latest_assistant, DISPLAY)
        before = len(events)
        receive(adapter, 'full-text', text=DISPLAY)
        receive(adapter, 'audio', display_text={'text': ''}, audio='synthetic')
        self.assertEqual(len(events), before)

    def test_cumulative_snapshots_do_not_duplicate_earlier_deltas(self):
        adapter, _, _ = fixture()
        delta(adapter, '回答\n')
        delta(adapter, '- 第一項\n')
        receive(adapter, 'full-text', text='回答\n- 第一項\n- 第二項\n')
        self.assertEqual(adapter.latest_assistant, '回答\n- 第一項\n- 第二項\n')

    def test_whitespace_delta_and_large_display_are_not_truncated(self):
        adapter, _, _ = fixture()
        delta(adapter, ' ')
        delta(adapter, '\n\t')
        delta(adapter, '字' * 100001)
        self.assertEqual(adapter.latest_assistant, ' \n\t' + '字' * 100001)

    def test_old_scope_cannot_append_after_reconnect(self):
        adapter, chat, _ = fixture()
        scope = dict(zip(('client_uid', 'conf_uid', 'context_id', 'history_uid'), chat.history_identity()))
        delta(adapter, '舊回答')
        chat.context_id = 'reconnected'
        adapter.on_state('idle', True)
        adapter.receive(dict(type='audio', conversation_scope=scope, display_text={'text': '舊事件'},
                             display_append=True, display_contract='kuro.speech-lanes.v1'))
        self.assertEqual(adapter.latest_assistant, '')
        delta(adapter, '新回答\n')
        self.assertEqual(adapter.latest_assistant, '新回答\n')

    def test_new_turn_resets_stream_but_preserves_previous_history(self):
        adapter, _, _ = fixture()
        adapter.history_rows = [{'role': 'ai', 'content': DISPLAY}]
        for _ in range(2):
            receive(adapter, 'control', text='conversation-chain-start')
            for part in PARTS:
                delta(adapter, part)
            receive(adapter, 'control', text='conversation-chain-end')
            self.assertEqual(adapter.latest_assistant, DISPLAY)
            self.assertEqual(adapter.history_rows[0]['content'], DISPLAY)


def export_frames():
    adapter, chat, _ = fixture()
    adapter.latest_user = '列出工具'
    frames = []
    def frame(name):
        frames.append(dict(name=name, chat=adapter.chat_state(), history=adapter._history_result()))
    receive(adapter, 'control', text='conversation-chain-start')
    for part in PARTS:
        delta(adapter, part)
    frame('live')
    receive(adapter, 'control', text='conversation-chain-end')
    frame('final-before-history')
    result = []
    adapter.dispatch('getHistories', {}, result.append)
    adapter.receive(dict(type='history-list', request_id='ws-id', client_uid=chat.client_uid,
                         conf_uid=chat.conf_uid, context_id=chat.context_id, histories=[]))
    adapter.receive(dict(type='history-data', request_id='ws-id', client_uid=chat.client_uid,
                         conf_uid=chat.conf_uid, context_id=chat.context_id,
                         timeline=[dict(role='human', content='列出工具'), dict(role='ai', content=DISPLAY)]))
    frame('history-ack')
    chat.context_id = 'reconnected'
    adapter.on_state('idle', True)
    frame('reconnected')
    print(json.dumps(frames, ensure_ascii=False))


if __name__ == '__main__':
    if '--export' in sys.argv:
        export_frames()
    else:
        unittest.main()
