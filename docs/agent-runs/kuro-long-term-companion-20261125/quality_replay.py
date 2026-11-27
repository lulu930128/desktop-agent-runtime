"""Matched local-model replay. No cloud, production ports, private transcripts or deployment."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
BASE = "c2b3e64c27caaec8c2cba5b213444ddce0d79e03"
MODULE = "Open-LLM-VTuber/src/open_llm_vtuber"
MODEL = "qwen2.5:7b"
CASES = [
    ("What did the pottery workshop cost?", "37", "pottery"),
    ("陶芸教室の参加費はいくらでしたか？", "37", "pottery"),
    ("What was the Skylark launch code?", "BETA82", "current"),
    ("What is my dentist's name?", "UNKNOWN", None),
]
HISTORIES = {
    "pottery": [
        ("我昨天參加了陶藝課。學費是 37 歐元，沒有買工具。", "已記下你的經歷。")
    ],
    "current": [("The Skylark launch code was BETA82.", "Understood.")]
    + [(f"Checking inventory shelf {i}.", "Okay.") for i in range(12)],
}


if "--longitudinal" in sys.argv:
    os.environ["KURO_REPLAY_LONGITUDINAL"] = "1"
if os.environ.get("KURO_REPLAY_LONGITUDINAL") == "1":
    HISTORIES.update(
        {
            "booking": [
                ("My Aurora ticket used reference BRIDGE71.", "Receipt noted.")
            ],
            "amount": [
                ("The charge for BRIDGE71 was 58 euros.", "Payment source recorded.")
            ],
            "october": [("My locker combination in October was CEDAR31.", "Noted.")],
            "november": [
                (
                    "I changed my locker combination to ALDER82 in November.",
                    "Previous code superseded.",
                )
            ],
        }
    )
    CASES.extend(
        [
            ("How much was the Aurora ticket?", "58", ["booking", "amount"]),
            ("As of 2026-10-31 what was my locker combination?", "CEDAR31", "october"),
            (
                "What did I change my locker combination to in November?",
                "ALDER82",
                "november",
            ),
            ("What was the refund amount for the Aurora ticket?", "UNKNOWN", None),
        ]
    )


def context(arm):
    from open_llm_vtuber.conversation_history_index import (
        format_past_conversations_for_prompt,
    )

    if arm == "vector":
        from open_llm_vtuber.conversation_history_index import (
            _CONVERSATION_HISTORY_INDEX,
        )

        _CONVERSATION_HISTORY_INDEX.retrieval_mode = "vector"
    for uid, turns in HISTORIES.items():
        rows = []
        for i, (user, assistant) in enumerate(turns):
            for role, content, status in [
                ("human", user, "received"),
                ("ai", assistant, "complete"),
            ]:
                rows.append(
                    dict(
                        role=role,
                        content=content,
                        completion=status,
                        turn_id=f"{uid}-{i}",
                        timestamp="2026-11-03T09:00:00+08:00"
                        if uid == "november"
                        else "2026-10-16T09:00:00+08:00",
                    )
                )
        path = Path("chat_history/actor") / (uid + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    result = []
    for q, expected, source in CASES:
        start = time.perf_counter()
        value = format_past_conversations_for_prompt(
            "actor", q, current_history_uid="current"
        )
        result.append(
            dict(
                query=q,
                context=value,
                seconds=time.perf_counter() - start,
                expected=expected,
                source=source,
            )
        )
    return result


def request(url, payload=None):
    data = json.dumps(payload).encode() if payload else None
    with urllib.request.urlopen(
        urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        ),
        timeout=180,
    ) as r:
        return json.load(r)


def streaming_replay(endpoint, receipt, source, output):
    measured = json.loads(source.read_bytes())
    for key in ("dataset_sha256", "model", "manifest_sha256", "options"):
        if measured[key] != receipt[key]:
            raise ValueError("Unmatched streaming replay " + key)
    receipt["contexts_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    instruction = "Answer using only the supplied history. Return the requested number or code only. If missing return UNKNOWN."
    request(
        endpoint + "/api/generate",
        dict(
            model=MODEL,
            prompt="warm",
            stream=False,
            options={**receipt["options"], "num_predict": 1},
        ),
    )
    records = receipt["observations"] = []
    for index in range(len(measured["arms"]["baseline"])):
        for arm in ("baseline", "hybrid") if index % 2 == 0 else ("hybrid", "baseline"):
            item = measured["arms"][arm][index]
            payload = dict(
                model=MODEL,
                stream=True,
                options=receipt["options"],
                messages=[
                    dict(role="system", content=instruction + "\n" + item["context"]),
                    dict(role="user", content=item["query"]),
                ],
            )
            first = None
            started = time.perf_counter()
            req = urllib.request.Request(
                endpoint + "/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as response:
                for line in response:
                    chunk = json.loads(line)
                    if first is None and chunk.get("message", {}).get("content"):
                        first = time.perf_counter() - started
                    if chunk.get("done"):
                        break
            if first is None or not chunk.get("done"):
                raise RuntimeError("Incomplete model stream")
            records.append(
                dict(
                    arm=arm,
                    case=index,
                    first_text_seconds=first,
                    completion_seconds=time.perf_counter() - started,
                    prompt_tokens=chunk.get("prompt_eval_count"),
                    output_tokens=chunk.get("eval_count"),
                )
            )
    receipt.pop("arms")
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")


def run(output, scratch, *, qt_only=False, swap=False):
    baseline = scratch / "source"
    for module in (
        "__init__",
        "conversation_history_index",
        "chat_history_manager",
        "character_memory_repository",
        "character_memory_retriever",
        "character_memory_lifecycle",
        "mcpp/privacy",
    ):
        path = baseline / "open_llm_vtuber" / (module + ".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            subprocess.check_output(
                ["git", "show", BASE + ":" + MODULE + "/" + module + ".py"], cwd=ROOT
            )
        )
    # Only copy the public model's manifest and content-addressed blobs into the owned sandbox.
    source = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama/models"))
    manifest = Path("manifests/registry.ollama.ai/library/qwen2.5/7b")
    target = scratch / "models"
    (target / "blobs").mkdir(parents=True)
    models = [manifest]
    alternate = "qwen3.5:9b-q4_K_M"
    if swap:
        models.append(manifest.parents[1] / "qwen3.5/9b-q4_K_M")
    for item in models:
        (target / item).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / item, target / item)
        desc = json.loads((target / item).read_bytes())
        for layer in [desc["config"], *desc["layers"]]:
            name = layer["digest"].replace(":", "-")
            if not (target / "blobs" / name).exists():
                shutil.copyfile(source / "blobs" / name, target / "blobs" / name)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}"
    env = dict(
        os.environ,
        PYTHONHASHSEED="0",
        OLLAMA_HOST=endpoint,
        OLLAMA_MODELS=str(target),
        OLLAMA_NO_CLOUD="1",
        OLLAMA_NOPRUNE="1",
        CUDA_VISIBLE_DEVICES="-1",
        USERPROFILE=str(scratch),
        HOME=str(scratch),
        APPDATA=str(scratch),
        LOCALAPPDATA=str(scratch),
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    server = subprocess.Popen(
        [shutil.which("ollama"), "serve"],
        env=env,
        cwd=scratch,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    receipt = dict(
        model=MODEL,
        manifest_sha256=hashlib.sha256((target / manifest).read_bytes()).hexdigest(),
        dataset_sha256=hashlib.sha256(
            json.dumps([HISTORIES, CASES], sort_keys=True).encode()
        ).hexdigest(),
        options=dict(
            seed=17,
            temperature=0,
            num_predict=32,
            num_gpu=0,
            num_thread=4,
            num_ctx=2048,
        ),
        arms={},
    )
    try:
        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError("isolated model server exited")
            try:
                version = request(endpoint + "/api/version")
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("isolated server unavailable")
        receipt["ollama"] = version
        if "--stream-from" in sys.argv:
            streaming_replay(
                endpoint,
                receipt,
                Path(sys.argv[sys.argv.index("--stream-from") + 1]),
                output,
            )
            return
        if qt_only or swap:
            env.update(
                KURO_MEMORY_ENCODER_DIR=str(
                    ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"
                ),
                QT_QPA_PLATFORM="offscreen",
                LOGURU_LEVEL="WARNING",
                PYTHONIOENCODING="utf-8",
            )
            harness = [
                sys.executable,
                "-B",
                str(Path(__file__).with_name("qt_runtime_replay.py")),
                endpoint,
            ]
            if swap:
                results = []
                for phase, model_name, model_manifest in zip(
                    ("save", "read"), (MODEL, alternate), models
                ):
                    phase_output = scratch / (phase + ".json")
                    subprocess.run(
                        [*harness, str(phase_output)],
                        cwd=scratch,
                        env=dict(
                            env, KURO_REPLAY_PHASE=phase, KURO_REPLAY_MODEL=model_name
                        ),
                        check=True,
                        timeout=300,
                    )
                    results.append(
                        dict(
                            model=model_name,
                            manifest=hashlib.sha256(
                                (target / model_manifest).read_bytes()
                            ).hexdigest(),
                            **json.loads(phase_output.read_bytes()),
                        )
                    )
                output.write_text(
                    json.dumps(
                        {"processes": results, "ollama": version},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return
            subprocess.run(
                [*harness, str(output)], cwd=scratch, env=env, check=True, timeout=180
            )
            return
        if "--reuse-baseline" in sys.argv:
            old_path = Path(sys.argv[sys.argv.index("--reuse-baseline") + 1])
            old = json.loads(old_path.read_bytes())
            if any(
                old.get(k) != receipt[k]
                for k in (
                    "dataset_sha256",
                    "model",
                    "manifest_sha256",
                    "options",
                    "ollama",
                )
            ):
                raise ValueError("Unmatched model baseline")
            receipt["arms"]["baseline"] = old["arms"]["baseline"]
            receipt["reused_baseline_sha256"] = hashlib.sha256(
                old_path.read_bytes()
            ).hexdigest()
        for arm, source_path in [
            ("baseline", baseline),
            ("lexical", ROOT / MODULE.rsplit("/", 1)[0]),
            ("vector", ROOT / MODULE.rsplit("/", 1)[0]),
            ("hybrid", ROOT / MODULE.rsplit("/", 1)[0]),
        ]:
            if arm in receipt["arms"]:
                continue
            directory = scratch / arm
            directory.mkdir()
            env.update(
                PYTHONPATH=str(source_path),
                KURO_MEMORY_ROOT=str(directory / "memories"),
                KURO_MEMORY_ENCODER_DIR=str(
                    ROOT / "Open-LLM-VTuber/cache/companion-e8f8c211"
                )
                if arm in {"vector", "hybrid"}
                else "",
                PYTHONIOENCODING="utf-8",
            )
            contexts = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).resolve()),
                        "--context",
                        arm,
                    ],
                    cwd=directory,
                    env=env,
                ).decode("utf-8")
            )
            cases = receipt["arms"][arm] = []
            for item in contexts:
                instruction = "Answer using only the supplied history. Return the requested number or code only. If missing return UNKNOWN."
                payload = dict(
                    model=MODEL,
                    stream=False,
                    options=receipt["options"],
                    messages=[
                        dict(
                            role="system", content=instruction + "\n" + item["context"]
                        ),
                        dict(role="user", content=item["query"]),
                    ],
                )
                r = request(endpoint + "/api/chat", payload)
                answer = r["message"]["content"].strip()
                spans = [
                    line
                    for line in item["context"].splitlines()
                    if line.startswith("- [history=")
                ]
                sources = (
                    item["source"]
                    if isinstance(item["source"], list)
                    else [item["source"]]
                )
                located = {
                    source
                    for source in sources
                    if any(
                        ("history=" + str(source) + " ") in line
                        and (len(sources) > 1 or item["expected"] in line)
                        for line in spans
                    )
                }
                relevant = sum(
                    any(
                        ("history=" + str(source) + " ") in line
                        and (len(sources) > 1 or item["expected"] in line)
                        for source in sources
                    )
                    for line in spans
                )
                # Classification uses exact source membership, with a separate answer score.
                cases.append(
                    dict(
                        **item,
                        answer=answer,
                        exact=answer == item["expected"],
                        recall=len(located) / len(sources) if item["source"] else None,
                        precision=relevant / len(spans) if spans else None,
                        false_answer=answer not in {item["expected"], "UNKNOWN"},
                        model_prompt_tokens=r.get("prompt_eval_count"),
                        model_output_tokens=r.get("eval_count"),
                        model_total_ms=r["total_duration"] / 1e6,
                    )
                )
                output.write_text(
                    json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8"
                )
    finally:
        server.terminate()
        server.wait(timeout=30)


if __name__ == "__main__":
    if sys.argv[1] == "--context":
        print(json.dumps(context(sys.argv[2]), ensure_ascii=False))
    else:
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            run(
                Path(sys.argv[1]).resolve(),
                Path(tmp),
                qt_only="--qt-only" in sys.argv[2:],
                swap="--swap" in sys.argv[2:],
            )
