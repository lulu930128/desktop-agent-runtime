"""Phase1 synthetic replay: real parser/conversation/queue/manager, mocked IO."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import test_speech_semantic_alignment as semantic

anchor, segment, lane, footer = semantic.anchor, semantic.segment, semantic.lane, semantic.footer
SETTINGS = semantic.v1.CHAT_SPEECH_DEFAULTS


def natural_cases():
    return [
        ('你好', '你好！可以和我聊聊今天的心情。',
         lane([anchor('a', '和我聊聊今天的心情', 'option')],
              [segment('こんにちは。今日はどんな気分か、聞かせてね。', 'a')])),
        ('我好餓', '肚子餓的話，可以先吃點清淡的東西。',
         lane([anchor('a', '先吃點清淡的東西', 'option')],
              [segment('お腹がすいているなら、軽いものを少し食べよう。', 'a')])),
        # Same diagnostic shape as 2026-11-03 01:27:16, not private-log text.
        ('該不該吃宵夜', '你好！先喝點水，餓的話吃點清淡的東西，再決定要不要吃宵夜。',
         lane([anchor('g', '你好', 'fact'), anchor('w', '先喝點水', 'option'),
               anchor('f', '吃點清淡的東西', 'option'), anchor('d', '再決定要不要吃宵夜', 'fact')],
              [segment('こんにちは。まず水を飲んで、お腹がすいていたら軽いものを少し食べてから、夜食にするか決めよう。',
                       'g', 'w', 'f', 'd')])),
    ]


def parse(display, value):
    parser = semantic.SpeechLaneParser()
    raw = display + footer(value)
    visible = ''.join(parser.feed(char) for char in raw) + parser.finish_display()
    if visible != display:
        raise AssertionError('Display changed or private footer leaked')
    return parser.result(SETTINGS)


def hard_conflicts():
    for source, text, kind, reason in [
        ('價格100.5，停損95', '価格は95、損切りは100.5です。', 'fact', 'anchor_value_mismatch'),
        ('比率-5%', '比率は5%です。', 'fact', 'anchor_value_mismatch'),
        ('操作失敗 HTTP403', '操作は失敗しました。', 'status', 'anchor_value_mismatch'),
        ('操作失敗', '操作は成功しました。', 'status', 'anchor_status_mismatch'),
        ('工具請求遭阻擋', '処理は成功しました。', 'status', 'anchor_status_mismatch'),
        ('尚未驗證', '確認しました。', 'status', 'anchor_status_mismatch'),
        ('資料部分缺失', 'データは完全です。', 'status', 'anchor_status_mismatch'),
        ('不能下單', '注文できます。', 'status', 'anchor_status_mismatch'),
    ]:
        _, display, value = natural_cases()[1]
        display += '\n' + source
        value['anchors'].append(anchor('s', source, kind))
        value['speech'].append(segment(text, 's'))
        yield display, value, reason
    for text in ('公開ウェブを検索できません。',
                 'ウェブ検索か、診断チェックリストの確認ができません。'):
        _, display, value = natural_cases()[1]
        display += '\n' + semantic.OPTION_DISPLAY
        options = semantic.option_lane(text)
        value['anchors'].extend([dict(item, id='known_' + item['id']) for item in options['anchors']])
        value['speech'].append(segment(text, 'known_a', 'known_b'))
        yield display, value, 'option_unverified'


class Phase1ParserTests(unittest.TestCase):
    def test_natural_chat_keeps_speech_and_explicit_unverified_diagnostics(self):
        for user, display, value in natural_cases():
            with self.subTest(user=user):
                result = parse(display, value)
                self.assertEqual(result['state'], 'semantic_unverified')
                self.assertEqual(result['text'], value['speech'][0]['text'])
                diag = result['diagnostics']
                self.assertEqual(diag['rule_id'], 'semantic_unverified')
                self.assertEqual(diag['stage'], 'final')
                self.assertEqual(diag['received_anchors'], len(value['anchors']))
                self.assertEqual(diag['received_semantic_segments'], 1)
                self.assertIn(dict(rule_id='option_unverified', stage='required_anchor',
                                   anchor_index=1 if user == '該不該吃宵夜' else 0), diag['soft_failures'])
                self.assertNotIn(value['speech'][0]['text'], json.dumps(diag, ensure_ascii=False))

    def test_unknown_never_short_circuits_later_hard_conflicts(self):
        for display, value, reason in hard_conflicts():
            with self.subTest(reason=reason, text=value['speech'][-1]['text']):
                result = parse(display, value)
                self.assertEqual(result['state'], reason)
                self.assertEqual(result['text'], '')
                self.assertIn('soft_failures', result['diagnostics'])

    def test_display_checks_still_run_after_unknown_option(self):
        _, display, value = natural_cases()[1]
        for extra, reason in [('\n尚未驗證', 'semantic_unverified'),
                              ('\n' + semantic.OPTION_DISPLAY, 'semantic_unverified')]:
            with self.subTest(reason=reason):
                self.assertEqual(parse(display + extra, value)['state'], reason)
        value['speech'][0]['text'] += '価格は999です。'
        self.assertEqual(parse(display, value)['state'], 'unbacked_value')

    def test_unknown_display_options_keep_soft_state_and_missing_references_block(self):
        display = 'A：先喝點水\nB：吃點清淡的東西'
        value = lane([anchor('a', '先喝點水', 'option'), anchor('b', '吃點清淡的東西', 'option')],
                     [segment('水を飲むか、軽いものを食べよう。', 'a', 'b')])
        result = parse(display, value)
        self.assertEqual(result['state'], 'semantic_unverified')
        self.assertTrue(any(item['stage'] == 'display' for item in result['diagnostics']['soft_failures']))
        value['speech'][0]['source_ids'] = ['a']
        self.assertEqual(parse(display, value)['state'], 'required_anchor_missing')
        value['anchors'][1]['importance'] = 'display_only'
        self.assertEqual(parse(display, value)['state'], 'semantic_unverified')

    def test_same_language_negative_remains_rejected_and_unprovable_omission_is_unverified(self):
        value = lane([anchor('a', 'origami folding', 'option')], [segment('origamiはできません。', 'a')])
        self.assertEqual(parse('origami folding', value)['state'], 'option_unverified')
        # With no shared words a lexical guard cannot prove omission either.
        _, display, value = natural_cases()[1]
        value['speech'][0]['text'] = 'こんにちは。'
        self.assertEqual(parse(display, value)['state'], 'semantic_unverified')

    def test_schema_technical_locale_and_required_segment_guards_stay_closed(self):
        _, display, original = natural_cases()[1]
        cases = []
        for key, data, reason in [('locale', 'en-US', 'invalid_schema'),
                                  ('policy', 'brief', 'invalid_schema'),
                                  ('emotion', [], 'invalid_schema')]:
            value = copy.deepcopy(original); value[key] = data; cases.append((value, reason))
        for text, reason in [('This is English.', 'locale_mismatch'), ('', 'empty'),
                             ('URLはhttps://example.testです。', 'technical_payload'),
                             ('設定は`x`です。', 'technical_payload')]:
            value = copy.deepcopy(original); value['speech'].append(segment(text)); cases.append((value, reason))
        value = copy.deepcopy(original); value['anchors'][0]['source'] = '不在文字中'; cases.append((value, 'anchor_source_missing'))
        value = copy.deepcopy(original); value['speech'][0]['source_ids'] = ['unknown']; cases.append((value, 'unknown_source_id'))
        value = copy.deepcopy(original); value['speech'] = []; cases.append((value, 'required_anchor_missing'))
        for value, reason in cases:
            with self.subTest(reason=reason):
                result = parse(display, value)
                self.assertEqual(result['state'], reason)
                self.assertEqual(result['text'], '')

    def test_malformed_duplicate_keys_and_missing_footer_do_not_gain_speech(self):
        _, display, value = natural_cases()[1]
        for raw, reason in [(display, 'missing'),
                            (display + semantic.SPEECH_LANE_V2_MARKER + '{broken', 'malformed'),
                            (display + footer(value)[:-1] + ',"emotion":"joy"}', 'malformed')]:
            parser = semantic.SpeechLaneParser()
            self.assertEqual(parser.feed(raw) + parser.finish_display(), display)
            result = parser.result(SETTINGS)
            self.assertEqual((result['state'], result['text']), (reason, ''))


class Phase1ConversationTests(unittest.IsolatedAsyncioTestCase):
    setUp = semantic.v1.ConversationTests.setUp
    context = semantic.v1.ConversationTests.context
    run_turn = semantic.v1.ConversationTests.run_turn

    async def check_turn(self, user, display, value, state='semantic_unverified'):
        self.tts.async_generate_audio.reset_mock()
        self.send.events.clear()
        context, llm, _ = self.context([list(display + footer(value))])
        with patch('open_llm_vtuber.conversations.single_conversation.logger.info') as timing:
            self.assertEqual(await self.run_turn(context, user), display)
        metrics = next(json.loads(call.args[1]) for call in timing.call_args_list if call.args[0] == 'speech_timing {}')
        self.assertNotIn(value['speech'][0]['text'], json.dumps(metrics, ensure_ascii=False))
        self.assertEqual(metrics['lane_state'], state)
        self.assertEqual(metrics['state'], state)
        self.assertEqual(metrics['bridge_requests'], 0)
        self.assertEqual(len(llm.calls), 1 if state in {"ready", "semantic_unverified"} else 2)
        self.assertEqual(context.agent_engine._memory[-1]['content'], display)
        self.assertEqual(self.stores.call_args.kwargs['content'], display)
        self.assertEqual(self.memories.call_args.kwargs['assistant_text'], display)
        public = json.dumps(self.send.events, ensure_ascii=False)
        self.assertNotIn('source_ids', public)
        self.assertNotIn('KURO_SPEECH', public)
        self.assertNotIn(value['speech'][0]['text'], public)
        self.assertEqual(''.join(e.get('display_text', {}).get('text', '') for e in self.send.events), display)
        self.assertEqual(self.send.events[-1], dict(type='control', text='conversation-chain-end'))
        return metrics

    async def test_natural_chat_parser_to_conversation_to_tts_preserves_soft_state(self):
        for user, display, value in natural_cases():
            with self.subTest(user=user):
                metrics = await self.check_turn(user, display, value)
                self.tts.async_generate_audio.assert_awaited_once()
                self.assertEqual(self.tts.async_generate_audio.await_args.kwargs['text'], value['speech'][0]['text'])
                self.assertEqual(metrics['tts_chunks'], 1)
                self.assertEqual(metrics['anchors'], len(value['anchors']))
                self.assertEqual(metrics['semantic_segments'], 1)
                status = next(e for e in self.send.events if e.get('type') == 'speech-status')
                self.assertEqual((status['status'], status['reason']), ('degraded', 'semantic_unverified'))
                self.assertEqual(status['validation']['rule_id'], 'semantic_unverified')
                self.assertIn(dict(type='backend-synth-complete'), self.send.events)
                self.assertTrue(any(e.get('audio') for e in self.send.events))

    async def test_soft_option_with_hard_conflict_never_reaches_tts(self):
        for display, value, state in hard_conflicts():
            with self.subTest(state=state):
                await self.check_turn('fixture', display, value, state)
                self.tts.async_generate_audio.assert_not_awaited()
                self.assertFalse(any(e.get('audio') for e in self.send.events))
                self.assertFalse(any(e.get('status') == 'degraded' for e in self.send.events))

    async def test_soft_state_survives_pronunciation_and_voice_guards(self):
        from open_llm_vtuber.conversations.conversation_utils import queue_generated_speech
        from open_llm_vtuber.conversations.tts_manager import TTSTaskManager
        _, display, value = natural_cases()[1]
        result = parse(display, value)
        manager = TTSTaskManager()
        with patch('open_llm_vtuber.conversations.conversation_utils.apply_pronunciation',
                   return_value=('軽いものを食べよう。', ['fixture'])):
            await queue_generated_speech(lane=result, settings=SETTINGS, tts_manager=manager,
                tts_engine=self.tts, live2d_model=self.live2d, websocket_send=self.send)
            await asyncio.gather(*manager.task_list)
        self.assertEqual(manager.speech_metrics['state'], 'semantic_unverified')
        self.assertEqual(manager.speech_metrics['pronunciation_hits'], 1)
        self.assertEqual(self.tts.async_generate_audio.await_args.kwargs['text'], '軽いものを食べよう。')
        manager.clear()
        for locale, engine, reason in [('ja-JP', None, 'voice_unavailable'),
                                       ('en-US', self.tts, 'locale_voice_unverified')]:
            self.tts.async_generate_audio.reset_mock()
            manager = TTSTaskManager()
            await queue_generated_speech(lane=result, settings=dict(SETTINGS, locale=locale), tts_manager=manager,
                tts_engine=engine, live2d_model=self.live2d, websocket_send=self.send)
            self.assertEqual(manager.speech_metrics['state'], reason)
            self.tts.async_generate_audio.assert_not_awaited()
            manager.clear()

    async def test_degraded_long_speech_uses_existing_group_fail_stop_and_ack(self):
        for failure in (False, True):
            self.tts.async_generate_audio.return_value = None if failure else 'fixture.wav'
            user, display, value = natural_cases()[1]
            value['speech'][0]['text'] = '軽いものを食べよう。温かいものがいいね。ゆっくり食べてね。少しで大丈夫。水も飲もう。あとで考えよう。' * 3
            metrics = await self.check_turn(user, display, value)
            self.assertEqual(metrics['tts_chunks'], 18)
            self.assertEqual(self.tts.async_generate_audio.await_count, 1 if failure else 18)
            self.assertIn(dict(type='backend-synth-complete'), self.send.events)
            if not failure:
                self.assertEqual(''.join(call.kwargs['text'] for call in self.tts.async_generate_audio.await_args_list),
                                 value['speech'][0]['text'])

    async def test_cancel_before_final_boundary_never_queues_soft_speech(self):
        _, display, value = natural_cases()[1]
        context, _, _ = self.context([[]])
        entered = asyncio.Event()
        async def stream(*args, **kwargs):
            yield display + footer(value)
            entered.set()
            await asyncio.Event().wait()
        context.agent_engine._llm.chat_completion = stream
        task = asyncio.create_task(self.run_turn(context))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.tts.async_generate_audio.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
