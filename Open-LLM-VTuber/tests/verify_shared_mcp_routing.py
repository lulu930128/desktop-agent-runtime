"""Opt-in native MCP read probe; no GUI launch, refresh, writes or API retries."""
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
from open_llm_vtuber.mcpp.server_registry import ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor
from open_llm_vtuber.mcpp.tool_schema import (
    SchemaError, validate_arguments, schema_digest, _json_type,
    _DIAGNOSTIC_IDENTIFIER, _SENSITIVE_ARGUMENT_KEY,
)
from open_llm_vtuber.mcpp.types import ToolCallObject

QUESTION = "可以幫我看看昨天美股的大致狀況嗎"
SERVERS = ("japanese-study", "english-study", "listening-audio", "omi-search")
READS = ("study_get_summary", "english_get_summary", "listening_health")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def argument_shape(arguments):
    """Reuse diagnostic masking; keep only bounded root field names and types."""
    if not isinstance(arguments, dict):
        return [{"field": "$", "type": _json_type(arguments)}]
    return [{"field": name if isinstance(name, str) and _DIAGNOSTIC_IDENTIFIER.fullmatch(name)
             and not _SENSITIVE_ARGUMENT_KEY.search(name) else "*", "type": _json_type(value)}
            for name, value in list(arguments.items())[:32]]


def market_receipt(source):
    """Market receipts retain status/target/freshness, never detailed evidence."""
    if not isinstance(source, dict):
        return {}
    target = source.get("target", {})
    if not isinstance(target, dict):
        target = {}
    return {"target": {key: target[key] for key in ("type", "market") if isinstance(target.get(key), str)},
            **{key: source[key] for key in ("status", "action", "answer_ready", "decision_ready", "as_of", "freshness_status")
               if isinstance(source.get(key), (str, bool, int))}}


def result_receipt(client, result):
    """Keep receipts and error codes, never learner records or credential values."""
    error, text, metadata, _ = result
    raw = client.last_call_result
    row = {"is_error": error, "execution_status": metadata.get("execution_status"),
           "reason_code": metadata.get("reason_code"), "text_bytes": len(text.encode())}
    if raw:
        row.update(result_received=raw.result_received, may_have_executed=raw.may_have_executed,
                   execution_id=raw.execution_id, server_id=raw.server_id,
                   canonical_tool_id=raw.canonical_tool_id,
                   started_at=raw.started_at, completed_at=raw.completed_at)
        source = raw.structured_content
        if not isinstance(source, dict) and raw.text_blocks:
            try:
                source = json.loads(raw.text_blocks[0])
            except (ValueError, TypeError):
                source = None
        if isinstance(source, dict):
            for key in ("ok", "status", "contract_version", "contractVersion"):
                if isinstance(source.get(key), (str, bool)):
                    row[key] = source[key]
            failure = source.get("error")
            if isinstance(failure, dict):
                row["backend_error_code"] = failure.get("code")
            if raw.server_id == "omi-search":
                row["market"] = market_receipt(metadata.get("omi_evidence"))
    return row


async def llm_probe(manager, executor, client):
    from kuro_launcher.utils import load_env_file
    from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
    from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    for path in (ROOT / ".env", ROOT / ".env.local"):
        load_env_file(path, override=True)
    key = os.environ.get("OPENAI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    receipt = {"model": "gpt-5-mini", "max_requests": 2, "max_retries": 0, "requests": 0}
    if not key:
        return {**receipt, "status": "UNVERIFIED", "reason": "api_key_unavailable"}
    llm = AsyncLLM(model="gpt-5-mini", base_url="https://api.openai.com/v1", llm_api_key=key,
                   organization_id=None, project_id=None)
    llm.client = llm.client.with_options(max_retries=0, timeout=45)
    tools = manager.get_formatted_tools("OpenAI", request_text=QUESTION)
    agent = BasicMemoryAgent.__new__(BasicMemoryAgent)
    agent._system = "請用繁體中文依 OMI 工具的真實結果回答。保留 partial、stale、missing 與失敗原因；不要猜測市場數字。"
    agent._turn_chat_speech = {"route": "legacy_bridge"}
    system = agent._compose_tool_system_prompt(manager.get_last_route_prompt())
    messages = [{"role": "user", "content": QUESTION}]
    calls, text = [], ""
    try:
        receipt["requests"] += 1
        async for event in llm.chat_completion(messages, system, tools=tools):
            if isinstance(event, list):
                calls.extend(item for item in event if isinstance(item, ToolCallObject))
            elif isinstance(event, str):
                text += event
        receipt["tool_calls"] = []
        if not calls:
            reason = "api_error_unclassified" if text.startswith("Error calling the chat endpoint:") else "model_returned_no_tool_call"
            return {**receipt, "status": "UNVERIFIED", "reason": reason}
        for call in calls:
            identity = manager.resolve_tool_name(call.function.name)
            args = json.loads(call.function.arguments)
            decision = executor.check_call(call.function.name, args, tool_id=call.id)
            row = {"identity": identity, "argument_fields": argument_shape(args),
                   "policy_schema_allowed": decision.allowed, "reason_code": decision.reason_code}
            if identity != "omi-search::omi_ask":
                row["probe_execution"] = "not_executed_non_omi"
                receipt["tool_calls"].append(row)
                continue
            try:
                canonical = manager.get_tool(identity).input_schema
                row["schema_digest"] = schema_digest(canonical)
                validate_arguments(canonical, args)
                row["schema"] = "PASS"
            except SchemaError as exc:
                row.update(schema="FAIL", diagnostics=[{key: item[key] for key in ("path", "keyword")}
                                                        for item in exc.diagnostics])
            receipt["tool_calls"].append(row)
        # Limit the probe to one model-requested read. No automatic retries.
        if len(calls) != 1 or manager.resolve_tool_name(calls[0].function.name) != "omi-search::omi_ask":
            return {**receipt, "status": "UNVERIFIED", "reason": "unexpected_tool_call_set"}
        updates = [update async for update in executor.execute_tools(calls, "OpenAI")]
        receipt["tool_statuses"] = [{key: update.get(key) for key in ("type", "status", "reason_code", "tool_name")}
                                    for update in updates if update.get("type") == "tool_call_status"]
        results = next(update["results"] for update in updates if update.get("type") == "final_tool_results")
        messages.append({"role": "assistant", "content": text or None,
                         "tool_calls": [{"id": call.id, "type": call.type,
                                         "function": {"name": call.function.name,
                                                      "arguments": call.function.arguments}} for call in calls]})
        messages.extend(results)
        reply = ""
        receipt["requests"] += 1
        # Second request explains the actual result; no tools/retry are exposed.
        async for event in llm.chat_completion(messages, system):
            if isinstance(event, str):
                reply += event
        receipt["response_received"] = bool(reply) and not reply.startswith("Error calling the chat endpoint:")
        receipt["status"] = "PASS" if all(row.get("schema") == "PASS" and row["policy_schema_allowed"]
                                           for row in receipt["tool_calls"]) else "FAIL"
        return receipt
    except Exception as exc:
        return {**receipt, "status": "UNVERIFIED", "reason": type(exc).__name__}
    finally:
        await llm.client.close()


async def verify(output, with_llm, servers=SERVERS):
    logger.remove()
    registry = ServerRegistry(RUNTIME / "mcp_servers.json")
    entries = {name: Path(registry.servers[name].args[-1]) for name in servers}
    before = {name: digest(path) for name, path in entries.items()}
    receipt = {"observed_at": datetime.now(timezone.utc).isoformat(),
               "formal_qt_runtime": "NOT_RESTARTED_NOT_UPGRADED", "llm": {"requests": 0},
               "entries": {name: {"command": registry.servers[name].command,
                                  "command_exists": Path(registry.servers[name].command).is_file(),
                                  "entrypoint": str(path), "sha256": before[name]}
                           for name, path in entries.items()}}
    def save():
        output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        adapter = ToolAdapter(registry)
        _, openai, claude = await adapter.get_tools(list(servers))
        raw = adapter.get_last_formatted_tools_dict()
        receipt["discovery"] = {name: {"complete": row.complete, "reason": row.reason,
            "discovered_count": len(row.tools), "visible_count": sum(info.related_server == name for info in raw.values()),
            "visible_tools": sorted(key for key, info in raw.items() if info.related_server == name),
            "schema_digest": row.schema_digest} for name, row in adapter.discovery_results.items()}
        receipt["schema_errors"] = adapter.schema_errors
        manager = ToolManager(openai, claude, raw)
        if "omi-search" in servers:
            manager.get_formatted_tools("OpenAI", request_text=QUESTION)
            receipt["route"] = {"tools": manager.get_last_route().tool_names, "reason": manager.get_last_route().reason}
            receipt["omi_schema_digest"] = schema_digest(raw["omi-search::omi_ask"].input_schema)
        save()
        async with MCPClient(registry) as client:
            executor = ToolExecutor(client, manager)
            receipt["readonly_calls"] = {}
            for server, tool in zip(SERVERS, READS):
                if server not in servers:
                    continue
                identity = server + "::" + tool
                result = await executor.run_single_tool(identity, "shared-read-" + server, {})
                receipt["readonly_calls"][identity] = result_receipt(client, result)
                save()
            if "omi-search" in servers:
                args = {"question": QUESTION, "target": {"type": "market", "market": "US"},
                        "mode": "data_only", "refresh_if_missing": False, "realtime_policy": "cache_only"}
                decision = executor.check_call("omi-search::omi_ask", args)
                receipt["omi_us_check"] = {"argument_fields": argument_shape(args), "target": args["target"],
                                            "allowed": decision.allowed, "reason_code": decision.reason_code}
                result = await executor.run_single_tool("omi-search::omi_ask", "shared-read-us-market", args)
                receipt["readonly_calls"]["omi-search::omi_ask"] = result_receipt(client, result)
                response_target = receipt["readonly_calls"]["omi-search::omi_ask"].get("market", {}).get("target")
                receipt["omi_us_check"]["response_target_matches"] = response_target == args["target"]
            save()
            if with_llm:
                receipt["llm"] = await llm_probe(manager, executor, client)
    finally:
        receipt["shared_entrypoints_unchanged"] = all(digest(path) == before[name] for name, path in entries.items())
        save()
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-llm", action="store_true", help="Opt in to at most two authorized gpt-5-mini API requests.")
    parser.add_argument("--only", choices=SERVERS, help="Probe only this adapter; avoid repeating unrelated reads.")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Use a new output path in an existing directory.")
    if args.with_llm and args.only and args.only != "omi-search":
        parser.error("The LLM probe requires omi-search.")
    os.chdir(RUNTIME)
    receipt = asyncio.run(verify(args.output, args.with_llm, (args.only,) if args.only else SERVERS))
    print(json.dumps({key: receipt.get(key) for key in ("discovery", "route", "readonly_calls", "llm", "shared_entrypoints_unchanged")}, ensure_ascii=False))
