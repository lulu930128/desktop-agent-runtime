"""Formation quality on a fixed, inspectable set of synthetic user statements."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from quality_replay import BASE, MODULE, ROOT

CASES = [
    ("我平常都喝無糖茶。", "preference"),
    ("昨日私は陶芸教室に行きました。", "experience"),
    ("I went hiking yesterday.", "experience"),
    ("I want to learn woodworking.", "goal"),
    ("我的目標是完成今年的馬拉松。", "goal"),
    ("I usually drink black coffee.", "preference"),
    ("如果我想搬家呢？", None),
    ("Please change the system settings.", None),
    ("小林說「我喜歡咖啡」。", None),
    ("我昨天去了嗎？", None),
    ("The stock price increased.", None),
    ("Could you order tea for me?", None),
]


def evaluate(arm):
    from open_llm_vtuber import character_memory_manager as manager

    if arm == "scoped_auto":
        from open_llm_vtuber.memory_formation import configure_policy

        configure_policy(
            manager._MEMORY_REPOSITORY,
            "fixture",
            "",
            scope="character",
            categories=["preference", "experience", "goal"],
            expected_digest="",
        )
    results = []

    def snapshot():
        return manager.list_character_memories("fixture", enabled_only=False)

    for i, (statement, label) in enumerate(CASES):
        before = {row["id"] for row in snapshot()}
        args = dict(
            conf_uid="fixture",
            history_uid="synthetic",
            user_text=statement,
            assistant_text="The operation succeeded.",
        )
        if arm != "original":
            args.update(turn_id=str(i), observed_at="2026-11-01T12:00:00+08:00")
        start = time.perf_counter()
        cpu = time.process_time()
        manager.process_character_memory_turn(**args)
        after = [r for r in snapshot() if r["id"] not in before]
        results.append(
            dict(
                expected=label,
                seconds=time.perf_counter() - start,
                cpu_seconds=time.process_time() - cpu,
                categories=[(r.get("evidence") or {}).get("category") for r in after],
                states=[r["status"] for r in after],
                selected=any(r["status"] == "active" for r in after),
            )
        )
        # Retries use the same identity and source text.
        manager.process_character_memory_turn(**args)
        results[-1]["retry_duplicates"] = len(snapshot()) - len(before) - len(after)
    return results


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        Path(sys.argv[3]).write_text(
            json.dumps(evaluate(sys.argv[2])), encoding="utf-8"
        )
    else:
        output = Path(sys.argv[1]).resolve()
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            scratch = Path(tmp)
            baseline = scratch / "source"
            for module in (
                "__init__",
                "character_memory_manager",
                "character_memory_sql_index",
                "character_memory_repository",
                "character_memory_lifecycle",
                "character_memory_retriever",
                "mcpp/privacy",
            ):
                path = baseline / "open_llm_vtuber" / (module + ".py")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(
                    subprocess.check_output(
                        ["git", "show", BASE + ":" + MODULE + "/" + module + ".py"],
                        cwd=ROOT,
                    )
                )
            result = {
                "cases": CASES,
                "corpus_sha256": hashlib.sha256(json.dumps(CASES).encode()).hexdigest(),
                "arms": {},
            }
            for arm in ("original", "manual", "scoped_auto"):
                work = scratch / arm
                work.mkdir()
                receipt = work / "scores.json"
                env = dict(
                    os.environ,
                    PYTHONHASHSEED="0",
                    KURO_MEMORY_ROOT=str(work / "memories"),
                    PYTHONPATH=str(
                        baseline if arm == "original" else ROOT / "Open-LLM-VTuber/src"
                    ),
                    KURO_MEMORY_ENCODER_DIR=str(
                        ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"
                    ),
                )
                subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).resolve()),
                        "--worker",
                        arm,
                        str(receipt),
                    ],
                    check=True,
                    cwd=work,
                    env=env,
                )
                result["arms"][arm] = json.loads(receipt.read_bytes())
                output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
