"""Longitudinal, synthetic replay across the canonical owners."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from open_llm_vtuber import character_memory_manager as memory
from open_llm_vtuber import chat_history_manager as history
from open_llm_vtuber.character_memory_lifecycle import has_save_authorization
from open_llm_vtuber.conversation_history_index import (
    ConversationHistoryIndex,
    format_past_conversations_for_prompt,
)
from open_llm_vtuber.memory_formation import configure_policy
from open_llm_vtuber.memory_maintenance import backfill, backup, restore

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"


class Companion(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(directory.cleanup)
        self.scratch = Path(directory.name)
        self.state = self.scratch / "source"
        self.state.mkdir()
        previous = Path.cwd()
        os.chdir(self.state)
        self.addCleanup(os.chdir, previous)
        env = patch.dict(
            os.environ,
            KURO_MEMORY_ROOT=str(self.state / "memories"),
            KURO_MEMORY_ENCODER_DIR="",
        )
        env.start()
        self.addCleanup(env.stop)

    def policy(self, scope="global_user", categories=None):
        configure_policy(
            memory._MEMORY_REPOSITORY,
            "a",
            "",
            scope=scope,
            expected_digest=memory.formation_policy_digest("a", ""),
            categories=["experience", "preference", "goal"]
            if categories is None
            else categories,
        )

    def turn(self, uid, text, turn, reply="收到。", actor="a", project=""):
        receipt = history.store_message(
            actor,
            uid,
            "human",
            text,
            turn_id=turn,
            project_id=project,
            completion="received",
        )
        grant = memory.formation_policy_digest(actor, project)
        history.store_message(
            actor,
            uid,
            "ai",
            reply,
            turn_id=turn,
            project_id=project,
            completion="complete",
            formation_rule=grant,
        )
        return memory.finish_pending_turns(
            actor,
            uid,
            turn,
            dict(user_text=text, assistant_text=reply, project_id=project, **receipt),
        )

    def test_capacity_and_query_read_only(self):
        for i in range(95):
            memory.add_character_memory("a", f"numbered stable item {i:04}")
        entries = memory.list_character_memories("a")
        self.assertEqual(len(entries), 95)
        with patch.object(
            memory._MEMORY_REPOSITORY,
            "load",
            side_effect=AssertionError("hot JSON scan"),
        ):
            self.assertEqual(
                len(memory.list_character_memories("a", query_text="0094")), 1
            )
            self.assertEqual(
                memory.list_character_memories("a", query_text="unrelated"), []
            )
        target = entries[0]["id"]
        memory.update_character_memory_status("a", target, "disabled")
        memory.compact_character_memories("a")
        self.assertEqual(len(memory.list_character_memories("a")), 94)

    def test_scope_version_and_source_priority(self):
        memory.add_character_memory(
            "a", "Saffron project launch", scope_level="project", project_id="red"
        )
        memory.add_character_memory("a", "Secret character greeting")
        memory.add_character_memory(
            "a", "Thread appointment", scope_level="thread", history_uid="h"
        )
        self.assertTrue(
            memory.list_character_memories("b", project_id="red", query_text="Saffron")
        )
        self.assertFalse(
            memory.list_character_memories("b", project_id="blue", query_text="Saffron")
        )
        self.assertFalse(
            memory.list_character_memories("b", project_id="red", query_text="greeting")
        )
        self.assertFalse(
            memory.list_character_memories(
                "a", query_text="appointment", history_uid="other"
            )
        )
        self.assertTrue(
            memory.list_character_memories(
                "a", query_text="appointment", history_uid="h"
            )
        )
        self.turn("history", "以後叫我小晴", "1")
        self.turn("history", "以後叫我小夏", "2")
        records = memory.list_character_memories("b", enabled_only=False)
        old, new = sorted(records, key=lambda e: e["revision"])
        self.assertEqual(
            (old["status"], new["supersedes"]), ("superseded", [old["id"]])
        )
        self.assertEqual(new["status"], "active")
        self.assertEqual(memory.list_character_memories("b", query_text="小晴"), [])
        self.assertTrue(
            memory.list_character_memories("b", query_text="小晴", historical=True)
        )

    def test_scoped_assistant_reply_carries_original_subject(self):
        self.turn("first", "The Skylark launch code was BETA82.", "a1")
        self.turn(
            "second",
            "I changed my locker combination to ALDER82.",
            "a2",
            "Previous code superseded.",
        )
        hits = ConversationHistoryIndex().search(
            "a", "What was the Skylark launch code?"
        )
        self.assertTrue(any("BETA82" in h.content for h in hits))
        self.assertFalse(
            any(
                "Previous code" in h.content and "locker" not in h.content for h in hits
            )
        )

    def test_expired_project_state_retains_historical_evidence(self):
        memory.add_character_memory(
            "a",
            "Azul release pending",
            memory_type="project_state",
            scope_level="project",
            project_id="azul",
        )
        ns = memory.memory_namespaces("a", "azul")[-1]
        store = memory._load_store(ns)
        store["entries"][0].update(
            valid_from="2001-01-01T00:00:00+08:00", valid_to="2001-02-01T00:00:00+08:00"
        )
        memory._save_store(ns, store)
        self.assertFalse(
            memory.list_character_memories("b", project_id="azul", query_text="Azul")
        )
        self.assertTrue(
            memory.list_character_memories(
                "b", project_id="azul", query_text="Azul as of 2001-01-15"
            )
        )

    def test_asof_filters_future_claims_before_packing(self):
        for i, (name, day) in enumerate(
            [("小晴", "2026-10-01"), ("小夏", "2026-11-02")]
        ):
            memory.process_character_memory_turn(
                conf_uid="a",
                history_uid="h",
                turn_id=str(i),
                observed_at=day + "T19:20:00+08:00",
                user_text="以後叫我" + name,
            )
        before = memory.format_character_memories_for_prompt(
            "b", query_text="截至 2026-10-31 我叫小晴還是小夏？", max_entries=1
        )
        self.assertIn("小晴", before)
        self.assertNotIn("小夏", before)
        after = memory.format_character_memories_for_prompt(
            "b", query_text="截至 2026-11-02 我叫小晴還是小夏？", max_entries=1
        )
        self.assertIn("小夏", after)
        self.assertNotIn("小晴", after)

    def test_history_retry_reads_exact_identity(self):
        args = dict(
            conf_uid="a",
            history_uid="id",
            role="human",
            content="fixture",
            turn_id="once",
            completion="received",
        )
        receipt = history.store_message(**args)
        self.assertEqual(history.store_message(**args), receipt)
        self.assertEqual(len(history.get_history("a", "id")), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting History turn"):
            history.store_message(**dict(args, content="different"))

    def test_history_delta_atomicity_interruption_and_repair(self):
        uid = history.create_new_history("a")
        history.store_message("a", uid, "human", "alpha sentinel", turn_id="x")
        index = ConversationHistoryIndex()
        self.assertEqual(len(index.search("a", "alpha")), 1)
        with patch.object(index, "sync", side_effect=AssertionError("hot full scan")):
            history.store_message(
                "a",
                uid,
                "ai",
                "unfinished evidence",
                turn_id="x",
                completion="interrupted",
            )
            self.assertFalse(index.search("a", "unfinished"))
            self.assertTrue(history.modify_latest_message("a", uid, "ai", "partial"))
            self.assertTrue(index.search("a", "alpha"))
        path = Path(history._get_safe_history_path("a", uid))
        good = path.read_bytes()
        with (
            patch("os.replace", side_effect=OSError("fixture failure")),
            self.assertRaises(OSError),
        ):
            history.store_message("a", uid, "human", "lost")
        self.assertEqual(path.read_bytes(), good)
        index.sync("a")
        self.assertTrue(history.rename_history_file("a", uid, "renamed"))
        self.assertEqual(index.search("a", "alpha")[0].history_uid, "renamed")
        self.assertTrue(history.delete_history("a", "renamed"))
        self.assertFalse(index.search("a", "alpha"))
        path.write_bytes(b"{")
        with self.assertRaises(ValueError):
            history.store_message("a", uid, "human", "keep original")
        self.assertEqual(path.read_bytes(), b"{")

    def test_concurrent_history_and_queue_retry(self):
        uid = history.create_new_history("a")
        with ThreadPoolExecutor(2) as pool:
            list(
                pool.map(
                    lambda i: history.store_message("a", uid, "human", str(i)), range(6)
                )
            )
        self.assertEqual(
            {r["content"] for r in history.get_history("a", uid)},
            set(map(str, range(6))),
        )
        with patch.object(memory, "_save_store", side_effect=ValueError("busy")):
            self.assertIn(
                "formation-deferred", self.turn(uid, "請記住代號是琥珀", "abc")[1]
            )
        self.turn(uid, "收到", "def")
        self.assertEqual(len(memory.list_character_memories("a", query_text="琥珀")), 1)
        self.assertFalse(list(Path("chat_history/a/.formation-pending").glob("*.json")))

    @unittest.skipUnless(
        (MODEL / "model_quint8_avx2.onnx").exists(),
        "requires pinned local multilingual encoder",
    )
    def test_scoped_auto_multilingual_event_and_forget(self):
        os.environ["KURO_MEMORY_ENCODER_DIR"] = str(MODEL)
        self.policy()
        self.turn("history", "我昨天去京都參觀陶藝展。", "a1")
        self.turn("history", "我平常喜歡喝無糖茶。", "a2")
        current = memory.list_character_memories("b", query_text="普段飲むお茶")
        self.assertTrue(any("無糖茶" in r["content"] for r in current))
        chosen = current[0]
        self.assertEqual(chosen["save_authorization"]["method"], "scoped_auto")
        self.assertTrue(has_save_authorization(chosen))
        self.assertFalse(has_save_authorization(dict(chosen, content="unrelated")))
        self.turn("history", "忘記上一輪", "a3")
        self.assertFalse(
            any("無糖茶" in r["content"] for r in memory.list_character_memories("b"))
        )
        index = ConversationHistoryIndex()
        index.sync("a")
        self.assertFalse(
            any("無糖茶" in h.content for h in index.search("a", "無糖茶"))
        )
        self.assertTrue(
            any("陶藝展" in r["content"] for r in memory.list_character_memories("b"))
        )
        self.policy(categories=[])
        self.turn("history", "如果我想搬家呢？", "a4", reply="已完成搬家")
        self.assertFalse(
            any("搬家" in r["content"] for r in memory.list_character_memories("b"))
        )
        trace = format_past_conversations_for_prompt(
            "a", "陶藝展", current_history_uid="history"
        )
        self.assertIn("history=history", trace)

    def test_continuation_episode_preserves_numbers_and_forget_applies_to_linked_turns(
        self,
    ):
        uid = "episode"
        self.turn(uid, "陶藝展預算 37 歐元。", "first", reply="目前尚未買票。")
        idx = ConversationHistoryIndex()
        idx.sync("a")
        self.turn(uid, "後來呢？", "second", reply="第二天才買票。")
        with closing(idx._connect()) as conn:
            payload = json.loads(
                conn.execute(
                    "SELECT message_json FROM conversation_messages WHERE role='episode' AND message_index=3"
                ).fetchone()[0]
            )
        self.assertEqual(payload["source_span"], [0, 3])
        self.assertIn("37", payload["content"])
        self.assertIn("尚未", payload["content"])
        with patch.object(memory, "suppressed_sources", return_value={(uid, "first")}):
            self.assertFalse(any("37" in h.content for h in idx.search("a", "買票")))
        idx.sync("a")
        self.assertTrue(any("37" in h.content for h in idx.search("a", "陶藝展")))

    def test_renaming_cannot_revive_a_forgotten_turn(self):
        self.turn("before", "請記住我喜歡無糖抹茶。", "original")
        self.assertTrue(history.rename_history_file("a", "before", "after"))
        ConversationHistoryIndex().sync("a")
        linked = history.read_memory_source(self.state, "a", "before", "original")
        self.assertEqual(linked["history"], "after")
        self.assertIn("抹茶", linked["text"])
        self.turn("after", "忘記上一輪", "next")
        self.assertFalse(memory.list_character_memories("b", query_text="抹茶"))
        self.assertFalse(ConversationHistoryIndex().search("a", "抹茶"))
        self.assertEqual(
            backfill("a", apply=True)["receipts"]["after"]["excluded"]["suppressed"], 1
        )

    def test_corrupt_derived_restore_uses_canonical_files(self):
        from open_llm_vtuber.memory_maintenance import rebuild_copy

        self.turn("source", "請記住我喜歡無糖抹茶。", "one")
        index = ConversationHistoryIndex()
        self.assertTrue(index.search("a", "抹茶"))
        index.db_path().write_bytes(b"synthetic corrupt database")
        destination = self.scratch / "repaired"
        report = rebuild_copy(self.state, destination, ["a"])
        self.assertTrue(report["published"])
        self.assertEqual(index.db_path().read_bytes(), b"synthetic corrupt database")
        os.chdir(destination)
        os.environ["KURO_MEMORY_ROOT"] = str(destination / "memories")
        self.assertTrue(ConversationHistoryIndex().search("a", "抹茶"))
        self.assertTrue(memory.list_character_memories("b", query_text="抹茶"))

    def test_scope_migration_preserves_reviewed_bytes_and_unresolved_records(self):
        from open_llm_vtuber.memory_maintenance import migrate_scopes
        from open_llm_vtuber.character_memory_repository import (
            CharacterMemoryRepository,
            memory_namespaces,
        )

        self.turn("source", "請記住我喜歡無糖茶。", "grant")
        shared = memory_namespaces("a")[1]
        donor = memory._load_store(shared)
        entry = donor["entries"].pop()
        memory._save_store(shared, donor)
        old = memory._load_store("a")
        unknown = dict(entry, id="ambiguous", scope_id="a")
        old["entries"] = [unknown, entry]
        memory._save_store("a", old)
        initial = memory._store_path("a").read_bytes()
        target = self.scratch / "upgrade"
        result = migrate_scopes(self.state, target)
        self.assertEqual(result["counts"], {"moved": 1, "unresolved": 1})
        self.assertEqual(initial, memory._store_path("a").read_bytes())
        repo = CharacterMemoryRepository(root=target / "memories")
        self.assertEqual(repo.load(shared)["entries"], [entry])
        self.assertEqual(repo.load("a")["entries"], [unknown])
        self.assertTrue(has_save_authorization(repo.load(shared)["entries"][0]))

    def test_rehearsal_checkpoint_restart_restore(self):
        for uid in ("one", "two"):
            history.store_message("a", uid, "human", "我昨天去京都參觀陶藝展。")
            history.store_message("a", uid, "ai", "還沒買票，預算 37 歐元。")
        root = Path("chat_history/a")
        broken = root / "three.json"
        broken.write_bytes(b"{")
        original = (root / "one.json").read_bytes()
        dry = backfill("a", include_legacy=True)
        self.assertEqual((root / "one.json").read_bytes(), original)
        self.assertEqual((dry["sources"], dry["failed"]), (3, 1))
        first = backfill("a", include_legacy=True, apply=True)
        self.assertEqual(first["remaining"], 1)
        from open_llm_vtuber.memory_maintenance import processing_status

        self.assertEqual(processing_status(self.state, "a", "")["state"], "degraded")
        broken.write_bytes(original)
        final = backfill("a", include_legacy=True, apply=True)
        self.assertEqual(final["remaining"], 0)
        self.assertEqual(processing_status(self.state, "a", "")["processed"], 3)
        self.assertEqual(final["job_id"], first["job_id"])
        self.assertEqual(backfill("a", include_legacy=True, apply=True), final)
        self.turn("one", "請記住藍色代號", "89")
        store_bytes = memory._store_path("a").read_bytes()
        archive = self.scratch / "snapshot.zip"
        receipt = backup(self.state, archive)
        self.turn("one", "請記住額外代號", "90")
        with self.assertRaises(FileExistsError):
            restore(archive, self.state)
        destination = self.scratch / "new-machine"
        self.assertEqual(restore(archive, destination)["files"], receipt["files"])
        os.chdir(destination)
        os.environ["KURO_MEMORY_ROOT"] = str(destination / "memories")
        self.assertEqual(memory._store_path("a").read_bytes(), store_bytes)
        self.assertTrue(memory.list_character_memories("a", query_text="藍色代號"))
        idx = ConversationHistoryIndex()
        self.assertTrue(idx.search("a", "37"))
        with closing(sqlite3.connect(idx.db_path())) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) FROM conversation_messages WHERE role='episode'"
                ).fetchone()[0],
                4,
            )
