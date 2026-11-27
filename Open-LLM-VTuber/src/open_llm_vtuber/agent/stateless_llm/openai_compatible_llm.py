"""Description: This file contains the implementation of the `AsyncLLM` class.
This class is responsible for handling asynchronous interaction with OpenAI API compatible
endpoints for language generation.
"""

import re
from typing import AsyncIterator, List, Dict, Any
from openai import (
    AsyncStream,
    AsyncOpenAI,
    APIError,
    APIConnectionError,
    RateLimitError,
    NotGiven,
    NOT_GIVEN,
)
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall
from loguru import logger

from .stateless_llm_interface import StatelessLLMInterface
from ...mcpp.types import ToolCallObject


def _safe_failure_field(value: Any, field: str) -> str:
    """Accept bounded identifiers only, never stringify or truncate payloads."""
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return "unknown"
    if any(token in value.lower() for token in ("sk-", "bearer", "http", "www.")):
        return "unknown"
    patterns = {
        "param": r"[a-zA-Z_][a-zA-Z_0-9]*(?:\[[0-9]{1,6}\]|\.[a-zA-Z_][a-zA-Z_0-9]*)*",
        "request_id": r"req_[a-zA-Z0-9_-]{1,100}",
    }
    return value if re.fullmatch(patterns.get(field, r"[a-z][a-z0-9_]{0,63}"), value, re.ASCII) else "unknown"


def _failure_value(source: Any, key: str) -> Any:
    return source.get(key) if isinstance(source, dict) else getattr(source, key, None)


def _report_responses_failure(category: str, source: Any = None, *,
                              status: Any = None, request_id: Any = None,
                              reason: Any = None) -> str:
    """Emit safe metadata only, never raw exceptions, bodies or messages."""
    fields = {
        "category": category,
        "status": status if type(status) is int and 100 <= status <= 599 else "unknown",
        **{key: _safe_failure_field(_failure_value(source, key), key)
           for key in ("type", "code", "param")},
        "reason": _safe_failure_field(reason, "reason"),
    }
    if request_id is not None:
        fields["request_id"] = _safe_failure_field(request_id, "request_id")
    logger.bind(**fields).error("llm_api_failure " + " ".join(
        f"{key}={value}" for key, value in fields.items()))
    labels = {
        "connection": "無法連線至 LLM API", "rate_limit": "LLM API 請求受限",
        "api_error": "LLM API 請求失敗", "response.failed": "LLM 回覆失敗",
        "response.incomplete": "LLM 回覆未完成", "error": "LLM 串流失敗",
    }
    return (f"{labels[category]}（status={fields['status']}, code={fields['code']}, "
            f"param={fields['param']}, reason={fields['reason']}）。請查看 Log。")


class AsyncLLM(StatelessLLMInterface):
    def __init__(
        self,
        model: str,
        base_url: str,
        llm_api_key: str = "z",
        organization_id: str = "z",
        project_id: str = "z",
        temperature: float = 1.0,
    ):
        """
        Initializes an instance of the `AsyncLLM` class.

        Parameters:
        - model (str): The model to be used for language generation.
        - base_url (str): The base URL for the OpenAI API.
        - organization_id (str, optional): The organization ID for the OpenAI API. Defaults to "z".
        - project_id (str, optional): The project ID for the OpenAI API. Defaults to "z".
        - llm_api_key (str, optional): The API key for the OpenAI API. Defaults to "z".
        - temperature (float, optional): What sampling temperature to use, between 0 and 2. Defaults to 1.0.
        """
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.client = AsyncOpenAI(
            base_url=base_url,
            organization=organization_id,
            project=project_id,
            api_key=llm_api_key,
        )
        self.support_tools = True
        self._uses_responses = model in {
            "gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"
        } and (base_url is None or "api.openai.com" in str(base_url))
        self._responses_reasoning_effort = (
            "low" if model in {"gpt-6-astra", "gpt-6.1-sol"} else "none"
        )

        self._responses_pending_reasoning: list[dict[str, Any]] = []
        self._responses_pending_call_ids: set[str] = set()
        logger.info('Initialized AsyncLLM with the parameters; payload details omitted.')

    @staticmethod
    def _responses_content(content: Any, role: str) -> Any:
        """Convert Chat blocks only at the Responses boundary, preserving order."""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            raise ValueError("Unsupported Responses message content shape")
        converted = []
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else None
            if kind == "text":
                if role == "assistant":
                    converted.append({"type": "output_text", "text": block["text"],
                                      "annotations": []})
                else:
                    converted.append({"type": "input_text", "text": block["text"]})
            elif kind == "image_url":
                image = block["image_url"]
                converted.append({"type": "input_image", "image_url": image["url"],
                                  "detail": image.get("detail", "auto")})
            else:
                # Do not expose arbitrary type values or payloads in exceptions/logs.
                raise ValueError("Unsupported Responses content block type (unknown)")
        return converted

    @staticmethod
    def _responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Translate the agent's existing Chat messages to Responses items.

        Tool call IDs remain unchanged, so the existing MCP executor and
        conversation history can keep their Chat-style internal contract.
        """
        items = []
        for message in messages:
            role = message.get("role")
            if role == "assistant" and message.get("tool_calls"):
                if message.get("content"):
                    items.append({"role": "assistant", "content": AsyncLLM._responses_content(message["content"], role)})
                for tool in message["tool_calls"]:
                    function = tool.get("function") or {}
                    items.append({
                        "type": "function_call",
                        "call_id": tool["id"],
                        "name": function["name"],
                        "arguments": function["arguments"],
                    })
            elif role == "tool":
                output = message.get("content", "")
                if not isinstance(output, str):
                    import json
                    output = json.dumps(output, ensure_ascii=False)
                items.append({
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": output,
                })
            elif role in {"system", "developer", "user", "assistant"}:
                if message.get("content") is not None:
                    items.append({"role": role, "content": AsyncLLM._responses_content(message["content"], role)})
        return items

    def _responses_input_with_reasoning(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Attach the last tool turn's opaque reasoning before its tool calls."""
        items = self._responses_input(messages)
        if self._responses_pending_reasoning and self._responses_pending_call_ids:
            for index, item in enumerate(items):
                if (item.get("type") == "function_call"
                        and item.get("call_id") in self._responses_pending_call_ids):
                    items[index:index] = self._responses_pending_reasoning
                    break
        return items

    async def _responses_completion(
        self,
        messages: List[Dict[str, Any]],
        system: str | None,
        tools: List[Dict[str, Any]] | NotGiven,
    ) -> AsyncIterator[str | List[ToolCallObject]]:
        """Stream GPT-6 Responses events through the existing agent interface."""
        api_tools = []
        if tools is not NOT_GIVEN and tools is not None and self.support_tools:
            for tool in tools:
                function = tool.get("function", {})
                if not function.get("name"):
                    continue
                api_tools.append({
                    "type": "function",
                    "name": function["name"],
                    "description": function.get("description", ""),
                    "parameters": function.get("parameters", {"type": "object", "properties": {}}),
                    "strict": False,
                })

        params = {
            "model": self.model,
            "input": self._responses_input_with_reasoning(messages),
            "stream": True,
            "store": False,
            "reasoning": {"effort": self._responses_reasoning_effort},
        }
        if system:
            params["instructions"] = system
        if api_tools:
            params["tools"] = api_tools

        stream = None
        calls: dict[int, dict[str, Any]] = {}
        reasoning_items: list[dict[str, Any]] = []
        self._responses_pending_reasoning = []
        self._responses_pending_call_ids = set()

        def update_call(index: int, item: Any) -> None:
            if getattr(item, "type", None) != "function_call":
                return
            row = calls.setdefault(index, {"name": "", "call_id": "", "arguments": ""})
            if getattr(item, "name", None):
                row["name"] = item.name
            if getattr(item, "call_id", None):
                row["call_id"] = item.call_id
            if isinstance(getattr(item, "arguments", None), str):
                row["arguments"] = item.arguments

        try:
            stream = await self.client.responses.create(**params)
            async for event in stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    if getattr(event, "delta", None):
                        yield event.delta
                elif kind in {"response.output_item.added", "response.output_item.done"}:
                    item = getattr(event, "item", None)
                    update_call(getattr(event, "output_index", 0), item)
                    if kind == "response.output_item.done" and getattr(item, "type", None) == "reasoning":
                        value = item.model_dump(mode="json", exclude_none=True) if hasattr(item, "model_dump") else item
                        if isinstance(value, dict) and value.get("encrypted_content"):
                            reasoning_items.append(value)
                elif kind == "response.function_call_arguments.delta":
                    index = getattr(event, "output_index", 0)
                    row = calls.setdefault(index, {"name": "", "call_id": "", "arguments": ""})
                    row["arguments"] += getattr(event, "delta", "")
                elif kind == "response.function_call_arguments.done":
                    index = getattr(event, "output_index", 0)
                    row = calls.setdefault(index, {"name": "", "call_id": "", "arguments": ""})
                    arguments = getattr(event, "arguments", None)
                    if isinstance(arguments, str):
                        row["arguments"] = arguments
                    update_call(index, getattr(event, "item", None))
                elif kind in {"response.failed", "response.incomplete", "error"}:
                    response = getattr(event, "response", None)
                    # A top-level error event's type is the event discriminator,
                    # not the API error type. Only code/param are defined there.
                    metadata = ({key: getattr(event, key, None) for key in ("code", "param")}
                                if kind == "error" else _failure_value(response, "error"))
                    details = _failure_value(response, "incomplete_details")
                    yield _report_responses_failure(
                        kind, metadata, reason=_failure_value(details, "reason"))
                    return

            if calls:
                completed = []
                for index, row in sorted(calls.items()):
                    if not row["call_id"] or not row["name"]:
                        raise RuntimeError("Responses tool call lacks call_id or name")
                    completed.append(ToolCallObject.from_dict({
                        "index": index,
                        "id": row["call_id"],
                        "type": "function",
                        "function": {"name": row["name"], "arguments": row["arguments"]},
                    }))
                self._responses_pending_reasoning = reasoning_items
                self._responses_pending_call_ids = {row.id for row in completed}
                yield completed
        except (APIConnectionError, RateLimitError, APIError) as exc:
            # Never downgrade the selected model or silently suppress tool support.
            category = ("connection" if isinstance(exc, APIConnectionError) else
                        "rate_limit" if isinstance(exc, RateLimitError) else "api_error")
            yield _report_responses_failure(
                category, exc, status=getattr(exc, "status_code", None),
                request_id=getattr(exc, "request_id", None))
        finally:
            if stream is not None:
                await stream.close()

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: str = None,
        tools: List[Dict[str, Any]] | NotGiven = NOT_GIVEN,
    ) -> AsyncIterator[str | List[ChoiceDeltaToolCall]]:
        """
        Generates a chat completion using the OpenAI API asynchronously.

        Parameters:
        - messages (List[Dict[str, Any]]): The list of messages to send to the API.
        - system (str, optional): System prompt to use for this completion.
        - tools (List[Dict[str, str]], optional): List of tools to use for this completion.

        Yields:
        - str: The content of each chunk from the API response.
        - List[ChoiceDeltaToolCall]: The tool calls detected in the response.

        Raises:
        - APIConnectionError: When the server cannot be reached
        - RateLimitError: When a 429 status code is received
        - APIError: For other API-related errors
        """
        if self._uses_responses:
            async for event in self._responses_completion(messages, system, tools):
                yield event
            return

        stream = None
        # Tool call related state variables
        accumulated_tool_calls = {}
        in_tool_call = False

        try:
            # If system prompt is provided, add it to the messages
            messages_with_system = messages
            if system:
                messages_with_system = [
                    {"role": "system", "content": system},
                    *messages,
                ]
            logger.debug('Messages; payload details omitted.')

            available_tools = tools if self.support_tools else NOT_GIVEN

            stream: AsyncStream[
                ChatCompletionChunk
            ] = await self.client.chat.completions.create(
                messages=messages_with_system,
                model=self.model,
                stream=True,
                temperature=self.temperature,
                tools=available_tools,
            )
            logger.debug('Tool Support; payload details omitted.')

            async for chunk in stream:
                if self.support_tools:
                    has_tool_calls = (
                        hasattr(chunk.choices[0].delta, "tool_calls")
                        and chunk.choices[0].delta.tool_calls
                    )

                    if has_tool_calls:
                        logger.debug('Tool calls detected in chunk; payload details omitted.')
                        in_tool_call = True
                        # Process tool calls in the current chunk
                        for tool_call in chunk.choices[0].delta.tool_calls:
                            index = (
                                tool_call.index if hasattr(tool_call, "index") else 0
                            )

                            # Initialize tool call for this index if needed
                            if index not in accumulated_tool_calls:
                                accumulated_tool_calls[index] = {
                                    "index": index,
                                    "id": getattr(tool_call, "id", None),
                                    "type": getattr(tool_call, "type", None),
                                    "function": {"name": "", "arguments": ""},
                                }

                            # Update tool call information
                            if hasattr(tool_call, "id") and tool_call.id:
                                accumulated_tool_calls[index]["id"] = tool_call.id
                            if hasattr(tool_call, "type") and tool_call.type:
                                accumulated_tool_calls[index]["type"] = tool_call.type

                            # Update function information
                            if hasattr(tool_call, "function"):
                                if (
                                    hasattr(tool_call.function, "name")
                                    and tool_call.function.name
                                ):
                                    accumulated_tool_calls[index]["function"][
                                        "name"
                                    ] = tool_call.function.name
                                if (
                                    hasattr(tool_call.function, "arguments")
                                    and tool_call.function.arguments
                                ):
                                    accumulated_tool_calls[index]["function"][
                                        "arguments"
                                    ] += tool_call.function.arguments

                        continue

                    # If we were in a tool call but now we're not, yield the tool call result
                    elif in_tool_call and not has_tool_calls:
                        in_tool_call = False
                        # Convert accumulated tool calls to the required format and output
                        logger.info('Complete tool calls; payload details omitted.')

                        # Use the from_dict method to create a ToolCallObject instance from a dictionary
                        complete_tool_calls = [
                            ToolCallObject.from_dict(tool_data)
                            for tool_data in accumulated_tool_calls.values()
                        ]

                        yield complete_tool_calls
                        accumulated_tool_calls = {}  # Reset for potential future tool calls

                # Process regular content chunks
                if len(chunk.choices) == 0:
                    logger.info("Empty chunk received")
                    continue
                elif chunk.choices[0].delta.content is None:
                    chunk.choices[0].delta.content = ""
                yield chunk.choices[0].delta.content

            # If stream ends while still in a tool call, make sure to yield the tool call
            if in_tool_call and accumulated_tool_calls:
                logger.info('Final tool call at stream end; payload details omitted.')

                # Create a ToolCallObject instance from a dictionary using the from_dict method.
                complete_tool_calls = [
                    ToolCallObject.from_dict(tool_data)
                    for tool_data in accumulated_tool_calls.values()
                ]

                yield complete_tool_calls

        except APIConnectionError as e:
            logger.error('Error calling the chat endpoint: Connection error. Failed to connect to the LLM API. \nCheck the configurations and the reachability of the LLM backend. \nSee the logs for details. \nTroubleshooting with documentation: https://open-llm-vtuber.github.io/docs/faq#%E9%81%87%E5%88%B0-error-calling-the-chat-endpoint-%E9%94%99%E8%AF%AF%E6%80%8E%E4%B9%88%E5%8A%9E; payload details omitted.')
            yield "Error calling the chat endpoint: Connection error. Failed to connect to the LLM API. Check the configurations and the reachability of the LLM backend. See the logs for details. Troubleshooting with documentation: [https://open-llm-vtuber.github.io/docs/faq#%E9%81%87%E5%88%B0-error-calling-the-chat-endpoint-%E9%94%99%E8%AF%AF%E6%80%8E%E4%B9%88%E5%8A%9E]"

        except RateLimitError as e:
            logger.error('Error calling the chat endpoint: Rate limit exceeded; payload details omitted.')
            yield "Error calling the chat endpoint: Rate limit exceeded. Please try again later. See the logs for details."

        except APIError as e:
            if "does not support tools" in str(e):
                self.support_tools = False
                logger.warning('does not support tools. Disabling tool support.; payload details omitted.')
                yield "__API_NOT_SUPPORT_TOOLS__"
                return
            logger.error('LLM API: Error occurred; payload details omitted.')
            logger.info('Base URL; payload details omitted.')
            logger.info('Model; payload details omitted.')
            logger.info('Messages; payload details omitted.')
            logger.info('temperature; payload details omitted.')
            yield "Error calling the chat endpoint: Error occurred while generating response. See the logs for details."

        finally:
            # make sure the stream is properly closed
            # so when interrupted, no more tokens will being generated.
            if stream:
                logger.debug("Chat completion finished.")
                await stream.close()
                logger.debug("Stream closed.")
