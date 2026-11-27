"""Noncommercial LoCoMo retrieval evaluation. Original dialogue stays in the temporary sandbox.
Adyasha Maharana et al., Evaluating Very Long-Term Conversational Memory of LLM Agents (ACL 2024).
https://github.com/snap-research/locomo — CC BY-NC 4.0. No images or external model calls.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.request
from quality_replay import ROOT, BASE, MODULE
import subprocess

REV = "3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376"
URL = f"https://raw.githubusercontent.com/snap-research/locomo/{REV}/data/locomo10.json"


def evaluate(samples):
    from open_llm_vtuber.conversation_history_index import ConversationHistoryIndex

    results = []
    for sample in samples:
        actor = sample["sample_id"]
        convo = sample["conversation"]
        source_map = {}
        directory = Path("chat_history") / actor
        directory.mkdir(parents=True)
        for session, turns in convo.items():
            if not re.fullmatch(r"session_\d+", session):
                continue
            rows = []
            for i, turn in enumerate(turns):
                role = "human" if turn["speaker"] == convo["speaker_a"] else "ai"
                uid = f"{session}-{i if role == 'human' else i - 1}"
                rows.append(
                    dict(
                        role=role,
                        content=turn["speaker"] + ": " + turn["text"],
                        turn_id=uid,
                        completion="received" if role == "human" else "complete",
                        timestamp=convo.get(session + "_date_time", ""),
                    )
                )
                source_map[session, i] = turn["dia_id"]
            (directory / (session + ".json")).write_text(
                json.dumps(rows), encoding="utf-8"
            )
        index = ConversationHistoryIndex()
        for qid, q in enumerate(sample["qa"]):
            gold = set(q.get("evidence") or []) & set(source_map.values())
            if not gold:
                results.append(
                    dict(sample=actor, id=qid, category=q["category"], scored=False)
                )
                continue
            start = time.perf_counter()
            hits = index.search(actor, q["question"], max_snippets=4, token_budget=520)
            found = set()
            for hit in hits:
                span = getattr(hit, "source_span", ())
                ids = range(span[0], span[-1] + 1) if span else [hit.message_index]
                found.update(source_map[hit.history_uid, i] for i in ids)
            overlap = gold & found
            results.append(
                dict(
                    sample=actor,
                    id=qid,
                    category=q["category"],
                    gold=sorted(gold),
                    found=sorted(found),
                    recall=len(overlap) / len(gold),
                    precision=len(overlap) / len(found) if found else 0,
                    seconds=time.perf_counter() - start,
                    scored=True,
                )
            )
    return results


if __name__ == "__main__":
    if sys.argv[1] == "--arm":
        samples = json.loads(Path(sys.argv[2]).read_bytes())
        Path(sys.argv[3]).write_text(json.dumps(evaluate(samples)), encoding="utf-8")
    else:
        output = Path(sys.argv[1]).resolve()
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            scratch = Path(tmp)
            corpus = scratch / "locomo10.json"
            corpus.write_bytes(urllib.request.urlopen(URL, timeout=30).read())
            base = scratch / "base"
            for name in (
                "__init__",
                "conversation_history_index",
                "chat_history_manager",
                "character_memory_repository",
                "character_memory_retriever",
                "character_memory_lifecycle",
                "mcpp/privacy",
            ):
                path = base / "open_llm_vtuber" / (name + ".py")
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_bytes(
                    subprocess.check_output(
                        ["git", "show", f"{BASE}:{MODULE}/{name}.py"], cwd=ROOT
                    )
                )
            record = dict(
                corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
                revision=REV,
                license="CC BY-NC 4.0",
                hash_seed=0,
                baseline=BASE,
                arms={},
            )
            if "--reuse-baseline" in sys.argv:
                old_path = Path(sys.argv[sys.argv.index("--reuse-baseline") + 1])
                old = json.loads(old_path.read_bytes())
                if any(
                    old.get(k) != record[k]
                    for k in ("corpus_sha256", "revision", "hash_seed", "baseline")
                ):
                    raise ValueError("Unmatched baseline receipt")
                record["arms"]["original"] = old["arms"]["original"]
                record["reused_original_receipt"] = hashlib.sha256(
                    old_path.read_bytes()
                ).hexdigest()
            for arm, src in [
                ("original", base),
                ("hybrid", ROOT / "Open-LLM-VTuber/src"),
            ]:
                if arm in record["arms"]:
                    continue
                directory = scratch / arm
                directory.mkdir()
                receipt = directory / "results.json"
                env = dict(
                    os.environ,
                    PYTHONHASHSEED="0",
                    PYTHONPATH=str(src),
                    KURO_MEMORY_ROOT=str(directory / "memories"),
                    KURO_MEMORY_ENCODER_DIR=str(
                        ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"
                    )
                    if arm == "hybrid"
                    else "",
                )
                subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).resolve()),
                        "--arm",
                        str(corpus),
                        str(receipt),
                    ],
                    cwd=directory,
                    env=env,
                    check=True,
                )
                record["arms"][arm] = json.loads(receipt.read_bytes())
                output.write_text(
                    json.dumps(record, separators=(",", ":")), encoding="utf-8"
                )
