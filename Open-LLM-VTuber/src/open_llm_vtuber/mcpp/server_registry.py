"""MCP Server Manager for Open-LLM-Vtuber."""

import shutil
import json
import os
import math
from urllib.parse import urlsplit

from datetime import timedelta
from pathlib import Path
from typing import Dict, Optional, Union, Any
from loguru import logger

from .types import MCPServer
from .utils.path import validate_file

DEFAULT_CONFIG_PATH = "mcp_servers.json"
DEFAULT_TIMEOUT_SECONDS = 30

# These are domain-owned MCP endpoints, never model-supplied network targets.
HTTP_ENDPOINTS = {
    "memory-core": "http://127.0.0.1:18818/mcp",
    "personal-asset-os": "http://127.0.0.1:18876/mcp/",
}
HTTP_SERVER_NAMES = {"memory-core": "memory-core-mcp", "personal-asset-os": "Personal Asset OS"}
# The installed owners enforce their own action scopes at these loopback endpoints.
OWNER_SERVICES = {
    "project-workspace": (18787, "gpt-project-workspace-mcp"),
    "japanese-study": (18790, "japanese-study-mcp"),
    "english-study": (18886, "english-study-mcp"),
    "listening-audio": (18810, "listening-audio"),
    "omi-search": (18797, "omi-search-mcp"),
}
for _service, (_port, _identity) in OWNER_SERVICES.items():
    HTTP_ENDPOINTS[_service] = f"http://127.0.0.1:{_port}/mcp"
    HTTP_SERVER_NAMES[_service] = _identity

HTTP_READ_TOOLS = {
    "memory-core": (
        "search", "fetch", "memory_fetch_record_revision", "memory_list_record_links",
        "memory_overview", "memory_detect_duplicates", "memory_list_collections", "memory_get_collection",
    ),
    "personal-asset-os": (
        "get_asset_overview", "list_asset_accounts", "list_asset_positions",
        "list_recent_asset_transactions", "get_pending_financial_events",
        "get_reconciliation_status", "get_asset_system_status",
    ),
}
HTTP_FORBIDDEN_ARGS = frozenset({"url", "uri", "endpoint", "headers", "auth", "token", "client_token",
                               "scope", "scopes", "command", "env", "cwd", "transport"})


def http_tool_is_read_only(server_name, tool) -> bool:
    return (tool.name in HTTP_READ_TOOLS.get(server_name, ()) and tool.annotations is not None
            and tool.annotations.readOnlyHint is True and tool.annotations.destructiveHint is not True)


def http_arguments_allowed(server_name, args) -> bool:
    return (isinstance(args, dict) and not HTTP_FORBIDDEN_ARGS.intersection(args)
            and not (server_name == "memory-core" and args.get("sensitivity") == "restricted"))


def validate_http_endpoint(server_name: str, url: Any) -> None:
    if not isinstance(url, str) or server_name not in HTTP_ENDPOINTS:
        raise ValueError("http_endpoint_denied")
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or url != HTTP_ENDPOINTS[server_name]):
        raise ValueError("http_endpoint_denied")


def validate_http_server(server: MCPServer) -> None:
    validate_http_endpoint(server.name, server.url)
    if server.name in OWNER_SERVICES:
        if (server.transport != "streamable_http" or server.command or server.args or server.env
                or server.cwd or server.require_read_only or server.allowed_tools is not None):
            raise ValueError("http_server_config_denied")
        return
    if (server.transport != "streamable_http" or server.require_read_only is not True
            or not isinstance(server.allowed_tools, list)
            or len(server.allowed_tools) != len(HTTP_READ_TOOLS[server.name])
            or set(server.allowed_tools) != set(HTTP_READ_TOOLS[server.name])
            or server.command or server.args or server.env or server.cwd):
        raise ValueError("http_server_config_denied")


def _normalize_timeout(value: Any) -> timedelta:
    """Normalize JSON timeout values into the type expected by mcp.ClientSession."""
    if isinstance(value, timedelta):
        return value
    if value is None:
        return timedelta(seconds=DEFAULT_TIMEOUT_SECONDS)
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        try:
            seconds = float(value.strip())
        except ValueError:
            logger.warning(
                f"MCPSR: Invalid timeout value '{value}'. Using default timeout."
            )
            return timedelta(seconds=DEFAULT_TIMEOUT_SECONDS)
    else:
        logger.warning(
            f"MCPSR: Unsupported timeout type '{type(value).__name__}'. Using default timeout."
        )
        return timedelta(seconds=DEFAULT_TIMEOUT_SECONDS)

    if not math.isfinite(seconds) or seconds <= 0:
        logger.warning(
            f"MCPSR: Non-positive timeout value '{value}'. Using default timeout."
        )
        return timedelta(seconds=DEFAULT_TIMEOUT_SECONDS)
    return timedelta(seconds=seconds)


class ServerRegistry:
    """MCP Server Manager for managing server files."""

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        """Initialize the MCP Server Manager."""
        try:
            config_path = validate_file(config_path, ".json")
        except ValueError:
            logger.error(
                f"MCPSR: File '{config_path}' does not exist, or is not a json file."
            )
            raise ValueError(
                f"MCPSR: File '{config_path}' does not exist, or is not a json file."
            )

        self.config: Dict[str, Union[str, dict]] = json.loads(
            config_path.read_text(encoding="utf-8")
        )

        self.servers: Dict[str, MCPServer] = {}

        self.npx_available = self._detect_runtime("npx")
        self.uvx_available = self._detect_runtime("uvx")
        self.node_available = self._detect_runtime("node")

        self.load_servers()

    def _detect_runtime(self, target: str) -> bool:
        """Check if a runtime is available in the system PATH."""
        founded = shutil.which(target)
        return True if founded else False

    def load_servers(self) -> None:
        """Load servers from the config file."""
        servers_config: Dict[str, Dict[str, Any]] = self.config.get("mcp_servers", {})
        if not isinstance(servers_config, dict):
            raise ValueError("MCP server configuration must be an object.")
        if servers_config == {}:
            logger.warning("MCPSR: No servers found in the config file.")
            return

        for server_name, server_details in servers_config.items():
            if server_name == "omi-market":
                logger.warning("MCPSR: Retired market server cannot be started.")
                continue
            if not isinstance(server_details, dict):
                continue
            transport = server_details.get("transport", "stdio")
            if transport == "streamable_http":
                try:
                    # HTTP has no command, environment, headers, auth or client options.
                    if set(server_details) - {"transport", "url", "timeout", "allowed_tools", "require_read_only"}:
                        raise ValueError("http_config_fields_denied")
                    server = MCPServer(
                        name=server_name, command="", transport=transport, url=server_details.get("url"),
                        timeout=_normalize_timeout(server_details.get("timeout")),
                        allowed_tools=server_details.get("allowed_tools"),
                        require_read_only=server_details.get("require_read_only", False),
                    )
                    validate_http_server(server)
                except (ValueError, TypeError):
                    logger.warning("MCPSR: Invalid HTTP MCP configuration; server disabled.")
                    continue
                self.servers[server_name] = server
                continue
            if transport != "stdio" or server_name in HTTP_READ_TOOLS or "url" in server_details:
                logger.warning("MCPSR: Invalid MCP transport; server disabled.")
                continue
            if type(server_details.get("require_read_only", False)) is not bool:
                logger.warning("MCPSR: Invalid read-only annotation requirement; server disabled.")
                continue
            allowed_tools = server_details.get("allowed_tools")
            if allowed_tools is not None and (not isinstance(allowed_tools, list) or not all(isinstance(name, str) and name for name in allowed_tools)):
                logger.warning("MCPSR: Invalid configured tool allowlist; server disabled.")
                continue
            if "command" not in server_details or "args" not in server_details:
                logger.warning(
                    f"MCPSR: Invalid server details for '{server_name}'. Ignoring."
                )
                continue

            command = server_details["command"]
            args, env = server_details["args"], server_details.get("env")
            if (not isinstance(command, str) or not command or
                not isinstance(args, list) or not all(isinstance(arg, str) for arg in args) or
                (env is not None and (not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())))):
                logger.warning("MCPSR: Invalid command arguments or environment; server disabled.")
                continue
            if command == "npx":
                if not self.npx_available:
                    logger.warning(
                        f"MCPSR: npx is not available. Cannot load server '{server_name}'."
                    )
                    continue
            elif command == "uvx":
                if not self.uvx_available:
                    logger.warning(
                        f"MCPSR: uvx is not available. Cannot load server '{server_name}'."
                    )
                    continue

            elif command == "node":
                if not self.node_available:
                    logger.warning(
                        f"MCPSR: node is not available. Cannot load server '{server_name}'."
                    )
                    continue

            child_env = {key: os.path.expandvars(value) for key, value in (env or {}).items()}
            if server_name == "project-workspace":
                # The stdio owner alone validates these operator-supplied scope and journal paths.
                for key in ("WORKSPACE_MCP_WRITE_POLICY", "WORKSPACE_MCP_WRITE_STATE_DIR"):
                    if key not in child_env and key in os.environ:
                        child_env[key] = os.environ[key]
            self.servers[server_name] = MCPServer(
                name=server_name,
                command=command,
                args=server_details["args"],
                env=child_env or None,
                allowed_tools=allowed_tools,
                require_read_only=server_details.get("require_read_only", False),
                cwd=server_details.get("cwd", None),
                timeout=_normalize_timeout(server_details.get("timeout", None)),
            )
            logger.debug(f"MCPSR: Loaded server: '{server_name}'.")

    def remove_server(self, server_name: str) -> None:
        """Remove a server from the available servers."""
        try:
            self.servers.pop(server_name)
            logger.info(f"MCPSR: Removed server: {server_name}")
        except KeyError:
            logger.warning(f"MCPSR: Server '{server_name}' not found. Cannot remove.")

    def get_server(self, server_name: str) -> Optional[MCPServer]:
        """Get the server by name."""
        return self.servers.get(server_name, None)
