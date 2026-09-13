import copy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from open_llm_vtuber import character_memory_manager as memory
from open_llm_vtuber.character_memory_lifecycle import review_digest, entry_status, is_active_memory
from open_llm_vtuber.character_memory_repository import CharacterMemoryRepository, store_lock
from open_llm_vtuber.character_memory_migration import dry_run, apply_migration, file_digest, restore


class MemoryTrustTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"KURO_MEMORY_ROOT": self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_claim_and_forged_evidence_never_activate(self):
        plan = memory.build_memory_write_plan(user_text="幫我修復這個專案的 MCP 工具", assistant_text="已完成修復這個專案的 MCP 工具")
        self.assertTrue(plan.candidates)
        self.assertTrue(all(c["status"] == "pending_confirmation" and c["enabled"] is False for c in plan.candidates))
        memory.add_character_memory("test", "Claim of deployment complete", source="tool_verified", evidence={"verified": True, "tool_call_id": "fake"})
        self.assertEqual(memory.list_character_memories("test"), [])

    def test_explicit_save_and_ordinary_statement(self):
        memory.process_character_memory_turn(conf_uid="test", history_uid="h", user_text="請記住我喜歡繁體中文")
        entries = memory.list_character_memories("test")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["save_authorization"]["method"], "explicit")
        plan = memory.build_memory_write_plan(user_text="我喜歡喝茶")
        self.assertTrue(all(c["status"] == "pending_confirmation" for c in plan.candidates))

    def test_status_and_content_tampering_fail_closed(self):
        for status in ("unverified", "unknown", {}, [], 1, "", None):
            entry = {"status": status, "enabled": True, "source": "manual"}
            self.assertFalse(memory._is_active_memory(entry))
            self.assertFalse(is_active_memory(entry))
        self.assertEqual(entry_status({"source": "manual"}), "active")
        self.assertEqual(entry_status({"source": "assistant_outcome"}), "pending_confirmation")
        memory.add_character_memory("test", "Stable preference")
        entry = memory.list_character_memories("test")[0]
        entry["content"] = "Different content"
        self.assertFalse(is_active_memory(entry))

    def test_duplicate_and_conflicting_claim_preserves_decisions(self):
        memory.add_character_memory("test", "Stable preference")
        before = memory._load_store("test")
        record = before["entries"][0]
        for status in ("active", "disabled", "pending_delete"):
            store = copy.deepcopy(before)
            store["entries"][0]["status"] = status
            store["entries"][0]["enabled"] = status == "active"
            original = copy.deepcopy(store["entries"][0])
            memory._upsert_memory(store, content=record["content"], memory_type="fact", source="assistant_outcome", history_uid="claim", confidence=1, importance=1)
            memory._compact_store(store)
            self.assertEqual(store["entries"][0], original)

    def test_review_digest_and_final_delete_refresh_index(self):
        memory.add_character_memory("test", "Pending preference", status="pending_confirmation")
        entry = memory.list_character_memories("test", enabled_only=False)[0]
        with self.assertRaises(ValueError):
            memory.update_character_memory_status("test", entry["id"], "active", expected_digest="outdated")
        memory.update_character_memory_status("test", entry["id"], "active", expected_digest=review_digest(entry))
        self.assertEqual(len(memory.list_character_memories("test")), 1)
        memory.delete_character_memory("test", entry["id"])
        self.assertEqual(memory.format_character_memories_for_prompt("test"), "")
        with closing(sqlite3.connect(Path(self.temp.name)/"character_memory.sqlite3")) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM memory_entries WHERE conf_uid='test'").fetchone()[0], 0)

    def test_legacy_dry_run_migration_restore(self):
        source = {"entries": [
            {"id": "manual", "source": "manual", "status": "active", "enabled": True, "created_at": "old"},
            {"id": "claim", "source": "assistant_outcome", "status": "active", "enabled": True},
        ]}
        migrated, changes = dry_run(source)
        self.assertEqual(len(changes), 1)
        self.assertEqual(source["entries"][1]["status"], "active")
        self.assertEqual(migrated["entries"][0], source["entries"][0])
        self.assertEqual(dry_run(migrated)[1], [])
        path, backup = Path(self.temp.name)/"store.json", Path(self.temp.name)/"backup.json"
        path.write_text(json.dumps(source), encoding="utf-8")
        digest = file_digest(path)
        with self.assertRaises(ValueError):
            apply_migration(path, expected_digest="old", backup=backup)
        result = apply_migration(path, expected_digest=digest, backup=backup)
        index = memory.SQLiteMemoryIndex(db_path=Path(self.temp.name)/'migration-index.sqlite3')
        index.sync('test',json.loads(path.read_text())['entries'])
        with closing(sqlite3.connect(index.db_path())) as conn:
            self.assertEqual(conn.execute("SELECT status,enabled FROM memory_entries WHERE entry_id='claim'").fetchone(),('pending_confirmation',0))
        restore(path, backup=backup, expected_current_digest=result["after_digest"], expected_backup_digest=digest)
        self.assertEqual(file_digest(path), digest)
        index.sync('test',json.loads(path.read_text())['entries'])
        with closing(sqlite3.connect(index.db_path())) as conn:
            # Even a restored old claim is excluded by the shared lifecycle.
            self.assertEqual(conn.execute("SELECT status,enabled FROM memory_entries WHERE entry_id='claim'").fetchone(),('pending_confirmation',0))

    def test_stale_snapshot_and_revoked_approval_cannot_overwrite(self):
        memory.add_character_memory("test", "Candidate", status="pending_confirmation")
        repository = CharacterMemoryRepository()
        stale = repository.load("test")
        entry = stale["entries"][0]
        digest = review_digest(entry)
        memory.update_character_memory_status("test", entry["id"], "disabled")
        with self.assertRaises(ValueError):
            memory.update_character_memory_status("test", entry["id"], "active", expected_digest=digest)
        with self.assertRaises(ValueError):
            repository.save("test", stale)
        self.assertEqual(memory.list_character_memories("test"), [])
        with store_lock(repository.store_path("test")):
            with self.assertRaises(ValueError):
                repository.save("test", repository.load("test"))
        memory.add_character_memory("test", "Writer after lock release")

    def test_malformed_store_is_not_replaced_by_empty_data(self):
        repository = CharacterMemoryRepository()
        path = repository.store_path("test")
        path.parent.mkdir(parents=True)
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            memory.add_character_memory("test", "Would overwrite data")
        self.assertEqual(path.read_text(), '{broken')

    def test_interrupted_migration_retains_original_and_verified_backup(self):
        path, backup = Path(self.temp.name)/'store.json', Path(self.temp.name)/'backup.json'
        path.write_text(json.dumps({'entries':[{'id':'claim','source':'assistant_outcome','content':'claim'}]}),encoding='utf-8')
        original = file_digest(path)
        with patch('open_llm_vtuber.character_memory_migration.os.replace',side_effect=OSError('fixture interruption')):
            with self.assertRaises(OSError):
                apply_migration(path,expected_digest=original,backup=backup)
        self.assertEqual(file_digest(path),original)
        self.assertEqual(file_digest(backup),original)
        self.assertEqual(list(path.parent.glob('.memory-migration-*')),[])
        backup.write_text('{"entries":[]}',encoding='utf-8')
        with self.assertRaises(ValueError):
            restore(path,backup=backup,expected_current_digest=original,expected_backup_digest=original)
        self.assertEqual(file_digest(path),original)
