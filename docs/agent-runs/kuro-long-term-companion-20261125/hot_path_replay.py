"""Read the completed synthetic scale projection; capture real hot queries and their query plans."""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch
from quality_replay import ROOT


def replay(state, expected, output):
    from open_llm_vtuber.conversation_history_index import ConversationHistoryIndex

    baseline = json.loads(expected.read_bytes())["runs"][-1]
    if baseline["messages"] != 100000:
        raise ValueError("100k build has not completed")
    digest = hashlib.sha256()
    paths = sorted(
        (state / "chat_history/scale").glob("*.json"), key=lambda p: int(p.stem)
    )
    for p in paths:
        digest.update(p.read_bytes())
    assert digest.hexdigest() == baseline["corpus_sha256"]
    os.chdir(state)
    os.environ["KURO_MEMORY_ROOT"] = str(state / "memories")
    os.environ["KURO_MEMORY_ENCODER_DIR"] = str(
        ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"
    )
    idx = ConversationHistoryIndex()
    idx.sync("scale")
    real = idx._connect
    mutations = []
    plans = {}
    history_reads = 0
    original_bytes = Path.read_bytes

    def read(p):
        nonlocal history_reads
        if p.parent.name == "scale" and p.suffix == ".json":
            history_reads += 1
        return original_bytes(p)

    def trace(sql):
        s = sql.lstrip().upper()
        if s.startswith(("DELETE ", "INSERT ", "UPDATE ", "REPLACE ")):
            mutations.append(s[:20])
        if "WITH WEIGHTS(TERM,WEIGHT)" in s:
            plans.setdefault("vector", sql)
        if "BM25(CONVERSATION_MESSAGES_FTS)" in s:
            plans.setdefault("fts", sql)

    def connect():
        c = real()
        c.set_trace_callback(trace)
        return c

    results = []
    with (
        patch.object(idx, "_connect", side_effect=connect),
        patch.object(Path, "read_bytes", read),
        patch.object(idx, "sync", side_effect=AssertionError("hot rebuild")),
    ):
        for case in baseline["queries"]:
            start = time.perf_counter()
            hits = idx.search("scale", case["query"], max_snippets=4)
            results.append(
                dict(
                    query=case["query"],
                    seconds=time.perf_counter() - start,
                    sources=[[h.history_uid, h.message_index] for h in hits],
                    strict_hit=any(
                        {
                            "陶芸教室の参加費はいくら？": "陶藝",
                            "What did the pottery workshop cost?": "陶藝",
                            "azurite ceramic admission": "azurite",
                            "庫存出貨": "盤點",
                        }[case["query"]]
                        in hit.content
                        for hit in hits
                    ),
                    pottery_found=any(
                        h.history_uid == "0" and h.message_index in {18, 19}
                        for h in hits
                    ),
                )
            )
    with closing(real()) as c:
        actual = {
            key: [r[3] for r in c.execute("EXPLAIN QUERY PLAN " + sql)]
            for key, sql in plans.items()
        }
    if history_reads or mutations:
        raise AssertionError(
            "Unchanged hot lookup mutated or scanned canonical sources"
        )
    if not any("owner=? AND term=?" in step for step in actual["vector"]):
        raise AssertionError("Semantic query did not seek the indexed posting keys")
    output.write_text(
        json.dumps(
            dict(
                messages=100000,
                vectors=baseline["vectors"],
                corpus_sha256=digest.hexdigest(),
                history_reads=history_reads,
                sqlite_mutations=len(mutations),
                queries=results,
                plans=actual,
                query_p50_seconds=statistics.median(r["seconds"] for r in results),
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "Open-LLM-VTuber/src"))
    replay(*(Path(value).resolve() for value in sys.argv[1:]))
