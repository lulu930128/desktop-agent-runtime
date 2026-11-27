"""Incrementally grow an isolated multilingual corpus and measure the actual local encoder."""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

from quality_replay import ROOT


def peak_working_set():
    if os.name != "nt":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak",
                "current",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError()
    return counters.peak


def measure(output):
    from open_llm_vtuber.conversation_history_index import ConversationHistoryIndex

    index = ConversationHistoryIndex()
    directory = Path("chat_history/scale")
    directory.mkdir(parents=True)
    samples = [
        ("今天盤點了一箱工具。", "收到，尚未出貨。"),
        ("Inventory count finished.", "No shipment yet."),
        ("倉庫の在庫を確認した。", "まだ発送されていません。"),
    ]
    queries = [
        ("陶芸教室の参加費はいくら？", "陶藝"),
        ("What did the pottery workshop cost?", "陶藝"),
        ("azurite ceramic admission", "azurite"),
        ("庫存出貨", "盤點"),
    ]
    sha = hashlib.sha256()
    result = []
    prev = 0
    for size in (1000, 10000, 100000):
        for start in range(prev, size, 1000):
            rows = []
            for i in range(start, start + 1000, 2):
                user, ai = samples[(i // 2) % len(samples)]
                user = (
                    f"{i} " + user
                    if i != 18
                    else "昨天參加 azurite 陶藝課，入場費 37 歐元。"
                )
                for role, content, state in (
                    ("human", user, "received"),
                    ("ai", ai, "complete"),
                ):
                    rows.append(
                        dict(
                            role=role,
                            turn_id=str(i),
                            content=content,
                            completion=state,
                            timestamp="2026-10-01T08:00:00+08:00",
                        )
                    )
            body = json.dumps(rows, ensure_ascii=False).encode()
            (directory / f"{start}.json").write_bytes(body)
            sha.update(body)
        cpu = time.process_time()
        now = time.perf_counter()
        index.sync("scale")
        stage = time.perf_counter() - now
        build_cpu = time.process_time() - cpu
        with closing(index._connect()) as db:
            counts = dict(
                db.execute(
                    "SELECT role,count(*) FROM conversation_messages GROUP BY role"
                )
            )
            vectors = db.execute("SELECT count(*) FROM semantic_vectors").fetchone()[0]
        assert vectors == size // 2 and counts["human"] + counts["ai"] == size, (
            counts,
            vectors,
            size,
        )
        reads = []
        for question, expected in queries:
            for _ in range(2):
                begin = time.perf_counter()
                hits = index.search("scale", question, max_snippets=4)
                reads.append(
                    dict(
                        query=question,
                        seconds=time.perf_counter() - begin,
                        hit=any(expected in hit.content for hit in hits),
                        sources=[[h.history_uid, h.message_index] for h in hits],
                    )
                )
        result.append(
            dict(
                messages=size,
                added=size - prev,
                corpus_sha256=sha.hexdigest(),
                vectors=vectors,
                rows=counts,
                stage_seconds=stage,
                build_cpu_seconds=build_cpu,
                process_peak_bytes=peak_working_set(),
                queries=reads,
                db_bytes=sum(
                    p.stat().st_size
                    for p in index.db_path().parent.glob(
                        "conversation_history.sqlite3*"
                    )
                ),
                query_p50_seconds=statistics.median(r["seconds"] for r in reads),
            )
        )
        output.write_text(
            json.dumps(
                {"runs": result, "network_calls": 0}, indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        prev = size


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "Open-LLM-VTuber/src"))
    output = Path(sys.argv[1]).resolve()
    previous = Path.cwd()
    from contextlib import nullcontext

    if len(sys.argv) == 4 and sys.argv[2] == "--keep-for-analysis":
        scratch_path = Path(sys.argv[3]).resolve()
        scratch_path.mkdir(exist_ok=False)
        workspace = nullcontext(scratch_path)
    else:
        workspace = tempfile.TemporaryDirectory(dir=ROOT)
    with workspace as scratch:
        try:
            os.chdir(scratch)
            os.environ["KURO_MEMORY_ROOT"] = str(Path(scratch) / "memories")
            os.environ["KURO_MEMORY_ENCODER_DIR"] = str(
                ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"
            )
            measure(output)
        finally:
            os.chdir(previous)
