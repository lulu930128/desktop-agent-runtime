"""Run Kuro's chat entry with its configured real model and a persistent, isolated Japanese Study owner."""
import asyncio
from contextlib import nullcontext
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "kuro-real-api-20261123"))
from isolated_writes import study_hub
from live import RT, ROOT, ServerRegistry, ToolAdapter, ToolManager, MCPClient, ToolExecutor, BasicMemoryAgent, yaml
from open_llm_vtuber.agent.input_types import BatchInput, TextData, TextSource
from open_llm_vtuber.agent.stateless_llm_factory import LLMFactory
from open_llm_vtuber.config_manager.utils import validate_config
from open_llm_vtuber.service_context import ServiceContext
from open_llm_vtuber.live2d_model import Live2dModel

def now():
    return datetime.now(timezone.utc).isoformat()

async def main(personal_read_only=False, particle_fixture=False):
    assert not (personal_read_only and particle_fixture)
    run_id = uuid.uuid4().hex
    data = ROOT / ".git" / "kuro-production-tools-20261123" / "teacher-test-hub" / run_id
    data.mkdir(parents=True, exist_ok=False)
    receipt = HERE / (("teacher-live-read-" if personal_read_only else "teacher-test-") + run_id + ".json")
    record = {"started": now(), "scope": "separate agent process, real configured Responses API, persistent test Hub", "test_store": str(data.relative_to(ROOT)), "requests": [], "turns": []}

    if personal_read_only:
        record.update(scope="separate Kuro agent, production Japanese MCP, read-only personal learner")

    def save():
        tmp = receipt.with_suffix(".part")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf8")
        tmp.replace(receipt)

    os.chdir(RT)
    cfg = yaml.safe_load((RT / "conf.launcher_runtime.yaml").read_text(encoding="utf-8-sig"))
    role = validate_config(cfg)
    cc = role.character_config
    ac = cfg["character_config"]["agent_config"]
    settings = ac["agent_settings"]["basic_memory_agent"]
    provider = settings["llm_provider"]
    llm = LLMFactory.create_llm(provider, **ac["llm_configs"][provider])
    assert llm._uses_responses and str(llm.client.base_url).rstrip("/") == "https://api.openai.com/v1"
    llm.client.max_retries = 0
    record.update(model=llm.model, effort=llm._responses_reasoning_effort)
    save()
    async def sdk_response(response):
        record["requests"].append({"time": now(), "status": response.status_code, "request_id": response.headers.get("x-request-id")})
        save()
    llm.client._client.event_hooks["response"].append(sdk_response)
    try:
        hub = nullcontext(None) if personal_read_only else study_hub(ROOT.parent / "japanese-study-hub", "JSTUDY", data)
        with hub as url:
            if personal_read_only:
                registry = ServerRegistry(RT / "mcp_servers.json")
            else:
                fixture_policy = {"operation_id": "test-policy-" + run_id, "actor": "Kuro acceptance", "policy": {"practice": {"auto_record_completed_practice": True}}}
                with urlopen(Request(url + "/api/v1/learner-policy", method="PUT", data=json.dumps(fixture_policy).encode(), headers={"Content-Type": "application/json"})) as resp:
                    assert json.load(resp)["persisted"]
                if particle_fixture:
                    stamp = now()
                    seed = {"schema_version": 1, "practice_contract_version": 2, "submission_id": "seed-submit-" + run_id,
                            "session": {"session_id": "seed-session-" + run_id, "title": "Isolated particle baseline", "source": "fixture",
                                        "practice_type": "grammar", "requested_level": "N3", "started_at": stamp, "completed_at": stamp},
                            "questions": [{"question_key": "seed-q1", "position": 1, "snapshot": {"schemaVersion": 1, "language": "ja", "questionType": "cloze", "prompt": "本（　）読む。"},
                                           "response": {"answer": {"text": "が"}, "answer_result": "wrong", "awarded_points": 0, "submitted_at": stamp,
                                                        "diagnosis_events": [{"code": "particle_ga_wo_confusion"}]}}]}
                    for endpoint in ("/api/v1/practice/submissions/preview", "/api/v1/practice/submissions"):
                        with urlopen(Request(url + endpoint, data=json.dumps(seed).encode(), headers={"Content-Type": "application/json"})) as resp:
                            assert json.load(resp)["ok"]
                # The production HTTP adapter must never receive synthetic answers.
                entry = ROOT.parent.parent / "GPT_MCPtool/japanese_study/dist/src/index.js"
                assert entry.is_file() and url.startswith("http://127.0.0.1:") and not url.endswith(":18791")
                config = {"command": "node", "args": [str(entry)], "env": {"JSTUDY_HUB_BASE_URL": url}}
                record["test_transport"] = {"type": "stdio", "owner": str(entry), "test_hub": url}
                path = data / "test-registry.json"
                path.write_text(json.dumps({"mcp_servers": {"japanese-study": config}}), encoding="utf8")
                registry = ServerRegistry(path)
            adapter = ToolAdapter(registry)
            _, openai, claude = await adapter.get_tools(["japanese-study"])
            manager = ToolManager(openai, claude, adapter.get_last_formatted_tools_dict())
            manager.bind_discovery(adapter, ["japanese-study"])
            assert "japanese-study::study_get_learner_policy" in manager.tools, "test MCP discovery failed"
            ctx = ServiceContext()
            ctx.system_config = role.system_config
            ctx.live2d_model = Live2dModel(cc.live2d_model_name)
            prompt = await ctx.construct_system_prompt(cc, cc.persona_prompt)
            assert "【日文語練習】" in prompt
            async with MCPClient(registry) as client:
                # Observe exact wire arguments locally only for this synthetic learner.
                record["calls"] = []
                original_call = client.call_tool
                async def observe_call(server_name, tool_name, tool_args, **kwargs):
                    if personal_read_only and (server_name != "japanese-study" or tool_name not in {"study_get_learning_context", "study_get_learner_policy"}):
                        raise RuntimeError("Outside personal learner read-only sample")
                    record["calls"].append({"tool": tool_name, "arguments": tool_args, "schema_sha256": kwargs.get("expected_schema_digest")})
                    save()
                    actual = await original_call(server_name, tool_name, tool_args, **kwargs)
                    if tool_name == "study_get_learning_context" and isinstance(actual.structured_content, dict):
                        context = actual.structured_content
                        record["learning_context"] = {
                            "weakness_codes": [event.get("code") or event.get("diagnosis_code") for event in context.get("recent_diagnoses", []) if event.get("polarity") == "weakness"],
                            "skill_keys": sorted({str(event["skill_key"]) for event in context.get("recent_diagnoses", []) if event.get("skill_key")}),
                            "recommended_targets": len(context.get("recommended_targets", [])),
                        }
                    return actual
                client.call_tool = observe_call
                agent = BasicMemoryAgent(llm, prompt, ctx.live2d_model, use_mcpp=True, tool_manager=manager, tool_executor=ToolExecutor(client, manager))
                async def chat(text):
                    turn = {"input": text, "events": [], "display": "", "time": now()}
                    record["turns"].append(turn)
                    request = BatchInput(texts=[TextData(TextSource.INPUT, text)])
                    async for item in agent.chat(request):
                        if hasattr(item, "display_text"):
                            turn["display"] += item.display_text.text
                        elif isinstance(item, dict) and item.get("type") == "tool_call_status":
                            fields = ("tool_name","tool_id","outcome","reason_code","status","call_summary","practice_readback")
                            row = {key: item[key] for key in fields if key in item}
                            if personal_read_only:
                                row["content_sha256"] = hashlib.sha256(str(item.get("content", "")).encode()).hexdigest()
                            else:
                                row["content"] = item.get("content")
                            turn["events"].append(row)
                        save()
                    turn["end"] = now()
                    save()
                    return turn
                first = await chat("今天做一輪日文。這次只要兩題，第一題練我剛才的助詞弱點，第二題中翻日。" if particle_fixture else "今天做一輪日文")
                count = 2 if particle_fixture else 5
                match = re.search(r"【日文語練習｜(jp-[a-z0-9-]+)】", first["display"])
                assert match and all("Q" + str(i) in first["display"] for i in range(1, count + 1)), "missing stable five-question snapshot"
                def successes(turn):
                    return [event["tool_name"] for event in turn["events"] if event.get("outcome") == "actual_success"]
                assert all("japanese-study::" + name in successes(first) for name in ("study_get_learning_context", "study_get_learner_policy"))
                record["session_id"] = match[1]
                if personal_read_only:
                    record["five_questions_after_owner_reads"] = True
                    return
                async def test_answer(name):
                    # The operator answers THIS generated snapshot in the isolated test learner.
                    path = data / name
                    while not path.is_file():
                        await asyncio.sleep(1)
                    return path.read_text(encoding="utf-8").strip()
                second = await chat(await test_answer("partial.txt"))
                assert not any("record_practice" in name for name in successes(second))
                final = await chat(await test_answer("complete.txt"))
                names = successes(final)
                expected = ["japanese-study::study_" + s for s in ("preview_practice_record", "record_practice", "get_practice_session")]
                cursor = -1
                for name in expected:
                    cursor = names.index(name, cursor + 1)
                row = next(e for e in reversed(final["events"]) if e.get("tool_name") == expected[-1] and e.get("outcome") == "actual_success")
                assert match[1] in row["content"]
                with urlopen(url + "/api/v1/practice/sessions/" + match[1]) as response:
                    readback = json.load(response)
                record["owner_readback"] = readback
                save()
                assert len(readback.get("questions", readback.get("session", {}).get("questions", []))) == count
                record["model_loop_completed"] = True
    except Exception as exc:
        record["failure"] = {"type": type(exc).__name__, "reason": str(exc)[:380]}
        raise
    finally:
        record["end"] = now()
        save()
        await llm.client.close()
    print(receipt.name)

if __name__ == "__main__":
    asyncio.run(main(personal_read_only="--personal-read-only" in sys.argv, particle_fixture="--particle-fixture" in sys.argv))
