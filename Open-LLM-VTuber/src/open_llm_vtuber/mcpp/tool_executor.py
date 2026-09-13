import json
import datetime
import asyncio
from .privacy import argument_summary, project, safe_text, secret_values
from .tool_identity import canonical_id, legacy_name
from .tool_schema import validate_arguments, SchemaError, schema_digest
from .tool_result import ToolResult
from loguru import logger
from typing import (
    Dict,
    Any,
    List,
    Literal,
    Union,
    AsyncIterator,
)

from .types import ToolCallObject
from .mcp_client import MCPClient
from .tool_manager import ToolManager
from .tool_policy_manager import ToolPolicy, ToolPolicyDecision
from .tool_catalog_manager import normalize_thinking_power


class ToolExecutor:
    def __init__(
        self,
        mcp_client: MCPClient,
        tool_manager: ToolManager,
        thinking_power: str = "normal",
    ):
        self._mcp_client = mcp_client
        self._tool_manager = tool_manager
        self._tool_policy = ToolPolicy.load_default()
        self._thinking_power = normalize_thinking_power(thinking_power)

    def parse_tool_call(self, call: Union[Dict[str, Any], ToolCallObject]) -> tuple:
        """Parse tool call from different formats.

        Returns:
            tuple: (tool_name, tool_id, tool_input, is_error, result_content, parse_error)
        """
        tool_name: str = ""
        tool_id: str = ""
        tool_input: Any = None
        is_error: bool = False
        result_content: str | dict = ""
        parse_error: bool = False

        if isinstance(call, ToolCallObject):
            tool_name = getattr(call.function, "name", "")
            tool_id = call.id
            try:
                tool_input = json.loads(getattr(call.function, "arguments", None))
            except (json.JSONDecodeError, TypeError):
                logger.error("Failed to decode tool arguments; payload omitted.")
                result_content = "Error: Invalid tool arguments format."
                is_error = True
                parse_error = True
        elif isinstance(call, dict):
            tool_id = call.get("id")
            tool_name = call.get("name")
            tool_input = call.get("input", call.get("args"))

            if tool_input is None:
                tool_input = {}

            if not tool_id or not tool_name:
                logger.error("Invalid tool call structure; payload omitted.")
                result_content = "Error: Invalid tool call structure from LLM."
                is_error = True
                parse_error = True
        else:
            logger.error('Unsupported tool call type; payload details omitted.')
            result_content = "Error: Unsupported tool call type."
            is_error = True
            parse_error = True

        if not isinstance(tool_name, str) or not isinstance(tool_id, str):
            tool_name, tool_id = "", ""
            is_error = parse_error = True
            result_content = "Error: Invalid tool call identity."
        return tool_name, tool_id, tool_input, is_error, result_content, parse_error

    def format_tool_result(
        self,
        caller_mode: Literal["Claude", "OpenAI", "Prompt"],
        tool_id: str,
        result_content: str,
        is_error: bool,
    ) -> Dict[str, Any] | None:
        """Format tool result for LLM API."""
        if caller_mode == "Claude":
            # Claude expects content as a list of blocks or a simple string
            # We will return a list if there are multiple items or non-text items
            if isinstance(result_content, list):
                # Already formatted as list of blocks
                content_to_send = result_content
            elif isinstance(result_content, str) and result_content:
                # Simple text result
                content_to_send = result_content
            elif not result_content and is_error:
                # Error case, send error message as string
                content_to_send = "Error occurred during tool execution."
            else:
                # Fallback for empty or unexpected content
                content_to_send = ""

            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": content_to_send,
                "is_error": is_error,
            }
        elif caller_mode == "OpenAI":
            # OpenAI expects content as a string
            return {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": str(result_content),
            }
        elif caller_mode == "Prompt":
            # Prompt mode also expects a string content for now
            return {
                "tool_id": tool_id,
                "content": str(result_content),
                "is_error": is_error,
            }
        return None

    def process_tool_from_prompt_json(
        self, data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process tool data from JSON in prompt mode."""
        parsed_tools = []
        for item in data:
            if not isinstance(item, dict):
                continue
            server = item.get("mcp_server")
            tool_name = item.get("tool")
            arguments_str = item.get("arguments")
            if all([server, tool_name, arguments_str]):
                try:
                    args_dict = json.loads(arguments_str)
                    parsed_tools.append(
                        {
                            "name": tool_name if tool_name.startswith(canonical_id(server, "_")[:-1]) else canonical_id(server, tool_name),
                            "server": server,
                            "args": args_dict,
                            "id": f"prompt_tool_{len(parsed_tools)}",
                        }
                    )
                    logger.info("Parsed tool call from prompt JSON.")
                except json.JSONDecodeError:
                    logger.error(
                        "Failed to decode arguments JSON in prompt mode tool call"
                    )
                except Exception as e:
                    logger.error('Error processing prompt mode tool dict; payload details omitted.')
            else:
                logger.warning("Skipping invalid tool structure in prompt mode JSON")
        return parsed_tools

    async def execute_tools(
        self,
        tool_calls: Union[List[Dict[str, Any]], List[ToolCallObject]],
        caller_mode: Literal["Claude", "OpenAI", "Prompt"],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute tools and yield status updates."""
        tool_results_for_llm = []

        logger.info(f"Executing {len(tool_calls)} tool(s) for {caller_mode} caller.")
        for call in tool_calls:
            (
                tool_name,
                tool_id,
                tool_input,
                is_error,
                result_content,
                parse_error,
            ) = self.parse_tool_call(call)

            logger.info("Executing tool call; payload omitted.")

            if parse_error:
                logger.warning('Skipping tool call due to parsing error; payload details omitted.')
                status_update = {
                    "type": "tool_call_status",
                    "tool_id": tool_id
                    or f"parse_error_{datetime.datetime.now(datetime.timezone.utc).isoformat()}",
                    "tool_name": tool_name or "Unknown Tool",
                    "status": "error",
                    "content": result_content,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
                yield status_update
                # Even on parse error, we might need to format a result for the LLM
                # Use dummy values or the error message
                formatted_result = self.format_tool_result(
                    caller_mode,
                    tool_id
                    or f"parse_error_{datetime.datetime.now(datetime.timezone.utc).isoformat()}",
                    result_content,
                    True,  # is_error
                )
                if formatted_result:
                    tool_results_for_llm.append(formatted_result)
                continue  # Skip execution logic for this call

            api_tool_name = tool_name
            tool_name = self._tool_manager.resolve_tool_name(tool_name)
            if tool_name != api_tool_name:
                logger.debug(
                    f"Resolved API tool name '{api_tool_name}' to MCP tool '{tool_name}'."
                )

            tool_input = self._apply_thinking_power(tool_name, tool_input)

            policy_decision = self.check_call(tool_name, tool_input)
            if not policy_decision.allowed:
                logger.warning("Tool call blocked by runtime policy: {}", policy_decision.reason_code)
                status_update = {
                    "type": "tool_call_status",
                    "tool_id": tool_id,
                    "tool_name": tool_name if self._tool_manager.get_tool(tool_name) else "Unavailable tool",
                    "status": policy_decision.status,
                    "reason_code": policy_decision.reason_code,
                    "content": policy_decision.reason,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
                yield status_update

                formatted_result = self.format_tool_result(
                    caller_mode,
                    tool_id,
                    f"Tool call blocked by runtime policy: {policy_decision.reason}",
                    True,
                )
                if formatted_result:
                    tool_results_for_llm.append(formatted_result)
                continue

            # Yield 'running' status before execution
            yield {
                "type": "tool_call_status",
                "tool_id": tool_id,
                "tool_name": tool_name,
                "status": "running",
                "content": argument_summary(tool_input),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            # Execute the tool
            try:
                (
                    is_error,
                    text_content,
                    metadata,
                    content_items,
                ) = await self.run_single_tool(tool_name, tool_id, tool_input)
            except asyncio.CancelledError:
                yield {"type": "tool_call_status", "tool_id": tool_id, "tool_name": tool_name,
                       "status": "error", "execution_status": "cancelled", "reason_code": "cancelled",
                       "content": "Tool call cancelled; execution outcome may be unknown.",
                       "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                raise

            # Determine content for status update and LLM result format
            status_content = safe_text(text_content, limit=2048)
            llm_formatted_content = text_content  # Default to text content for LLM

            if caller_mode == "Claude" and "claude_content" in metadata:
                llm_formatted_content = metadata["claude_content"]

            # Prepare and yield tool call status update
            status_update = {
                "type": "tool_call_status",
                "tool_id": tool_id,
                "tool_name": tool_name,
                "status": "error" if is_error else "completed",
                "execution_status": metadata.get("execution_status", "failed" if is_error else "succeeded"),
                "reason_code": metadata.get("reason_code", ""),
                "content": safe_text(status_content, limit=2048)
                if not is_error
                else safe_text(f"Error: {text_content}", limit=2048),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            if legacy_name(tool_name) in {"omi.ask", "omi.ask_stream"}:
                from .market_preflight import build_omi_evidence_snapshot
                evidence = metadata.get("omi_evidence") or build_omi_evidence_snapshot(text_content)
                if evidence:
                    status_update["omi_evidence"] = project(evidence)

            # Only the allowlisted result metadata is exposed; no arbitrary browser URLs.
            if tool_name == "stagehand_navigate" and not is_error:
                live_view_data = metadata.get("liveViewData", {})
                if live_view_data:
                    logger.info('Found live view data for stagehand_navigate; payload details omitted.')
                    status_update["browser_view"] = live_view_data

            yield status_update

            # Format result for LLM and add to list
            formatted_result = self.format_tool_result(
                caller_mode, tool_id, llm_formatted_content, is_error
            )
            if formatted_result:
                tool_results_for_llm.append(formatted_result)

        logger.info(
            f"Finished executing tools with {len(tool_results_for_llm)} results."
        )
        yield {"type": "final_tool_results", "results": tool_results_for_llm}

    def check_call(self, tool_name: str, tool_input: Any) -> ToolPolicyDecision:
        info = self._tool_manager.get_tool(tool_name)
        if not info:
            return ToolPolicyDecision(False, "blocked", "Tool is unavailable in this tool snapshot.", "tool_unavailable")
        identity = info.canonical_id or canonical_id(info.related_server, info.wire_name or legacy_name(tool_name))
        policy = getattr(self, "_tool_policy", None)
        if policy is None:
            return ToolPolicyDecision(False, "blocked", "Policy unavailable.", "policy_unavailable")
        decision = policy.check(identity, tool_input)
        if not decision.allowed:
            return decision
        try:
            if info.schema_digest and schema_digest(info.input_schema) != info.schema_digest:
                raise SchemaError("schema_changed")
            validate_arguments(info.input_schema, tool_input)
        except SchemaError as exc:
            return ToolPolicyDecision(False, "blocked", exc.code, exc.code)
        return decision

    async def run_single_tool(
        self, tool_name: str, tool_id: str, tool_input: Any
    ) -> tuple[bool, str, Dict[str, Any], List[Dict[str, Any]]]:
        """Run a single tool using MCPClient.

        Returns:
            tuple: (is_error, text_content, metadata, content_items)
        """
        logger.info("Executing validated tool call.")
        tool_info = self._tool_manager.get_tool(tool_name)

        is_error = False
        text_content = ""
        metadata = {}
        content_items = []

        if tool_input is None:
            tool_input = {}

        if tool_info:
            identity = tool_info.canonical_id or canonical_id(tool_info.related_server, tool_info.wire_name or legacy_name(tool_name))
            decision = self._tool_policy.check(identity, tool_input) if self._tool_policy else None
            if decision is None or not decision.allowed:
                text = decision.reason if decision else "Policy unavailable."
                return True, text, {}, [{"type": "text", "text": text}]
            try:
                if tool_info.schema_digest and schema_digest(tool_info.input_schema) != tool_info.schema_digest:
                    raise SchemaError("schema_changed")
                validate_arguments(tool_info.input_schema, tool_input)
            except SchemaError as exc:
                return True, exc.code, {}, [{"type": "text", "text": exc.code}]

        if not tool_info:
            logger.error("Tool unavailable in ToolManager.")
            text_content = "Error: Tool is not available."
            content_items = [{"type": "error", "text": text_content}]
            is_error = True
        elif not tool_info.related_server:
            logger.error(f"Tool '{tool_name}' does not have a related server defined.")
            text_content = f"Error: Configuration error for tool '{tool_name}'. No server specified."
            content_items = [{"type": "error", "text": text_content}]
            is_error = True
        else:
            try:
                result_dict = await self._mcp_client.call_tool(
                    server_name=tool_info.related_server,
                    tool_name=tool_info.wire_name or legacy_name(tool_name),
                    tool_args=tool_input,
                    expected_schema_digest=schema_digest(tool_info.input_schema),
                    expected_output_digest=schema_digest(tool_info.output_schema),
                )

                if isinstance(result_dict, ToolResult):
                    result_dict.policy_digest = self._tool_policy.digest
                    result_dict.execution_id = tool_id
                    is_error = result_dict.is_error
                    secrets = secret_values(tool_input)
                    text_content = result_dict.model_text(
                        secrets=secrets, limit=65536 if legacy_name(identity).startswith("omi.") else 128*1024,
                    )
                    # Raw results remain local to this invocation; legacy consumers get a safe copy.
                    content_items = project(result_dict.content_items, secrets=secrets)
                    metadata = {"execution_status": result_dict.status, "reason_code": result_dict.reason_code,
                                "claude_content": result_dict.claude_content(secrets=secrets, limit=65536 if legacy_name(identity).startswith("omi.") else 128*1024)}
                    if legacy_name(identity) in {"omi.ask", "omi.ask_stream"}:
                        from .market_preflight import build_omi_evidence_snapshot
                        source_text = json.dumps(project(result_dict.structured_content, secrets=secrets), ensure_ascii=False) if result_dict.structured_content is not None else text_content
                        metadata["omi_evidence"] = build_omi_evidence_snapshot(source_text)
                    return is_error, text_content, metadata, content_items
                # Compatibility is limited to the old internal result envelope.
                metadata = {}
                content_items = project(result_dict.get("content_items", []), secrets=secret_values(tool_input))

                is_error = bool(result_dict.get("isError")) or any(item.get("type") == "error" for item in content_items)
                text_content = safe_text("\n".join(item.get("text", "") for item in content_items if "text" in item))
                logger.info("Legacy tool result received; payload omitted.")

            except (ValueError, RuntimeError, ConnectionError):
                logger.error("Tool execution failed; raw exception omitted.")
                text_content = "Tool execution failed; outcome is unknown."
                content_items = [{"type": "error", "text": text_content}]
                is_error = True
            except Exception:
                logger.error("Tool execution failed; raw exception omitted.")
                text_content = "Tool execution failed; outcome is unknown."
                content_items = [{"type": "error", "text": text_content}]
                is_error = True

        return is_error, text_content, metadata, content_items

    def _apply_thinking_power(self, tool_name: str, tool_input: Any) -> Any:
        """Clamp web-search tool arguments according to launcher thinking power."""
        tool_name = legacy_name(tool_name)
        if not isinstance(tool_input, dict):
            return tool_input

        args = dict(tool_input)
        power = self._thinking_power

        if tool_name == "search_web":
            if power == "fast":
                args["max_results"] = min(_as_int(args.get("max_results"), 3), 3)
            elif power == "deep":
                args["max_results"] = min(max(_as_int(args.get("max_results"), 8), 8), 10)
            else:
                args["max_results"] = min(_as_int(args.get("max_results"), 5), 5)
        elif tool_name == "smart_search_web":
            if power == "fast":
                args["max_results"] = min(_as_int(args.get("max_results"), 3), 3)
                args["fetch_top_pages"] = 0
            elif power == "deep":
                args["max_results"] = min(max(_as_int(args.get("max_results"), 8), 6), 8)
                args["fetch_top_pages"] = min(max(_as_int(args.get("fetch_top_pages"), 3), 3), 3)
            else:
                args["max_results"] = min(_as_int(args.get("max_results"), 5), 5)
                args["fetch_top_pages"] = min(_as_int(args.get("fetch_top_pages"), 2), 2)
        elif tool_name == "advanced_search_web":
            args["depth"] = power
            if power == "fast":
                args["max_results"] = min(_as_int(args.get("max_results"), 4), 4)
                args["fetch_top_pages"] = min(_as_int(args.get("fetch_top_pages"), 0), 1)
            elif power == "deep":
                args["max_results"] = min(max(_as_int(args.get("max_results"), 10), 8), 12)
                args["fetch_top_pages"] = min(max(_as_int(args.get("fetch_top_pages"), 4), 3), 5)
            else:
                args["max_results"] = min(_as_int(args.get("max_results"), 6), 6)
                args["fetch_top_pages"] = min(_as_int(args.get("fetch_top_pages"), 2), 2)
        elif tool_name == "fetch_content":
            if power == "fast":
                args["max_chars"] = min(_as_int(args.get("max_chars"), 1800), 2000)
            elif power == "deep":
                args["max_chars"] = min(max(_as_int(args.get("max_chars"), 10000), 8000), 12000)
            else:
                args["max_chars"] = min(_as_int(args.get("max_chars"), 4000), 5000)

        return args


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default
