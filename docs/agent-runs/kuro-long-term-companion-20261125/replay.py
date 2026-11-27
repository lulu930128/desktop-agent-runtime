"""Synthetic History read-path benchmark. Pass the destination receipt as argv[1]."""

import hashlib
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if "--baseline" in sys.argv:
    import subprocess
    from quality_replay import BASE, MODULE

    with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
        for module in (
            "__init__",
            "conversation_history_index",
            "chat_history_manager",
            "character_memory_repository",
            "character_memory_retriever",
            "character_memory_lifecycle",
            "mcpp/privacy",
        ):
            path = Path(scratch) / "open_llm_vtuber" / (module + ".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                subprocess.check_output(
                    ["git", "show", BASE + ":" + MODULE + "/" + module + ".py"],
                    cwd=ROOT,
                )
            )
        subprocess.run(
            [sys.executable, "-B", __file__, sys.argv[1]],
            env=dict(os.environ, PYTHONHASHSEED="0", KURO_BENCH_SOURCE=scratch),
            check=True,
        )
    sys.exit(0)
sys.path.insert(
    0, os.environ.get("KURO_BENCH_SOURCE", str(ROOT / "Open-LLM-VTuber/src"))
)
from open_llm_vtuber.conversation_history_index import ConversationHistoryIndex

CASES = [("azurite", {17}), ("藍銅礦", {17}), ("unobtainium", set())]


def measure(size):
    owner = Path("chat_history/synthetic")
    owner.mkdir(parents=True)
    digest = hashlib.sha256()
    for start in range(0, size, 1000):
        messages = [
            {
                "role": "human",
                "timestamp": "2026-01-01T08:00:00+08:00",
                "content": "azurite specimen weighs 37 grams"
                if i == 17
                else f"inventory item {i}",
            }
            for i in range(start, start + 1000)
        ]
        payload = json.dumps(messages).encode()
        (owner / f"{start}.json").write_bytes(payload)
        digest.update(payload)
    index = ConversationHistoryIndex(Path("derived.sqlite3"))
    started = time.perf_counter()
    try:
        index.sync("synthetic")
    except sqlite3.Error as exc:
        return {
            "messages": size,
            "corpus_sha256": digest.hexdigest(),
            "error": str(exc),
            "seconds_to_failure": time.perf_counter() - started,
        }
    cold = time.perf_counter() - started
    queries = []
    durations = []
    for query, gold in CASES:
        for repeat in range(2):
            changes = []
            connect = index._connect

            def observed_connect():
                conn = connect()
                conn.set_trace_callback(
                    lambda sql: changes.append(1)
                    if sql.lstrip().startswith(
                        (
                            "INSERT OR REPLACE INTO conversation_messages",
                            "DELETE FROM conversation_messages ",
                            "INSERT INTO conversation_messages ",
                        )
                    )
                    else None
                )
                return conn

            with (
                patch.object(index, "_connect", observed_connect),
                patch.object(index, "sync", wraps=index.sync) as sync,
            ):
                started = time.perf_counter()
                hits = index.search("synthetic", query, max_snippets=4)
                elapsed = time.perf_counter() - started
            found = [int(h.history_uid) + h.message_index for h in hits]
            correct = len(gold.intersection(found))
            durations.append(elapsed)
            queries.append(
                dict(
                    query=query,
                    gold=sorted(gold),
                    found=found,
                    recall=correct / len(gold) if gold else None,
                    precision=correct / len(found) if found else None,
                    false_hits=len(found) - correct,
                    seconds=elapsed,
                    sync_calls=sync.call_count,
                    traced_message_mutations=len(changes),
                )
            )
    return dict(
        messages=size,
        corpus_sha256=digest.hexdigest(),
        cold_seconds=cold,
        retrieval_p50_seconds=statistics.median(durations),
        queries=queries,
        bytes=sum(p.stat().st_size for p in Path(".").glob("derived.sqlite3*")),
    )


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    records = []
    previous = Path.cwd()
    for size in (1000, 10000, 100000):
        with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
            try:
                os.chdir(scratch)
                os.environ["KURO_MEMORY_ROOT"] = str(Path(scratch) / "memory")
                records.append(measure(size))
            finally:
                os.chdir(previous)
        output.write_text(
            json.dumps(
                {"model": None, "external_calls": 0, "runs": records},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
