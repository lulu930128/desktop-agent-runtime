from loguru import logger
from typing import Dict, Any, List, Literal

from .types import FormattedTool
from .tool_catalog_manager import ToolCatalog, ToolRoute, normalize_thinking_power


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
        self.tools: Dict[str, FormattedTool] = initial_tools_dict or {}

        # Store the pre-formatted lists
        self._formatted_tools_openai: List[Dict[str, Any]] = (
            formatted_tools_openai or []
        )
        self._formatted_tools_claude: List[Dict[str, Any]] = (
            formatted_tools_claude or []
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

        for api_name, tool in openai_tools_by_api_name.items():
            self._openai_api_to_tool_name.setdefault(api_name, api_name)
            self._tools_by_name_openai.setdefault(api_name, tool)

        self._tools_by_name_claude = {
            tool.get("name"): tool
            for tool in self._formatted_tools_claude
            if tool.get("name")
        }
        self._tool_catalog = tool_catalog or ToolCatalog.load_default()
        self._thinking_power = normalize_thinking_power(thinking_power)
        self._last_route: ToolRoute | None = None

        logger.info(
            f"ToolManager initialized with {len(self._formatted_tools_openai)} OpenAI tools and {len(self._formatted_tools_claude)} Claude tools."
        )

    def get_tool(self, tool_name: str) -> FormattedTool | None:
        """Get a tool's raw information by its name."""
        canonical_name = self.resolve_tool_name(tool_name)
        tool = self.tools.get(canonical_name)
        if isinstance(tool, FormattedTool):
            return tool
        logger.warning(
            f"TM: Raw tool info for '{tool_name}' not found (was initial_tools_dict provided?)."
        )
        return None

    def resolve_tool_name(self, tool_name: str) -> str:
        """Resolve provider-safe API names back to canonical MCP tool names."""
        if tool_name in self.tools:
            return tool_name
        return self._openai_api_to_tool_name.get(tool_name, tool_name)

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
        return self._tool_catalog.format_route_prompt(self._last_route)

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
