"""Read metadata only through Kuro's registered owners. Run from repo root."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "Open-LLM-VTuber"
sys.path.insert(0, str(RUNTIME / "src"))
from open_llm_vtuber.mcpp.server_registry import ServerRegistry, OWNER_SERVICES
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.tool_manager import ToolManager
from open_llm_vtuber.mcpp.tool_schema import schema_validator
from jsonschema.exceptions import SchemaError
from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy

async def inspect():
    adapter = ToolAdapter(ServerRegistry(RUNTIME / "mcp_servers.json"))
    _, openai, claude = await adapter.get_tools(list(OWNER_SERVICES))
    manager = ToolManager(openai, claude, adapter.get_last_formatted_tools_dict())
    manager.bind_discovery(adapter, OWNER_SERVICES)
    policy = ToolPolicy(json.loads((RUNTIME / "tool_policy.json").read_text(encoding="utf-8")))
    inventory = manager.inventory(policy)
    inventory["workspace_scope"] = inventory["services"]["project-workspace"].get("scope", {})
    inventory["contract_evidence"] = {}
    for service, result in adapter.discovery_results.items():
        for tool in result.tools:
            name = f"{service}::{tool.name}"
            if name in adapter.exposure_errors:
                inventory["contract_evidence"][name] = {"visibility": tool.meta["ui"]["visibility"]}
            if name in adapter.schema_errors:
                for field, schema in (("inputSchema", tool.inputSchema), ("outputSchema", tool.outputSchema)):
                    if schema is None:
                        continue
                    try:
                        schema_validator(schema).check_schema(schema)
                    except SchemaError as exc:
                        inventory["contract_evidence"][name] = {"field": field, "path": list(exc.absolute_path),
                            "source_fragment": exc.instance, "message": exc.message}
    return inventory

if __name__ == "__main__":
    print(json.dumps(asyncio.run(inspect()), ensure_ascii=False, indent=2))
