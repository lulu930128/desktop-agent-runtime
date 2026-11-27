import unittest
from unittest.mock import patch

from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent


class JapaneseExerciseHistoryTests(unittest.TestCase):
    def setUp(self):
        self.agent = BasicMemoryAgent.__new__(BasicMemoryAgent)
        self.agent._short_term_memory_token_budget = 1
        self.agent._short_term_memory_min_recent_messages = 1

    def restore(self, turns):
        with patch("open_llm_vtuber.agent.agents.basic_memory_agent.get_history", return_value=turns):
            self.agent.set_memory_from_history("kuro_01", "selected-history")

    def test_original_snapshot_and_partial_answers_survive_history_restore_and_trimming(self):
        self.restore([
            {"role": "human", "content": "unrelated"},
            {"role": "ai", "content": "【日文語練習｜jp-example】\nQ1 原題\nQ2 原題"},
            {"role": "human", "content": "1. を"},
            {"role": "ai", "content": "還有 Q2"},
            {"role": "human", "content": "【練習結束｜jp-example】"},
        ])
        self.assertEqual(self.agent._open_japanese_exercise(), (1, "jp-example"))
        self.assertEqual(self.agent._pack_short_term_memory(), self.agent._memory[1:])

    def test_closed_or_other_history_does_not_restore_old_exercise(self):
        self.restore([
            {"role": "ai", "content": "【日文語練習｜jp-example】\nQ1 原題"},
            {"role": "ai", "content": "已讀回\n【練習結束｜jp-example】"},
            {"role": "human", "content": "換個話題"},
        ])
        self.assertIsNone(self.agent._open_japanese_exercise())
        self.assertEqual(self.agent._pack_short_term_memory(), self.agent._memory[-1:])
        self.restore([])
        self.assertEqual(self.agent._pack_short_term_memory(), [])
