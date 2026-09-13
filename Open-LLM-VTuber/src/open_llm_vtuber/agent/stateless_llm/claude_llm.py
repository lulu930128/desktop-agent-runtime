"""Description: This file contains the implementation of the `AsyncLLM` class for Claude API.
This class is responsible for handling asynchronous interaction with Claude API endpoints
for language generation.
"""

import json
from typing import AsyncIterator, List, Dict, Any

from loguru import logger
from anthropic import AsyncAnthropic, NOT_GIVEN

from .stateless_llm_interface import StatelessLLMInterface


class AsyncLLM(StatelessLLMInterface):
    def __init__(
        self,
        model: str = "claude-3-haiku-latest",
        base_url: str = None,
        llm_api_key: str = None,
        system: str = None,
    ):
        """
        Initialize Claude LLM.

        Args:
            model (str): Model name
            base_url (str): Base URL for Claude API
            llm_api_key (str): Claude API key
            system (str): System prompt
        """
        self.model = model
        self.system = system

        # Initialize Claude client
        self.client = AsyncAnthropic(
            api_key=llm_api_key, base_url=base_url if base_url else None
        )

        logger.info('Initialized Claude AsyncLLM with model; payload details omitted.')
        logger.debug('Base URL; payload details omitted.')

    def _convert_message_format(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert message format to Claude's expected format."""
        # Handle potential tool_result content blocks
        if isinstance(message.get("content"), list):
            new_content = []
            is_tool_result = False
            for content_item in message["content"]:
                if content_item.get("type") == "image_url":
                    # Extract media type and base64 data from data URL
                    data_url = content_item["image_url"]["url"]
                    # Split 'data:image/jpeg;base64,/9j/4AAQ...' into parts
                    header, base64_data = data_url.split(",", 1)
                    # Extract media type from 'data:image/jpeg;base64'
                    media_type = header.split(":")[1].split(";")[0]

                    new_content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_data,
                            },
                        }
                    )
                elif content_item.get("type") == "tool_result":
                    is_tool_result = True
                    # Keep tool_result block as is, Anthropic SDK handles it
                    new_content.append(content_item)
                else:
                    # Assume text or other standard types
                    new_content.append(content_item)

            # For tool_result messages, the role should be 'user'
            # Ensure the role is correctly set before returning
            role = "user" if is_tool_result else message["role"]
            return {"role": role, "content": new_content}

        # Handle plain text content or non-list content
        return message

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: str = None,
        tools: List[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Generates a chat completion using the Claude API asynchronously,
        handling text generation and tool use.

        Parameters:
        - messages (List[Dict[str, Any]]): The list of messages to send to the API.
        - system (str, optional): System prompt to use for this completion.
        - tools (List[Dict[str, Any]], optional): List of tools available.

        Yields:
        - Dict[str, Any]: Events representing text deltas, tool use, or errors.
          Possible event types:
            - {"type": "message_start", "data": ...}
            - {"type": "text_delta", "text": "..."}
            - {"type": "tool_use_start", "data": {"id": ..., "name": ..., "input": None}}
            - {"type": "tool_input_delta", "tool_id": ..., "partial_json": "..."} # Optional
            - {"type": "tool_use_complete", "data": {"id": ..., "name": ..., "input": {...}}}
            - {"type": "message_delta", "data": ...} # e.g., stop_reason
            - {"type": "message_stop"}
            - {"type": "error", "message": "..."}
        """
        try:
            # Filter out system messages and convert message format
            converted_messages = [
                self._convert_message_format(msg)
                for msg in messages
                if msg["role"] != "system"
            ]

            logger.debug('Sending messages to Claude API; payload details omitted.')
            logger.debug('Tools provided; payload details omitted.')

            async with self.client.messages.stream(
                messages=converted_messages,
                system=system if system else (self.system if self.system else ""),
                model=self.model,
                max_tokens=1024,
                tools=tools if tools else NOT_GIVEN,
            ) as stream:
                current_tool_call_info = None
                partial_json_accumulator = ""

                async for event in stream:
                    if event.type == "message_start":
                        logger.debug("Stream: message_start")
                        yield {
                            "type": "message_start",
                            "data": event.message.model_dump(exclude_none=True),
                        }
                    elif event.type == "content_block_start":
                        logger.debug('Stream: content_block_start - Index; payload details omitted.')
                        if event.content_block.type == "text":
                            pass  # Handled by text_delta
                        elif event.content_block.type == "tool_use":
                            current_tool_call_info = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input": None,
                                "index": event.index,  # Store index
                            }
                            partial_json_accumulator = ""
                            logger.debug('Stream: tool_use started - ID; payload details omitted.')
                            yield {
                                "type": "tool_use_start",
                                "data": current_tool_call_info.copy(),
                            }
                    elif event.type == "content_block_delta":
                        logger.debug('Stream: content_block_delta - Index; payload details omitted.')
                        if event.delta.type == "text_delta":
                            yield {"type": "text_delta", "text": event.delta.text}
                        elif event.delta.type == "input_json_delta":
                            if (
                                current_tool_call_info
                                and event.index == current_tool_call_info["index"]
                            ):
                                partial_json_accumulator += event.delta.partial_json
                                logger.trace('Stream: input_json_delta - Tool ID; payload details omitted.')
                            else:
                                logger.warning('Received input_json_delta but no active tool call matching index; payload details omitted.')
                    elif event.type == "content_block_stop":
                        logger.debug('Stream: content_block_stop - Index; payload details omitted.')
                        # Check if this stop corresponds to the active tool call
                        if (
                            current_tool_call_info
                            and event.index == current_tool_call_info["index"]
                        ):
                            try:
                                if not partial_json_accumulator.strip():
                                    logger.warning('Empty JSON input received for tool ID; payload details omitted.')
                                    tool_input = {}
                                else:
                                    tool_input = json.loads(partial_json_accumulator)
                                current_tool_call_info["input"] = tool_input
                                logger.debug('Stream: tool_use completed - ID; payload details omitted.')
                                # Yield the complete tool call info
                                yield {
                                    "type": "tool_use_complete",
                                    "data": current_tool_call_info.copy(),
                                }
                            except json.JSONDecodeError as e:
                                logger.error('Failed to decode tool input JSON; payload details omitted.')
                                yield {
                                    "type": "error",
                                    "message": f"Failed to parse tool input JSON for tool ID {current_tool_call_info['id']}",
                                }
                            finally:
                                # Reset regardless of success or failure for this index
                                current_tool_call_info = None
                                partial_json_accumulator = ""
                    elif event.type == "message_delta":
                        logger.debug('Stream: message_delta - Delta; payload details omitted.')
                        yield {
                            "type": "message_delta",
                            "data": {
                                "delta": event.delta.model_dump(exclude_none=True),
                                "usage": event.usage.model_dump(),
                            },
                        }
                    elif event.type == "message_stop":
                        logger.debug("Stream: message_stop")
                        yield {"type": "message_stop"}
                        # No need to break here, the context manager handles the end
                    elif event.type == "ping":
                        logger.trace("Stream: ping")
                        pass  # Ignore pings
                    # Anthropic SDK might raise errors directly, or via event.type == 'error'
                    # The outer try/except handles SDK-level errors.

        except Exception as e:
            logger.error('Claude API error occurred; payload details omitted.')
            logger.info('Model; payload details omitted.')
            # Yield an error event before raising
            yield {"type": "error", "message": "Claude API failed; private error details omitted."}
            raise RuntimeError("Claude API failed; private error details omitted.") from None

        # No finally block needed for stream.close() due to async with
        logger.debug("Chat completion stream processing finished.")
