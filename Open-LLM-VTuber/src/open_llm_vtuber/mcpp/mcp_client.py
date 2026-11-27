"""MCP Client for Open-LLM-Vtuber."""

from contextlib import AsyncExitStack
import asyncio
import hashlib
import json
import time
import uuid
import os
import httpx
from mcp.shared.exceptions import McpError
from .types import DiscoveryResult
from .tool_result import ToolResult, normalize_result, utc_now
from .tool_schema import SchemaError, schema_digest, resolved_schema, validate_arguments
from typing import Dict, Any, List, Callable
from loguru import logger
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.types import Tool
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .server_registry import (
    ServerRegistry, HTTP_ENDPOINTS, HTTP_SERVER_NAMES, HTTP_READ_TOOLS,
    validate_http_server, validate_http_endpoint, http_tool_is_read_only, http_arguments_allowed,
)

DEFAULT_TIMEOUT = timedelta(seconds=30)


def _http_client_factory(server):
    """Use the SDK transport with a pinned, credential-free HTTP connection."""
    validate_http_server(server)

    # Optional operator-provisioned credential. Never accept headers from tool arguments.
    workspace_token = os.environ.get("WORKSPACE_MCP_HTTP_TOKEN") if server.name == "project-workspace" else None

    async def guard(request):
        validate_http_endpoint(server.name, str(request.url))
        if request.method not in {"GET", "POST"} or any(
                key in request.headers for key in ("authorization", "proxy-authorization", "cookie")):
            raise ValueError("http_request_denied")

        if workspace_token:
            request.headers["authorization"] = "Bearer " + workspace_token

    def factory(headers=None, timeout=None, auth=None):
        if auth is not None:
            raise ValueError("http_auth_denied")
        return httpx.AsyncClient(headers=headers, timeout=timeout, trust_env=False,
                                 follow_redirects=False, event_hooks={"request": [guard]})
    return factory


def _transport_reason(exc):
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
        return "source_auth_denied"
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, (OSError, httpx.TransportError)):
        return "transport_offline"
    for child in getattr(exc, "exceptions", ()):
        reason = _transport_reason(child)
        if reason:
            return reason
    return ""


class OutputValidationFailure(RuntimeError):
    def __init__(self, result):
        super().__init__("MCP output schema validation failed.")
        self.result = result


class ValidatedClientSession(ClientSession):
    async def _validate_tool_result(self, name, result):
        try:
            await super()._validate_tool_result(name, result)
        except Exception:
            # Keep the received evidence while suppressing SDK exception payloads.
            raise OutputValidationFailure(result) from None


class MCPClient:
    """MCP Client for Open-LLM-Vtuber.
    Manages persistent connections to multiple MCP servers.
    """

    def __init__(
        self,
        server_registery: ServerRegistry,
        send_text: Callable = None,
        client_uid: str = None,
    ) -> None:
        """Initialize the MCP Client."""
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self.active_sessions: Dict[str, ClientSession] = {}
        self._list_tools_cache: Dict[str, List[Tool]] = {}  # Cache for list_tools
        self.discovery_results: dict[str, DiscoveryResult] = {}
        self.server_instructions: dict[str, str] = {}
        self.last_call_result: ToolResult | None = None
        self._send_text: Callable = send_text
        self._client_uid: str = client_uid

        if isinstance(server_registery, ServerRegistry):
            self.server_registery = server_registery
        else:
            raise TypeError(
                "MCPC: Invalid server manager. Must be an instance of ServerRegistry."
            )
        logger.info("MCPC: Initialized MCPClient instance.")

    async def _ensure_server_running_and_get_session(
        self, server_name: str
    ) -> ClientSession:
        """Gets the existing session or creates a new one."""
        server = self.server_registery.get_server(server_name)
        if server and (server.transport == "streamable_http" or server_name in HTTP_READ_TOOLS):
            validate_http_server(server)
        if server_name in self.active_sessions:
            return self.active_sessions[server_name]

        logger.info(f"MCPC: Starting and connecting to server '{server_name}'...")
        server = self.server_registery.get_server(server_name)
        if not server:
            raise ValueError(
                f"MCPC: Server '{server_name}' not found in available servers."
            )

        timeout = server.timeout if server.timeout else DEFAULT_TIMEOUT

        connection_stack = AsyncExitStack()
        try:
            if server.transport == "streamable_http":
                read, write, _ = await connection_stack.enter_async_context(
                    streamablehttp_client(
                        server.url, timeout=timeout, sse_read_timeout=timeout + timedelta(seconds=5),
                        terminate_on_close=False, httpx_client_factory=_http_client_factory(server),
                    )
                )
            elif server.transport == "stdio":
                server_params = StdioServerParameters(
                    command=server.command, args=server.args, env=server.env, cwd=server.cwd
                )
                # Server stderr may reflect credentials; keep it out of launcher logs.
                error_sink = connection_stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
                stdio_transport = await connection_stack.enter_async_context(
                    stdio_client(server_params, errlog=error_sink)
                )
                read, write = stdio_transport
            else:
                raise ValueError("unsupported_transport")

            session = await connection_stack.enter_async_context(
                ValidatedClientSession(read, write, read_timeout_seconds=timeout)
            )
            initialized = await asyncio.wait_for(session.initialize(), timeout.total_seconds())
            if server.transport == "streamable_http" and initialized.serverInfo.name != HTTP_SERVER_NAMES[server_name]:
                raise ValueError("http_server_identity_mismatch")

            self.server_instructions[server_name] = initialized.instructions or ""
            self.exit_stack.push_async_callback(connection_stack.aclose)
            self.active_sessions[server_name] = session
            logger.info(f"MCPC: Successfully connected to server '{server_name}'.")
            return session
        except BaseException as e:
            await connection_stack.aclose()
            if not isinstance(e, Exception):
                raise
            logger.error("MCPC: Connection failed type={} errno={}; raw transport error omitted.", type(e).__name__, getattr(e, "errno", None))
            raise

    async def discover_tools(self, server_name: str, *, refresh: bool = False) -> DiscoveryResult:
        previous = self.discovery_results.get(server_name)
        if not refresh and previous and previous.complete and server_name in self.active_sessions:
            return previous
        result = DiscoveryResult(server_id=server_name, observed_at=utc_now())
        server = self.server_registery.get_server(server_name)
        timeout = (server.timeout or DEFAULT_TIMEOUT).total_seconds() if server else 30
        deadline = time.monotonic() + timeout
        cursor, seen_cursors, names = None, set(), set()
        total_bytes = 0
        try:
            session = await self._ensure_server_running_and_get_session(server_name)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                response = await asyncio.wait_for(session.list_tools(cursor=cursor), remaining)
                result.pages_read += 1
                if not isinstance(response.tools, list):
                    raise ValueError("invalid_page")
                for tool in response.tools:
                    if not isinstance(tool, Tool) or not tool.name or tool.name in names:
                        raise ValueError("duplicate_or_invalid_identity")
                    total_bytes += len(tool.model_dump_json().encode())
                    if total_bytes > 8 * 1024 * 1024:
                        raise ValueError("discovery_size_limit")
                    names.add(tool.name)
                    result.tools.append(tool)
                cursor = response.nextCursor
                if cursor is None:
                    result.complete = True
                    result.instructions = self.server_instructions.get(server_name, "")
                    result.schema_digest = hashlib.sha256(json.dumps(
                        [t.model_dump(mode="json", by_alias=True) for t in sorted(result.tools,key=lambda x:x.name)],
                        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    self._list_tools_cache[server_name] = list(result.tools)
                    break
                if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                    raise ValueError("invalid_or_repeated_cursor")
                seen_cursors.add(cursor)
        except asyncio.CancelledError:
            result.reason = "cancelled"
            self.discovery_results[server_name] = result
            raise
        except asyncio.TimeoutError:
            result.reason = "discovery_timeout"
        except Exception as exc:
            result.reason = _transport_reason(exc) or "discovery_invalid_or_failed"
        if not result.complete and previous and previous.complete:
            result.cache_observed_at = previous.observed_at
        self.discovery_results[server_name] = result
        return result

    async def list_tools(self, server_name: str) -> List[Tool]:
        """Compatibility adapter: incomplete discovery is never an empty inventory."""
        result = await self.discover_tools(server_name)
        if not result.complete:
            raise RuntimeError(result.reason)
        return list(result.tools)

    async def call_tool(self, server_name: str, tool_name: str, tool_args: Dict[str, Any],
                        *, expected_schema_digest: str = "", expected_output_digest: str = "") -> ToolResult:
        from .tool_identity import canonical_id
        started, monotonic = utc_now(), time.monotonic()
        identity = dict(execution_id=uuid.uuid4().hex, canonical_tool_id=canonical_id(server_name, tool_name),
                        server_id=server_name, wire_name=tool_name, started_at=started)
        if server_name in HTTP_READ_TOOLS and (tool_name not in HTTP_READ_TOOLS[server_name]
                or not http_arguments_allowed(server_name, tool_args)):
            return ToolResult(**identity, status="failed", is_error=True, reason_code="http_tool_denied",
                              result_received=False, may_have_executed=False)
        sent = False
        try:
            # A fresh session must validate the snapshot from the discovery client.
            discovery = await self.discover_tools(server_name, refresh=True)
            current = next((tool for tool in discovery.tools if tool.name == tool_name), None)
            server = self.server_registery.get_server(server_name)
            allowed = server.allowed_tools if server else []
            reason = ((discovery.reason or "discovery_incomplete") if not discovery.complete else
                      "tool_unavailable" if current is None or (allowed is not None and tool_name not in allowed)
                      or (isinstance(((current.meta or {}).get("ui") or {}).get("visibility"), list)
                          and "model" not in current.meta["ui"]["visibility"])
                      or (server_name in HTTP_READ_TOOLS and not http_tool_is_read_only(server_name, current))
                      or (server and server.require_read_only and (not current.annotations or current.annotations.readOnlyHint is not True)) else
                      "schema_changed" if (expected_schema_digest and schema_digest(current.inputSchema) != expected_schema_digest)
                      or (expected_output_digest and schema_digest(current.outputSchema) != expected_output_digest) else "")
            if reason:
                return ToolResult(**identity, status="failed", is_error=True, reason_code=reason,
                                  result_received=False, may_have_executed=False, completed_at=utc_now(),
                                  duration_seconds=time.monotonic()-monotonic)
            validate_arguments(current.inputSchema, tool_args)
            if current.outputSchema is not None:
                resolved_schema(current.outputSchema, require_object=False)
            session = await self._ensure_server_running_and_get_session(server_name)
            sent = True
            response = await session.call_tool(tool_name, tool_args)
            result = normalize_result(response, **identity)
        except asyncio.CancelledError:
            # Preserve caller cancellation; do not issue an automatic retry.
            self.last_call_result = ToolResult(**identity, status="cancelled", is_error=True,
                                              reason_code="cancelled", result_received=False, may_have_executed=sent,
                                              completed_at=utc_now(), duration_seconds=time.monotonic()-monotonic)
            raise
        except OutputValidationFailure as exc:
            result = normalize_result(exc.result, **identity)
            result.status, result.is_error = "failed", True
            result.reason_code = "output_schema_invalid"
        except SchemaError as exc:
            result = ToolResult(**identity, status="failed", is_error=True, reason_code=exc.code,
                                result_received=False, may_have_executed=False)
        except McpError as exc:
            # SDK timeouts may arrive as protocol exceptions after dispatch.
            timeout = "timed out" in str(exc).lower() or "timeout" in str(exc).lower()
            result = ToolResult(**identity, status="unknown" if sent else "failed", is_error=True, protocol_error="mcp_protocol_error",
                                reason_code="timeout" if timeout else "mcp_protocol_error", result_received=False, may_have_executed=sent)
        except Exception as exc:
            result = ToolResult(**identity, status="unknown" if sent else "failed", is_error=True,
                                reason_code=_transport_reason(exc) or ("result_unknown" if sent else "transport_offline"), result_received=False, may_have_executed=sent)
        result.completed_at = utc_now()
        result.duration_seconds = time.monotonic() - monotonic
        self.last_call_result = result
        logger.info("MCPC: Tool finished status={} duration={:.3f}", result.status, result.duration_seconds)
        return result

    async def aclose(self) -> None:
        """Closes all active server connections."""
        logger.info(
            f"MCPC: Closing client instance and {len(self.active_sessions)} active connections..."
        )
        await self.exit_stack.aclose()
        self.active_sessions.clear()
        self._list_tools_cache.clear()  # Clear cache on close
        self.discovery_results.clear()
        self.exit_stack = AsyncExitStack()
        logger.info("MCPC: Client instance closed.")

    async def __aenter__(self) -> "MCPClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the async context manager."""
        await self.aclose()
        if exc_type:
            logger.error("MCPC: Async context failed; raw error omitted.")
