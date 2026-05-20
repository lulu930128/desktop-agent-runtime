from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

try:
    import loguru  # noqa: F401
except ModuleNotFoundError:
    class _TestLogger:
        def __getattr__(self, _name: str):
            return lambda *args, **kwargs: None

    sys.modules["loguru"] = types.SimpleNamespace(logger=_TestLogger())

from open_llm_vtuber.character_memory_manager import (  # noqa: E402
    add_character_memory,
    delete_character_memory,
    format_character_memories_for_prompt,
    list_character_memories,
    process_character_memory_turn,
    update_character_memory_status,
)
from open_llm_vtuber.character_memory_repository import (  # noqa: E402
    CharacterMemoryRepository,
)
from open_llm_vtuber.chat_history_manager import (  # noqa: E402
    create_new_history,
    store_message,
)
from open_llm_vtuber.conversation_history_index import (  # noqa: E402
    format_past_conversations_for_prompt,
    search_past_conversations,
)


class CharacterMemoryManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="kuro-memory-test-")
        self.previous_root = os.environ.get("KURO_MEMORY_ROOT")
        self.previous_cwd = os.getcwd()
        os.environ["KURO_MEMORY_ROOT"] = self.temp_dir
        os.chdir(self.temp_dir)
        self.conf_uid = "kuro"

    def tearDown(self) -> None:
        os.chdir(self.previous_cwd)
        if self.previous_root is None:
            os.environ.pop("KURO_MEMORY_ROOT", None)
        else:
            os.environ["KURO_MEMORY_ROOT"] = self.previous_root
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_repository_uses_safe_canonical_store_path(self) -> None:
        repository = CharacterMemoryRepository()

        store_path = repository.store_path(self.conf_uid)

        self.assertEqual(store_path.parent.name, self.conf_uid)
        self.assertEqual(store_path.name, "long_term.json")
        with self.assertRaises(ValueError):
            repository.store_path("..")

    def test_manual_memory_lifecycle(self) -> None:
        created = add_character_memory(
            self.conf_uid,
            "User prefers concise Traditional Chinese replies.",
            memory_type="preference",
            status="pending_confirmation",
        )
        self.assertTrue(created)

        self.assertEqual(list_character_memories(self.conf_uid), [])

        all_entries = list_character_memories(self.conf_uid, enabled_only=False)
        self.assertEqual(len(all_entries), 1)
        entry_id = all_entries[0]["id"]
        self.assertEqual(all_entries[0]["status"], "pending_confirmation")

        self.assertTrue(update_character_memory_status(self.conf_uid, entry_id, "active"))
        active_entries = list_character_memories(self.conf_uid)
        self.assertEqual(len(active_entries), 1)
        self.assertEqual(active_entries[0]["status"], "active")

        self.assertTrue(delete_character_memory(self.conf_uid, entry_id))
        self.assertEqual(list_character_memories(self.conf_uid, enabled_only=False), [])

    def test_retrieval_prioritizes_query_relevant_memory(self) -> None:
        add_character_memory(
            self.conf_uid,
            "User likes matcha tea during late night coding.",
            memory_type="preference",
            importance=0.75,
        )
        add_character_memory(
            self.conf_uid,
            "Launcher memory architecture uses repository and retriever boundaries.",
            memory_type="project_decision",
            scope_level="project",
            importance=0.75,
        )

        results = list_character_memories(
            self.conf_uid,
            query_text="launcher repository retriever",
            max_entries=2,
        )

        self.assertGreaterEqual(len(results), 2)
        self.assertIn("Launcher memory architecture", results[0]["content"])

        db_path = Path(self.temp_dir) / "character_memory.sqlite3"
        self.assertTrue(db_path.exists())
        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE conf_uid = ?",
                (self.conf_uid,),
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_sqlite_index_removes_stale_rows_on_next_query(self) -> None:
        add_character_memory(
            self.conf_uid,
            "Keep this memory about launcher indexing.",
            memory_type="project_state",
            scope_level="project",
        )
        add_character_memory(
            self.conf_uid,
            "Remove this memory about an obsolete launcher path.",
            memory_type="project_state",
            scope_level="project",
        )

        list_character_memories(
            self.conf_uid,
            query_text="launcher indexing",
            max_entries=2,
        )
        entries = list_character_memories(self.conf_uid, enabled_only=False)
        obsolete_entry = next(
            entry for entry in entries if "obsolete launcher path" in entry["content"]
        )
        self.assertTrue(delete_character_memory(self.conf_uid, obsolete_entry["id"]))

        list_character_memories(
            self.conf_uid,
            query_text="launcher indexing",
            max_entries=2,
        )
        db_path = Path(self.temp_dir) / "character_memory.sqlite3"
        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE conf_uid = ?",
                (self.conf_uid,),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_cross_history_search_excludes_current_history(self) -> None:
        old_history_uid = create_new_history(self.conf_uid)
        current_history_uid = create_new_history(self.conf_uid)
        store_message(
            self.conf_uid,
            old_history_uid,
            "human",
            "We decided the launcher memory should use SQLite FTS.",
        )
        store_message(
            self.conf_uid,
            current_history_uid,
            "human",
            "This current turn also mentions SQLite FTS.",
        )

        hits = search_past_conversations(
            self.conf_uid,
            "launcher SQLite FTS",
            exclude_history_uid=current_history_uid,
            max_snippets=5,
        )

        self.assertTrue(hits)
        self.assertTrue(all(hit["history_uid"] != current_history_uid for hit in hits))
        self.assertIn("launcher memory", hits[0]["content"])

    def test_cross_history_prompt_marks_raw_snippets(self) -> None:
        old_history_uid = create_new_history(self.conf_uid)
        current_history_uid = create_new_history(self.conf_uid)
        store_message(
            self.conf_uid,
            old_history_uid,
            "ai",
            "The professional architecture keeps long-term memory separate from raw history snippets.",
        )

        prompt = format_past_conversations_for_prompt(
            self.conf_uid,
            "raw history snippets architecture",
            current_history_uid=current_history_uid,
            max_snippets=3,
        )

        self.assertIn("Past conversation snippets", prompt)
        self.assertIn(old_history_uid, prompt)
        self.assertIn("not confirmed long-term facts", prompt)

    def test_prompt_excludes_pending_memory(self) -> None:
        active_text = "Remember that the project name is Kuro."
        pending_text = "Unapproved memory should not enter prompts."
        add_character_memory(self.conf_uid, active_text, memory_type="fact")
        add_character_memory(
            self.conf_uid,
            pending_text,
            memory_type="fact",
            status="pending_confirmation",
        )

        prompt = format_character_memories_for_prompt(
            self.conf_uid,
            query_text="project name",
            max_entries=8,
        )

        self.assertIn(active_text, prompt)
        self.assertNotIn(pending_text, prompt)

    def test_sensitive_turn_is_not_written(self) -> None:
        changed, notes = process_character_memory_turn(
            conf_uid=self.conf_uid,
            history_uid="history-1",
            user_text="Please remember my api key is sk-abcdefghijklmnopqrstuvwxyz.",
            assistant_text="I cannot store that.",
        )

        self.assertFalse(changed)
        self.assertIn("skipped-sensitive", notes)
        self.assertEqual(list_character_memories(self.conf_uid, enabled_only=False), [])


if __name__ == "__main__":
    unittest.main()
