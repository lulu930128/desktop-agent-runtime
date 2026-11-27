"""Opt-in production-prompt replay through native Agent/ToolManager/Executor/MCP.

No GUI/service startup, history writes, refresh, alternative executor or SDK retry.
Only a bounded receipt is saved; credentials, prompts, arguments and replies stay
in memory. Run with --live and a new --output path (maximum four LLM requests).
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

RUNTIME = Path(__file__).resolve().parents[1]
ROOT = RUNTIME.parent
sys.path[:0] = [str(RUNTIME / "src"), str(RUNTIME), str(ROOT)]

from loguru import logger
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_catalog_manager import ToolCatalog, infer_tool_intent
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.tool_schema import SchemaError, schema_digest, validate_arguments
from open_llm_vtuber.mcpp.types import ToolCallObject

QUESTION = "可以幫我查查昨天美股的狀況嗎"
IDENTITY = "omi-search::omi_ask"
HISTORY = RUNTIME / "chat_history/kuro_01/2026-10-31_15-10-37_de8ee45e33db4d5e820c842989f94d51.json"


def shape(value, path="$", depth=0):
    """Only declared-looking field paths and types, never argument values."""
    from open_llm_vtuber.mcpp.tool_schema import _json_type, _DIAGNOSTIC_IDENTIFIER, _SENSITIVE_ARGUMENT_KEY
    rows = [{"path": path, "type": _json_type(value)}]
    if isinstance(value, dict) and depth < 3:
        for key, child in list(value.items())[:24]:
            name = key if _DIAGNOSTIC_IDENTIFIER.fullmatch(key) and not _SENSITIVE_ARGUMENT_KEY.search(key) else "*"
            rows.extend(shape(child, path + "/" + name, depth + 1))
    return rows[:64]


def validation(schema, value):
    try:
        validate_arguments(schema, value)
        return {"status": "PASS"}
    except SchemaError as exc:
        return {"status": "FAIL", "reason": exc.code, "diagnostics": list(exc.diagnostics)}


def source_receipt(raw):
    source = raw.structured_content
    if not isinstance(source, dict):
        source = next((json.loads(text) for text in raw.text_blocks if text.lstrip().startswith("{")), {})
    facts, providers, dates, numbers = [], set(), set(), 0

    def walk(value, path="$", depth=0):
        nonlocal numbers
        if depth > 18:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"provider", "source", "source_id", "dataset"} and isinstance(child, str) and len(child) < 100:
                    providers.add(child)
                if key in {"as_of", "trade_date", "date", "session_date", "event_time", "effective_trade_date"} and isinstance(child, str):
                    dates.add(child[:32])
                if key in {"close", "price", "change_pct", "last", "value", "level"} and type(child) in (int, float):
                    numbers += 1
                if key in {"ok", "request_status", "contract_version", "status", "freshness_status"} and type(child) in (str, bool) and len(facts) < 32:
                    facts.append({"path": path + "/" + key, "value": child})
                walk(child, path + "/" + key, depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value[:100]):
                walk(child, path + "/" + str(index), depth + 1)

    walk(source)
    return {"status": raw.status, "result_received": raw.result_received,
            "is_error": raw.is_error, "reason_code": raw.reason_code,
            "execution_id": raw.execution_id, "canonical": raw.canonical_tool_id,
            "started_at": raw.started_at, "completed_at": raw.completed_at,
            "target": source.get("target"), "facts": facts,
            "source_names": sorted(providers)[:24], "source_dates": sorted(dates)[:24],
            "numeric_market_values": numbers, "result_bytes": len(raw.model_text(limit=8 * 1024 * 1024).encode())}


async def verify(output, max_requests):
    from kuro_launcher.config import load_config
    from kuro_launcher.utils import load_env_file
    from open_llm_vtuber.config_manager import Config, read_yaml
    from open_llm_vtuber.service_context import ServiceContext
    from open_llm_vtuber.live2d_model import Live2dModel
    from open_llm_vtuber.agent.agent_factory import AgentFactory
    from open_llm_vtuber.agent.input_types import BatchInput, TextData, TextSource

    logger.remove()
    for path in (ROOT / ".env", ROOT / ".env.local"):
        load_env_file(path, override=True)
    cfg = load_config(ROOT / "kuro_launcher.settings.yaml")
    config = Config(**read_yaml(str(cfg.runtime_conf_path)))
    os.chdir(RUNTIME)
    intent = infer_tool_intent(QUESTION, "normal")
    receipt = {"observed_at": datetime.now(timezone.utc).isoformat(), "requests": [],
               "max_requests": max_requests, "max_retries": 0,
               "question_codepoints": [hex(ord(c)) for c in QUESTION],
               "question_matches_fixture": QUESTION == "\u53ef\u4ee5\u5e6b\u6211\u67e5\u67e5\u6628\u5929\u7f8e\u80a1\u7684\u72c0\u6cc1\u55ce",
               "market_intent": intent.needs_market_intelligence,
               "formal_runtime": "NOT_STARTED_NOT_RELOADED", "tool_statuses": [],
               "loaded_probe": {"pid": os.getpid(), "executable": sys.executable,
                   "sources": {name: hashlib.sha256((RUNTIME / "src/open_llm_vtuber/mcpp" / (name + ".py")).read_bytes()).hexdigest()
                               for name in ("tool_adapter", "tool_policy_manager", "tool_executor")}}}

    def save():
        output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    assert receipt["question_matches_fixture"] and receipt["market_intent"], "input_encoding_or_intent"
    context = ServiceContext()
    context.system_config, context.character_config = config.system_config, config.character_config
    context.live2d_model = Live2dModel(config.character_config.live2d_model_name)
    system = await context.construct_system_prompt(config.character_config, config.character_config.persona_prompt)
    receipt["prompt"] = {"owner": "ServiceContext.construct_system_prompt", "chars": len(system),
                         "sha256": hashlib.sha256(system.encode()).hexdigest(), "conf_uid": config.character_config.conf_uid,
                         "production_layers": [x for x in ("System Contract", "Runtime Policy", "Character Persona", "Project Context", "Tool Use Policy", "Expression Contract") if x in system]}
    registry = ServerRegistry(RUNTIME / "mcp_servers.json")
    # Determine the actual category candidates without discovering unrelated services.
    catalog = ToolCatalog.load_default()
    catalog_names = [tool["name"] for category in catalog.categories.values() for tool in category.get("tools", [])]
    planned = catalog.route(QUESTION, catalog_names, thinking_power=config.system_config.thinking_power)
    servers = sorted({name.split("::")[0] for name in planned.tool_names})
    assert servers == ["omi-search"], "unexpected_replay_discovery_scope"
    adapter = ToolAdapter(registry)
    mcp_prompt, openai, claude = await adapter.get_tools(servers)
    manager = ToolManager(openai, claude, adapter.get_last_formatted_tools_dict(), thinking_power=config.system_config.thinking_power)
    info = manager.get_tool(IDENTITY)
    receipt["discovery"] = {"complete": adapter.discovery_results["omi-search"].complete,
                            "canonical_digest": info.schema_digest, "provider_digest": info.provider_schema_digest,
                            "schema_errors": adapter.schema_errors, "shared_entrypoint": registry.servers["omi-search"].args[-1]}
    async with MCPClient(registry) as client:
        executor = ToolExecutor(client, manager, thinking_power=config.system_config.thinking_power)
        agent_cfg = config.character_config.agent_config
        agent = AgentFactory.create_agent(
            agent_cfg.conversation_agent_choice, agent_cfg.agent_settings.model_dump(), agent_cfg.llm_configs.model_dump(),
            system, live2d_model=context.live2d_model, system_config=config.system_config.model_dump(),
            tool_manager=manager, tool_executor=executor, mcp_prompt_string=mcp_prompt)
        llm = agent._llm
        assert llm.model == "gpt-5-mini", "unexpected_model"
        llm.client = llm.client.with_options(max_retries=0, timeout=60)
        # Use only history preceding the failing user turn, with native packing.
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
        for row in history:
            if row.get("role") == "human" and row.get("content") == QUESTION:
                break
            if row.get("role") in {"human", "ai", "assistant"} and row.get("content"):
                agent._memory.append({"role": "user" if row["role"] == "human" else "assistant", "content": row["content"]})
        else:
            raise RuntimeError("exact_history_turn_not_found")
        receipt["history"] = {"prior_messages": len(agent._memory), "packed_messages": len(agent._pack_short_term_memory()),
                              "owner": "BasicMemoryAgent._pack_short_term_memory", "full_content_saved": False}
        # Preserve the production speech contract, but do not run TTS or presentation.
        original_completion = llm.chat_completion

        async def observed_completion(messages, system=None, tools=None):
            if len(receipt["requests"]) >= max_requests:
                raise RuntimeError("authorized_llm_budget_exhausted")
            row = {"number": len(receipt["requests"]) + 1, "model": llm.model, "calls": []}
            receipt["requests"].append(row)
            save()
            async for event in original_completion(messages, system, tools=tools):
                if isinstance(event, str) and event.startswith("Error calling the chat endpoint:"):
                    row["api_status"] = "FAIL_no_retry"
                    save()
                    raise RuntimeError("provider_request_failed_no_retry")
                if isinstance(event, list):
                    for call in event:
                        assert isinstance(call, ToolCallObject)
                        canonical = manager.resolve_tool_name(call.function.name)
                        selected_info = manager.get_tool(canonical)
                        args = json.loads(call.function.arguments)
                        prepared = executor._tool_policy.prepare_arguments(canonical, args, selected_info.input_schema)
                        decision = executor.check_call(call.function.name, args, tool_id=call.id)
                        row["calls"].append({"alias": call.function.name, "canonical": canonical,
                            "argument_shape": shape(args), "raw_canonical_validation": validation(selected_info.input_schema, args),
                            "prepared_canonical_validation": validation(selected_info.input_schema, prepared),
                            "provider_validation": validation(selected_info.generic_schema, args),
                            "policy_allowed": decision.allowed, "reason_code": decision.reason_code,
                            "requested_market": (prepared.get("target") or {}).get("market"),
                            "cache_only": prepared.get("realtime_policy") == "cache_only",
                            "no_refresh": prepared.get("refresh_if_missing") is False,
                            "zero_external_fetches": prepared.get("tool_budget", {}).get("max_external_fetches") == 0})
                        save()
                        if canonical != IDENTITY or prepared.get("realtime_policy") != "cache_only" or prepared.get("refresh_if_missing") is not False:
                            raise RuntimeError("model_selected_outside_authorized_cached_omi_probe")
                yield event
            row["api_status"] = "completed"
            save()

        llm.chat_completion = observed_completion
        input_data = BatchInput(texts=[TextData(source=TextSource.INPUT, content=QUESTION)], metadata={"skip_history": True})
        route_text = agent._compose_tool_route_text(QUESTION)
        tools = manager.get_formatted_tools("OpenAI", request_text=route_text)
        receipt["route"] = manager.get_last_route().tool_names
        receipt["all_planned_candidates_available"] = set(planned.tool_names).issubset(set(receipt["route"]))
        reply = ""
        save()
        try:
            async for event in agent._openai_tool_interaction_loop(
                    agent._to_messages(input_data), tools, route_prompt=manager.get_last_route_prompt(), require_tool_evidence=True):
                if isinstance(event, str):
                    reply += event
                elif event.get("type") == "tool_call_status":
                    receipt["tool_statuses"].append({k: event.get(k) for k in ("tool_name", "status", "execution_status", "reason_code")})
                    if event.get("status") in {"completed", "error"} and client.last_call_result:
                        receipt.setdefault("mcp_results", []).append(source_receipt(client.last_call_result))
                    save()
            terms = [term for term in ("美股", "US", "2026-10-30", "10/30", "S&P", "NASDAQ", "Nasdaq", "道瓊", "那斯達克", "partial", "stale", "缺", "過期", "資料") if term in reply]
            receipt["reply"] = {"received": bool(reply), "chars": len(reply), "public_topic_terms": terms,
                                "summary": "模型依本輪 OMI 回傳整理市場狀況；原始回覆未保存。"}
            completed = any(r.get("status") == "completed" and r.get("execution_status") == "succeeded" for r in receipt["tool_statuses"])
            receipt["status"] = "PASS" if completed and reply else "FAIL"
        finally:
            await llm.client.close()
            receipt["canonical_digest_unchanged"] = schema_digest(info.input_schema) == info.schema_digest
            save()
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists() or not destination.parent.is_dir():
        parser.error("Use a new output path in an existing directory.")
    try:
        result = asyncio.run(verify(destination, args.max_requests))
        print(json.dumps({key: result.get(key) for key in ("status", "question_codepoints", "market_intent", "route", "requests", "tool_statuses", "mcp_results", "reply", "canonical_digest_unchanged")}, ensure_ascii=False))
        sys.exit(0 if result["status"] == "PASS" else 1)
    except Exception as exc:
        # Never print provider exceptions, credentials or private payloads.
        print(json.dumps({"status": "UNVERIFIED", "error_type": type(exc).__name__, "receipt": str(destination)}))
        sys.exit(2)
