import asyncio

from loguru import logger
from copy import deepcopy
from .tool_catalog_manager import ToolCatalog, ToolRoute, normalize_thinking_power
from .tool_identity import canonical_id, legacy_canonical
from typing import Dict, Any, List, Literal

from .types import FormattedTool
from .tool_schema import validate_arguments, schema_digest

DISCOVERY = "kuro_discover"
DISCOVERY_DESCRIPTION = (
    "Search installed MCP tools by service, name or description. Omit query to browse. "
    "Pass load with exact canonical names to expose those schemas in the NEXT model call. "
    "Each load replaces the previous selection. Repeat as often as needed. "
    "Set refresh to re-list services after a connection or schema change."
)
DISCOVERY_SCHEMA = {"type": "object", "properties": {
    "query": {"type": "string"}, "service": {"type": "string"},
    "load": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    "refresh": {"type": "boolean"}}, "additionalProperties": False}


class ToolSelection:
    """Provider schemas and unresolved side effects scoped to one interaction loop."""
    def __init__(self, manager, mode):
        self.manager = manager
        self.mode = mode
        self.names = []
        self.uncertain = set()

    def descriptors(self):
        descriptor = {"name": DISCOVERY, "description": DISCOVERY_DESCRIPTION}
        if self.mode == "Claude":
            bootstrap = {**descriptor, "input_schema": DISCOVERY_SCHEMA}
            available = self.manager._tools_by_name_claude
        else:
            bootstrap = {"type": "function", "function": {**descriptor, "parameters": DISCOVERY_SCHEMA, "strict": False}}
            available = self.manager._tools_by_name_openai
        return [bootstrap, *(available[name] for name in self.names if name in available)]

    async def discover(self, arguments, policy):
        validate_arguments(DISCOVERY_SCHEMA, arguments)
        if arguments.get("refresh"):
            await self.manager.refresh()
        inventory = self.manager.inventory(policy)
        rows = inventory["tools"]
        allowed = {r["name"] for r in rows if r["allowed"]}
        if "load" in arguments:
            requested = []
            unavailable = []
            service = arguments.get("service")
            for name in arguments["load"]:
                # An owner-scoped wire name identifies the same tool as its canonical ID.
                canonical = canonical_id(service, name) if service and name and "::" not in name else name
                if canonical in allowed and (not service or canonical.startswith(service + "::")):
                    if canonical not in requested:
                        requested.append(canonical)
                else:
                    unavailable.append(canonical)
            if unavailable:
                return {"status": "unavailable", "unavailable": unavailable,
                        "details": [r for r in rows if r["name"] in unavailable], "services": inventory["services"],
                        "recovery": "Browse with service alone and load the exact names shown for allowed tools."}
            self.names = requested
        query = arguments.get("query", "").casefold().split()
        service = arguments.get("service")
        matches = [r for r in rows if ("load" not in arguments or query or r["name"] in self.names)
                   and (not service or r["service"] == service)
                   and all(word in (r["name"] + " " + r["description"]).casefold() for word in query)]
        owners = {self.manager.tools[n].related_server for n in self.names if n in self.manager.tools}
        instructions = {s: result.instructions for s, result in
                        (self.manager.adapter.discovery_results.items() if self.manager.adapter else ())
                        if s in owners and result.instructions}
        return {"status": "discovered", "services": inventory["services"], "loaded": self.names,
                "owner_instructions": instructions,
                "matches": [{k: r[k] for k in ("name", "operation", "allowed", "reason_code", "description")} for r in matches]}


class ToolManager:
    """Tool Manager for managing pre-formatted tools for different LLM APIs."""

    def __init__(
        self,
        formatted_tools_openai: List[Dict[str, Any]] = None,
        formatted_tools_claude: List[Dict[str, Any]] = None,
        initial_tools_dict: Dict[str, FormattedTool] = None,
        tool_catalog: ToolCatalog | None = None,
        thinking_power: str = "normal",
    ) -> None:
        """Initialize the Tool Manager with pre-formatted tool lists."""
        # Store the raw tool data (optional, for get_tool)
        self.tools: Dict[str, FormattedTool] = deepcopy(initial_tools_dict or {})

        # Store the pre-formatted lists
        self._formatted_tools_openai: List[Dict[str, Any]] = (
            deepcopy(formatted_tools_openai or [])
        )
        self._formatted_tools_claude: List[Dict[str, Any]] = (
            deepcopy(formatted_tools_claude or [])
        )
        openai_tools_by_api_name = {
            tool.get("function", {}).get("name"): tool
            for tool in self._formatted_tools_openai
            if tool.get("function", {}).get("name")
        }
        self._openai_api_to_tool_name: Dict[str, str] = {}
        self._tools_by_name_openai: Dict[str, Dict[str, Any]] = {}
        for canonical_name, tool_info in self.tools.items():
            api_name = getattr(tool_info, "api_name", "") or canonical_name
            if api_name in openai_tools_by_api_name:
                self._openai_api_to_tool_name[api_name] = canonical_name
                self._tools_by_name_openai[canonical_name] = openai_tools_by_api_name[
                    api_name
                ]

        claude_by_alias = {tool.get("name"): tool for tool in self._formatted_tools_claude}
        self._tools_by_name_claude = {
            canonical: claude_by_alias[info.api_name or canonical]
            for canonical, info in self.tools.items() if (info.api_name or canonical) in claude_by_alias
        }
        self.adapter = None
        self.enabled_servers = []
        self._refresh_lock = asyncio.Lock()
        self._tool_catalog = tool_catalog or ToolCatalog.load_default()
        self._thinking_power = normalize_thinking_power(thinking_power)
        self._last_route: ToolRoute | None = None
        self._last_inventory_question = False

        logger.info(
            f"ToolManager initialized with {len(self._formatted_tools_openai)} OpenAI tools and {len(self._formatted_tools_claude)} Claude tools."
        )

    def bind_discovery(self, adapter, enabled_servers):
        self.adapter = adapter
        self.enabled_servers = list(enabled_servers)

    async def refresh(self):
        if self.adapter is None:
            return
        async with self._refresh_lock:
            # Build in isolation so readers never see a half-refreshed index.
            from .tool_adapter import ToolAdapter
            adapter = ToolAdapter(self.adapter.server_registery)
            adapter.schema_profile = self.adapter.schema_profile
            _, openai, claude = await adapter.get_tools(self.enabled_servers)
            fresh = ToolManager(openai, claude, adapter.get_last_formatted_tools_dict(),
                                self._tool_catalog, self._thinking_power)
            fresh.bind_discovery(adapter, self.enabled_servers)
            fresh._refresh_lock = self._refresh_lock
            self.__dict__.update(fresh.__dict__)

    def inventory(self, policy):
        services, rows = {}, []
        discovered = self.adapter.discovery_results if self.adapter else {}
        for service in self.enabled_servers:
            result = discovered.get(service)
            services[service] = {"connected": bool(result and result.complete),
                                 "count": len(result.tools) if result and result.complete else None,
                                 "reason": result.reason if result else "not_configured",
                                 "observed_at": result.observed_at if result else ""}
        if "project-workspace" in services and getattr(self.adapter, "workspace_scope", None):
            services["project-workspace"]["scope"] = dict(self.adapter.workspace_scope)
        for service, result in discovered.items():
            if not result.complete:
                continue
            for tool in result.tools:
                name = canonical_id(service, tool.name)
                decision = policy.check(name, {})
                exposed = name in self.tools
                hint = tool.annotations
                operation = ("read" if hint and hint.readOnlyHint is True else
                             "destructive" if hint and hint.destructiveHint is True else
                             "write" if hint and hint.readOnlyHint is False else "owner_defined")
                rows.append({"name": name, "service": service, "label": tool.title or (hint.title if hint else None) or tool.name,
                             "description": tool.description or "",
                             "input_schema_sha256": schema_digest(tool.inputSchema),
                             "operation": operation, "allowed": exposed and decision.allowed,
                             "reason_code": decision.reason_code if exposed else
                             self.adapter.schema_errors.get(name) or self.adapter.exposure_errors.get(name, "not_model_exposed")})
        if not self.adapter:
            for name, tool in self.tools.items():
                decision = policy.check(name, {})
                rows.append({"name": name, "service": tool.related_server, "description": tool.description or "",
                             "operation": "owner_defined", "allowed": decision.allowed, "reason_code": decision.reason_code})
        return {"services": services, "tools": rows, "policy_digest": policy.digest}

    def get_tool(self, tool_name: str) -> FormattedTool | None:
        """Get a tool's raw information by its name."""
        canonical_name = self.resolve_tool_name(tool_name)
        tool = self.tools.get(canonical_name)
        if isinstance(tool, FormattedTool):
            return tool
        logger.warning("TM: Tool unavailable in this snapshot.")
        return None

    def resolve_tool_name(self, tool_name: str) -> str:
        """Resolve provider-safe API names back to canonical MCP tool names."""
        if not isinstance(tool_name, str):
            return ""
        if tool_name in self.tools:
            return tool_name
        return self._openai_api_to_tool_name.get(tool_name, legacy_canonical(tool_name))

    def get_formatted_tools(
        self, mode: Literal["OpenAI", "Claude"], request_text: str | None = None
    ) -> List[Dict[str, Any]] | Any:
        """Get the pre-formatted list of tools for the specified API mode."""

        if mode == "OpenAI":
            if request_text is None:
                return self._formatted_tools_openai
            return self._route_formatted_tools(
                request_text,
                self._formatted_tools_openai,
                self._tools_by_name_openai,
            )
        elif mode == "Claude":
            if request_text is None:
                return self._formatted_tools_claude
            return self._route_formatted_tools(
                request_text,
                self._formatted_tools_claude,
                self._tools_by_name_claude,
            )

    def get_tool_catalog_prompt(self) -> str:
        return self._tool_catalog.format_prompt_summary(
            list(self.tools.keys()),
            thinking_power=self._thinking_power,
        )

    def get_last_route(self) -> ToolRoute | None:
        return self._last_route

    def get_last_route_prompt(self) -> str:
        route_prompt = self._tool_catalog.format_route_prompt(self._last_route)
        if not self._last_inventory_question:
            return route_prompt
        return (route_prompt + "\n\nTool inventory question: report the following "
                "discovered ToolManager snapshot, not merely the candidate tools "
                "exposed for this turn. Discovery is not proof of successful "
                "execution or permission denial. Do not invent tools, and do not "
                "claim multi_tool_use.parallel is an installed tool unless it "
                "appears in the discovered inventory.\n"
                + self.get_tool_catalog_prompt())

    def disable(self) -> None:
        """Disable native API tool exposure while keeping raw tools for prompt mode."""
        self._formatted_tools_openai = []
        self._formatted_tools_claude = []
        self._tools_by_name_openai = {}
        self._tools_by_name_claude = {}

    def _route_formatted_tools(
        self,
        request_text: str,
        full_tools: List[Dict[str, Any]],
        tools_by_name: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        query = str(request_text or "").lower()
        compact = query.replace(" ", "")
        self._last_inventory_question = (
            "工具" in query or "tools" in query or "tool list" in query
            or "除了omi" in compact or "除了omi呢" in compact
        )
        if not self._tool_catalog.enabled:
            self._last_route = None
            return full_tools

        route = self._tool_catalog.route(
            request_text,
            list(tools_by_name.keys()),
            thinking_power=self._thinking_power,
        )
        self._last_route = route
        if not route.tool_names:
            logger.debug(f"Tool router selected no tools: {route.reason}")
            return []

        selected = [
            tools_by_name[name]
            for name in route.tool_names
            if name in tools_by_name
        ]
        logger.info(
            f"Tool router selected categories={route.categories}, tools={route.tool_names}"
        )
        return selected
