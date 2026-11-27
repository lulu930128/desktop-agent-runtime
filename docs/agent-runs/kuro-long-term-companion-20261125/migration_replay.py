"""Synthetic year of writes across process boundaries, portable restore and rollback rehearsal."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from quality_replay import ROOT

sys.path.insert(0, str(ROOT / "Open-LLM-VTuber/src"))


def inventory(root):
    from open_llm_vtuber.memory_maintenance import _sources

    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in _sources(root)
    }


def produce(start, end):
    from open_llm_vtuber import chat_history_manager as history
    from open_llm_vtuber import character_memory_manager as memory
    from open_llm_vtuber.conversation_history_index import ConversationHistoryIndex

    idx = ConversationHistoryIndex()
    for day in range(start, end):
        actor = ("a", "b")[day % 2]
        project = ("orchid", "maple")[(day // 2) % 2]
        uid = "month-" + str(day // 30)
        stamp = (
            datetime(2025, 1, 1, 18, tzinfo=timezone(timedelta(hours=8)))
            + timedelta(days=day)
        ).isoformat()
        ident = f"d{day:04d}"
        text = f"SYNTHETIC field observation {ident}"
        with patch.object(history, "_now_iso", return_value=stamp):
            history.store_message(
                actor,
                uid,
                "human",
                text,
                turn_id=ident,
                completion="received",
                project_id=project,
            )
            history.store_message(
                actor,
                uid,
                "ai",
                "Receipt noted.",
                turn_id=ident,
                completion="complete",
                project_id=project,
            )
        if day % 3 == 0:
            memory.add_character_memory(
                actor,
                text,
                scope_level="project",
                project_id=project,
                history_uid=uid,
                evidence={
                    "character_id": actor,
                    "turn_id": ident,
                    "observed_at": stamp,
                },
            )
        assert idx.search(actor, ident, project_id=project), ident
    print(
        json.dumps(
            {"first_day": start, "last_day": end - 1, "written_turns": end - start}
        )
    )


def rehearse(output, scratch):
    from open_llm_vtuber.memory_maintenance import (
        backup,
        restore,
        backfill,
        rebuild_copy,
    )
    from open_llm_vtuber import character_memory_manager as memory
    from open_llm_vtuber.conversation_history_index import ConversationHistoryIndex

    root = scratch / "original"
    root.mkdir()
    os.environ["KURO_MEMORY_ROOT"] = str(root / "memories")
    os.environ["KURO_MEMORY_ENCODER_DIR"] = ""
    workers = []
    start = time.perf_counter()
    for a, b in ((0, 90), (90, 180), (180, 270), (270, 366)):
        raw = subprocess.check_output(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                "--write",
                str(a),
                str(b),
            ],
            cwd=root,
        )
        workers.append(json.loads(raw))
    original = inventory(root)
    os.chdir(root)
    dry = backfill("a", project="orchid")
    assert inventory(root) == original
    cnt = {}
    for actor in ("a", "b"):
        for project in ("orchid", "maple"):
            applied = backfill(actor, project=project, apply=True)
            assert (
                applied["failed"] == 0
                and backfill(actor, project=project, apply=True) == applied
            )
            cnt[actor + "/" + project] = sum(
                r["eligible_turns"] for r in applied["receipts"].values()
            )
    assert sum(cnt.values()) == 366
    archive = scratch / "version.zip"
    saved = backup(root, archive)
    after = scratch / "restored"
    restore(archive, after)
    assert inventory(after) == original
    # Include the first post-cutover write in the rollback candidate.
    os.chdir(after)
    os.environ["KURO_MEMORY_ROOT"] = str(after / "memories")
    memory.add_character_memory(
        "b", "post-cutover sentinel", scope_level="project", project_id="orchid"
    )
    corrupt = after / "memories/conversation_history.sqlite3"
    corrupt.write_bytes(b"isolated damaged index")
    before_repair = inventory(after)
    rollback = scratch / "recovered"
    repaired = rebuild_copy(after, rollback, ["a", "b"], projects=["orchid", "maple"])
    assert repaired["published"] and inventory(rollback) == before_repair
    os.chdir(rollback)
    os.environ["KURO_MEMORY_ROOT"] = str(rollback / "memories")
    index = ConversationHistoryIndex()
    assert index.search("a", "d0000", project_id="orchid")
    assert not index.search("a", "d0000", project_id="maple")
    assert memory.list_character_memories(
        "a", project_id="orchid", query_text="post-cutover"
    )
    assert not memory.list_character_memories(
        "a", project_id="maple", query_text="post-cutover"
    )
    with closing(index._connect()) as db:
        rows = dict(
            db.execute("SELECT role,count(*) FROM conversation_messages GROUP BY role")
        )
    assert rows["human"] == rows["ai"] == rows["episode"] == 366
    output.write_text(
        json.dumps(
            dict(
                workers=workers,
                elapsed_seconds=time.perf_counter() - start,
                simulated_days=366,
                scope_counts=cnt,
                dry_run_sources=dry["sources"],
                source_manifest=original,
                initial_archive=saved,
                repaired=repaired,
                derived_rows=rows,
                post_cutover_retained=True,
                original_unchanged=inventory(root) == original,
                rollback_mode="current compatible canonical owner with lexical retrieval",
                formal=False,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if sys.argv[1] == "--write":
        produce(int(sys.argv[2]), int(sys.argv[3]))
    else:
        output = Path(sys.argv[1]).resolve()
        previous = Path.cwd()
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            try:
                rehearse(output, Path(tmp))
            finally:
                os.chdir(previous)
