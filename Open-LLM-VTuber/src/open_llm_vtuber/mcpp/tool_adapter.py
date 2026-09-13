"""Constructs prompts for servers and tools, formats tool information for OpenAI API."""

import re
import os
import json
from copy import deepcopy
from .tool_schema import provider_schema, resolved_schema, schema_digest, SchemaError
from typing import Dict, Optional, List, Tuple, Any
from loguru import logger

from .types import FormattedTool
from .mcp_client import MCPClient
from .server_registry import ServerRegistry
from .tool_identity import canonical_id, provider_alias


OPENAI_TOOL_NAME_MAX_LENGTH = 64
_OPENAI_TOOL_NAME_INVALID_CHARS = re.compile(r"[^a-zA-Z0-9_-]+")


def _openai_api_tool_name(tool_name: str, used_names: set[str]) -> str:
    """Return a unique OpenAI-compatible function name for a canonical MCP tool."""
    candidate = provider_alias(tool_name)
    if candidate in used_names:
        raise ValueError("Provider alias collision.")

    used_names.add(candidate)
    return candidate


class ToolAdapter:
    """Dynamically fetches tool information from enabled MCP servers and formats it."""

    def __init__(self, server_registery: Optional[ServerRegistry] = None) -> None:
        """Initialize with an ServerRegistry."""
        self.server_registery = server_registery or ServerRegistry()
        self._last_formatted_tools_dict: Dict[str, FormattedTool] = {}
        self.schema_profile = os.getenv("KURO_MCP_SCHEMA_PROFILE", "openai_non_strict")
        self.schema_errors: dict[str, str] = {}
        self.discovery_results = {}

    def get_last_formatted_tools_dict(self) -> Dict[str, FormattedTool]:
        """Return the raw tools from the most recent dynamic fetch."""
        return self._last_formatted_tools_dict

    async def get_server_and_tool_info(
        self, enabled_servers: List[str]
    ) -> Tuple[Dict[str, Dict[str, str]], Dict[str, FormattedTool]]:
        """Fetch tool information from specified enabled MCP servers."""
        servers_info: Dict[str, Dict[str, str]] = {}
        formatted_tools: Dict[str, FormattedTool] = {}

        if not enabled_servers:
            logger.warning(
                "MC: No enabled MCP servers specified. Cannot fetch tool info."
            )
            return servers_info, formatted_tools

        logger.debug(f"MC: Fetching tool info for enabled servers: {enabled_servers}")

        # Use a single client instance for efficiency
        async with MCPClient(self.server_registery) as client:
            for server_name in dict.fromkeys(enabled_servers):
                if server_name not in self.server_registery.servers:
                    logger.warning(
                        f"MC: Enabled server '{server_name}' not found in Server Manager. Skipping."
                    )
                    continue

                try:
                    servers_info[server_name] = {}
                    discovery = await client.discover_tools(server_name)
                    self.discovery_results[server_name] = discovery
                    if not discovery.complete:
                        continue
                    tools = discovery.tools
                    logger.debug(
                        f"MC: Found {len(tools)} tools on server '{server_name}'"
                    )
                    for tool in tools:
                        allowed = self.server_registery.servers[server_name].allowed_tools
                        if allowed is not None and tool.name not in allowed:
                            continue
                        servers_info[server_name][tool.name] = {}
                        tool_info = servers_info[server_name][tool.name]
                        tool_info["description"] = tool.description
                        tool_info["parameters"] = tool.inputSchema.get("properties", {})
                        tool_info["required"] = tool.inputSchema.get("required", [])

                        # Store the tool info in FormattedTool format
                        identity = canonical_id(server_name, tool.name)
                        formatted_tools[identity] = FormattedTool(
                            canonical_id=identity,
                            wire_name=tool.name,
                            output_schema=tool.outputSchema,
                            input_schema=tool.inputSchema,
                            related_server=server_name,
                            description=tool.description,
                            # Generic schema will be generated later if needed
                            generic_schema=None,
                        )
                except (ValueError, RuntimeError, ConnectionError) as e:
                    logger.error("MC: Failed to get info for server '; payload details omitted.")
                    if (
                        server_name not in servers_info
                    ):  # Ensure entry exists even on error
                        servers_info[server_name] = {}
                    continue  # Continue to next server
                except Exception as e:
                    logger.error("MC: Unexpected error for server '; payload details omitted.")
                    if server_name not in servers_info:
                        servers_info[server_name] = {}
                    continue  # Continue to next server

        logger.debug(
            f"MC: Finished fetching tool info. Found {len(formatted_tools)} tools across enabled servers."
        )
        return servers_info, formatted_tools

    def construct_mcp_prompt_string(
        self, servers_info: Dict[str, Dict[str, str]]
    ) -> str:
        """Build a single prompt string describing enabled servers and their tools."""
        full_prompt_content = ""
        if not servers_info:
            logger.warning(
                "MC: Cannot construct MCP prompt string, servers_info is empty."
            )
            return full_prompt_content

        logger.debug(
            f"MC: Constructing MCP prompt string for {len(servers_info)} server(s)."
        )

        for server_name, tools in servers_info.items():
            if not tools:  # Skip servers where info couldn't be fetched
                logger.warning(
                    f"MC: No tool info available for server '{server_name}', skipping in prompt."
                )
                continue

            prompt_content = f"Server: {server_name}\n"
            prompt_content += "    Tools:\n"
            for tool_name, tool_info in tools.items():
                prompt_content += f"        {tool_name}:\n"
                # Ensure description is handled correctly (might be None)
                description = tool_info.get("description", "No description available.")
                prompt_content += f"            Description: {description}\n"
                if "schema" in tool_info:
                    prompt_content += "            Input schema: " + json.dumps(tool_info["schema"], ensure_ascii=False, sort_keys=True) + "\n"
                parameters = tool_info.get("parameters", {})
                if parameters:
                    prompt_content += "            Parameters:\n"
                    for param_name, param_info in parameters.items():
                        param_desc = param_info.get("description") or param_info.get(
                            "title", "No description provided."
                        )
                        param_type = param_info.get(
                            "type", "string"
                        )  # Default to string if type missing
                        prompt_content += f"                {param_name}:\n"
                        prompt_content += f"                    Type: {param_type}\n"
                        prompt_content += (
                            f"                    Description: {param_desc}\n"
                        )
                required = tool_info.get("required", [])
                if required:
                    prompt_content += f"            Required: {', '.join(required)}\n"
            full_prompt_content += prompt_content + "\n"  # Add newline between servers

        logger.debug("MC: Finished constructing MCP prompt string.")
        return full_prompt_content.strip()  # Remove trailing newline

    def format_tools_for_api(
        self, formatted_tools_dict: Dict[str, FormattedTool]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Format tools to OpenAI and Claude function-calling compatible schemas."""
        openai_tools = []
        claude_tools = []

        if not formatted_tools_dict:
            logger.warning(
                "MC: Cannot format tools for API, input dictionary is empty."
            )
            return openai_tools, claude_tools

        logger.debug(f"MC: Formatting {len(formatted_tools_dict)} tools for API usage.")
        used_openai_tool_names: set[str] = set()

        rejected = []
        self.schema_errors = {}
        for tool_name, data_object in sorted(formatted_tools_dict.items()):
            if not isinstance(data_object, FormattedTool):
                logger.warning("MC: Skipping invalid tool format.")
                rejected.append(tool_name)
                self.schema_errors[tool_name] = "schema_invalid"
                continue

            input_schema = data_object.input_schema
            try:
                parameters = provider_schema(input_schema, self.schema_profile)
                if data_object.output_schema is not None:
                    resolved_schema(data_object.output_schema, require_object=False)
            except SchemaError as exc:
                self.schema_errors[tool_name] = exc.code
                rejected.append(tool_name)
                continue
            data_object.schema_digest = schema_digest(input_schema)
            data_object.provider_schema_digest = schema_digest(parameters)
            data_object.schema_profile = self.schema_profile
            data_object.generic_schema = parameters
            tool_description = data_object.description or "No description provided."
            openai_tool_name = _openai_api_tool_name(tool_name, used_openai_tool_names)
            data_object.api_name = openai_tool_name
            if openai_tool_name != tool_name:
                logger.debug(
                    f"MC: OpenAI tool alias '{openai_tool_name}' maps to MCP tool '{tool_name}'."
                )

            # Format for OpenAI
            openai_function_params = deepcopy(parameters)

            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": openai_tool_name,
                        "description": tool_description,
                        "parameters": openai_function_params,
                        "strict": self.schema_profile == "openai_strict",
                    },
                }
            )

            # Format for Claude
            claude_input_schema = deepcopy(parameters)
            claude_tools.append(
                {
                    "name": openai_tool_name,
                    "description": tool_description,
                    "input_schema": claude_input_schema,
                }
            )

        for name in rejected:
            formatted_tools_dict.pop(name, None)
        return openai_tools, claude_tools

    async def get_tools(
        self, enabled_servers: List[str]
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run the dynamic fetching and formatting process."""
        logger.info(
            f"MC: Running dynamic tool construction for servers: {enabled_servers}"
        )
        servers_info, formatted_tools_dict = await self.get_server_and_tool_info(
            enabled_servers
        )
        openai_tools, claude_tools = self.format_tools_for_api(formatted_tools_dict)
        effective_info = {}
        for identity, tool in formatted_tools_dict.items():
            effective_info.setdefault(tool.related_server, {})[identity] = {
                "description": tool.description, "schema": tool.generic_schema,
            }
        mcp_prompt_string = self.construct_mcp_prompt_string(effective_info)
        self._last_formatted_tools_dict = formatted_tools_dict
        logger.info("MC: Dynamic tool construction complete.")
        return mcp_prompt_string, openai_tools, claude_tools
