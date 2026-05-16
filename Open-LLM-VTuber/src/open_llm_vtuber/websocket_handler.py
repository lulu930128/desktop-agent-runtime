from typing import Dict, List, Optional, Callable, TypedDict
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
from enum import Enum
import numpy as np
from loguru import logger

from .service_context import ServiceContext
from .chat_group import (
    ChatGroupManager,
    handle_group_operation,
    handle_client_disconnect,
    broadcast_to_group,
)
from .message_handler import message_handler
from .utils.stream_audio import prepare_audio_payload
from .chat_history_manager import (
    create_new_history,
    get_history,
    delete_history,
    get_history_list,
    get_metadata,
    touch_history_opened,
)
from .config_manager.utils import (
    scan_config_alts_directory,
    scan_bg_directory,
    validate_config,
)
from .conversations.conversation_handler import (
    handle_conversation_trigger,
    handle_group_interrupt,
    handle_individual_interrupt,
)


class MessageType(Enum):
    """Enum for WebSocket message types"""

    GROUP = ["add-client-to-group", "remove-client-from-group"]
    HISTORY = [
        "fetch-history-list",
        "fetch-and-set-history",
        "create-new-history",
        "delete-history",
    ]
    CONVERSATION = ["mic-audio-end", "text-input", "ai-speak-signal"]
    CONFIG = ["fetch-configs", "switch-config"]
    CONTROL = ["interrupt-signal", "audio-play-start"]
    DATA = ["mic-audio-data"]


class WSMessage(TypedDict, total=False):
    """Type definition for WebSocket messages"""

    type: str
    action: Optional[str]
    text: Optional[str]
    audio: Optional[List[float]]
    images: Optional[List[str]]
    history_uid: Optional[str]
    force_new: Optional[bool]
    file: Optional[str]
    display_text: Optional[dict]


class WebSocketHandler:
    """Handles WebSocket connections and message routing"""

    def __init__(self, default_context_cache: ServiceContext):
        """Initialize the WebSocket handler with default context"""
        self.client_connections: Dict[str, WebSocket] = {}
        self.client_contexts: Dict[str, ServiceContext] = {}
        self.chat_group_manager = ChatGroupManager()
        self.current_conversation_tasks: Dict[str, Optional[asyncio.Task]] = {}
        self.default_context_cache = default_context_cache
        self.received_data_buffers: Dict[str, np.ndarray] = {}
        self.pending_history_bootstrap: Dict[str, bool] = {}

        # Message handlers mapping
        self._message_handlers = self._init_message_handlers()

    def _prune_finished_tasks(self) -> None:
        for task_key, task in list(self.current_conversation_tasks.items()):
            if task is None or task.done():
                self.current_conversation_tasks.pop(task_key, None)

    def _resolve_launcher_target(
        self, client_uid: Optional[str] = None
    ) -> tuple[Optional[str], list[str], Optional[str]]:
        connected_clients = sorted(self.client_connections.keys())
        if client_uid:
            if client_uid not in self.client_connections:
                return None, connected_clients, f"Client {client_uid} is not connected."
            return client_uid, connected_clients, None

        if len(connected_clients) == 1:
            return connected_clients[0], connected_clients, None
        if len(connected_clients) == 0:
            return None, connected_clients, None
        return None, connected_clients, "Multiple frontend clients are connected; hot switch is ambiguous."

    def _is_client_idle_for_switch(self, client_uid: str) -> tuple[bool, str]:
        self._prune_finished_tasks()

        group = self.chat_group_manager.get_client_group(client_uid)
        if group and len(group.members) > 1:
            return False, "The active frontend is in a multi-member group; hot switch is disabled."

        task_key = group.group_id if group else client_uid
        task = self.current_conversation_tasks.get(task_key)
        if task and not task.done():
            return False, "A conversation turn is still running or audio playback has not fully finished."

        return True, "idle"

    def _ordered_histories(
        self, conf_uid: str, selected_uid: Optional[str] = None
    ) -> list[dict]:
        histories = get_history_list(conf_uid)
        if not selected_uid:
            return histories

        selected_uid = str(selected_uid).strip()
        selected = None
        remaining = []
        for item in histories:
            if str(item.get("uid") or "") == selected_uid and selected is None:
                selected = item
            else:
                remaining.append(item)
        if selected is None:
            return histories
        return [selected, *remaining]

    def _load_history_into_context(
        self, context: ServiceContext, history_uid: str
    ) -> list[dict]:
        context.history_uid = history_uid
        context.agent_engine.set_memory_from_history(
            conf_uid=context.character_config.conf_uid,
            history_uid=history_uid,
        )
        touch_history_opened(context.character_config.conf_uid, history_uid)
        return [
            msg
            for msg in get_history(
                context.character_config.conf_uid,
                history_uid,
            )
            if msg["role"] != "system"
        ]

    async def _push_history_selection(
        self,
        websocket: WebSocket,
        context: ServiceContext,
        history_uid: str,
    ) -> dict:
        messages = self._load_history_into_context(context, history_uid)
        histories = self._ordered_histories(
            context.character_config.conf_uid,
            history_uid,
        )
        await websocket.send_text(
            json.dumps({"type": "history-list", "histories": histories})
        )
        await websocket.send_text(
            json.dumps({"type": "history-data", "messages": messages})
        )
        metadata = get_metadata(context.character_config.conf_uid, history_uid)
        return {
            "history_uid": history_uid,
            "messages": messages,
            "histories": histories,
            "title": str(metadata.get("title") or "").strip(),
        }

    async def _create_history_for_context(
        self,
        websocket: WebSocket,
        context: ServiceContext,
    ) -> dict:
        history_uid = create_new_history(context.character_config.conf_uid)
        if not history_uid:
            raise RuntimeError("Failed to create a new history thread.")

        context.history_uid = history_uid
        context.agent_engine.set_memory_from_history(
            conf_uid=context.character_config.conf_uid,
            history_uid=history_uid,
        )
        touch_history_opened(context.character_config.conf_uid, history_uid)

        histories = self._ordered_histories(
            context.character_config.conf_uid,
            history_uid,
        )
        await websocket.send_text(
            json.dumps(
                {
                    "type": "new-history-created",
                    "history_uid": history_uid,
                }
            )
        )
        await websocket.send_text(
            json.dumps({"type": "history-list", "histories": histories})
        )
        metadata = get_metadata(context.character_config.conf_uid, history_uid)
        return {
            "history_uid": history_uid,
            "histories": histories,
            "title": str(metadata.get("title") or "").strip(),
        }

    async def _resume_latest_history_or_create(
        self,
        websocket: WebSocket,
        context: ServiceContext,
    ) -> dict:
        histories = self._ordered_histories(context.character_config.conf_uid)
        if histories:
            history_uid = str(histories[0].get("uid") or "").strip()
            if history_uid:
                return await self._push_history_selection(
                    websocket,
                    context,
                    history_uid,
                )

        return await self._create_history_for_context(websocket, context)

    def get_launcher_status(self, client_uid: Optional[str] = None) -> dict:
        self._prune_finished_tasks()
        resolved_client_uid, connected_clients, resolve_error = (
            self._resolve_launcher_target(client_uid)
        )

        payload = {
            "ok": True,
            "connected_client_count": len(connected_clients),
            "connected_client_uids": connected_clients,
            "target_client_uid": resolved_client_uid,
            "can_hot_switch": False,
            "scope": "unavailable",
            "reason": "",
            "default_conf_name": self.default_context_cache.character_config.conf_name,
            "default_conf_uid": self.default_context_cache.character_config.conf_uid,
            "default_active_project_id": (
                self.default_context_cache.character_config.active_project_id or ""
            ),
        }

        if resolve_error:
            payload["reason"] = resolve_error
            return payload

        if resolved_client_uid is None:
            payload["can_hot_switch"] = True
            payload["scope"] = "default"
            payload["reason"] = "No active frontend session; launcher can update the default backend context only."
            return payload

        idle, reason = self._is_client_idle_for_switch(resolved_client_uid)
        payload["can_hot_switch"] = idle
        payload["scope"] = "session" if idle else "busy"
        payload["reason"] = reason

        context = self.client_contexts.get(resolved_client_uid)
        if context:
            payload["conf_name"] = context.character_config.conf_name
            payload["conf_uid"] = context.character_config.conf_uid
            payload["active_project_id"] = (
                context.character_config.active_project_id or ""
            )
            payload["current_history_uid"] = context.history_uid or ""

        return payload

    async def launcher_select_history(
        self,
        history_uid: str,
        *,
        target_client_uid: Optional[str] = None,
        trigger_source: str = "launcher",
    ) -> dict:
        if not history_uid:
            raise ValueError("history_uid is required.")

        resolved_client_uid, connected_clients, resolve_error = (
            self._resolve_launcher_target(target_client_uid)
        )
        if resolve_error:
            raise RuntimeError(resolve_error)
        if resolved_client_uid is None:
            raise RuntimeError("No active frontend session is connected.")

        idle, reason = self._is_client_idle_for_switch(resolved_client_uid)
        if not idle:
            raise RuntimeError(reason)

        context = self.client_contexts.get(resolved_client_uid)
        websocket = self.client_connections.get(resolved_client_uid)
        if not context or not websocket:
            raise RuntimeError(
                f"Target client {resolved_client_uid} disconnected before history selection could complete."
            )

        histories = self._ordered_histories(context.character_config.conf_uid)
        known_uids = {str(item.get("uid") or "") for item in histories}
        if history_uid not in known_uids:
            raise ValueError(f"History {history_uid} does not exist for this character.")

        result = await self._push_history_selection(websocket, context, history_uid)
        return {
            "ok": True,
            "scope": "session",
            "target_client_uid": resolved_client_uid,
            "connected_client_count": len(connected_clients),
            "history_uid": history_uid,
            "title": result.get("title", ""),
            "message": f"History switched by {trigger_source}.",
        }

    async def launcher_create_history(
        self,
        *,
        target_client_uid: Optional[str] = None,
        trigger_source: str = "launcher",
    ) -> dict:
        resolved_client_uid, connected_clients, resolve_error = (
            self._resolve_launcher_target(target_client_uid)
        )
        if resolve_error:
            raise RuntimeError(resolve_error)
        if resolved_client_uid is None:
            raise RuntimeError("No active frontend session is connected.")

        idle, reason = self._is_client_idle_for_switch(resolved_client_uid)
        if not idle:
            raise RuntimeError(reason)

        context = self.client_contexts.get(resolved_client_uid)
        websocket = self.client_connections.get(resolved_client_uid)
        if not context or not websocket:
            raise RuntimeError(
                f"Target client {resolved_client_uid} disconnected before history creation could complete."
            )

        result = await self._create_history_for_context(websocket, context)
        return {
            "ok": True,
            "scope": "session",
            "target_client_uid": resolved_client_uid,
            "connected_client_count": len(connected_clients),
            "history_uid": result.get("history_uid", ""),
            "title": result.get("title", ""),
            "message": f"New history created by {trigger_source}.",
        }

    async def hot_switch_runtime_config(
        self,
        runtime_config_data: dict,
        *,
        target_client_uid: Optional[str] = None,
        trigger_source: str = "launcher",
    ) -> dict:
        if not isinstance(runtime_config_data, dict):
            raise ValueError("runtime_config must be a JSON object.")

        resolved_client_uid, connected_clients, resolve_error = (
            self._resolve_launcher_target(target_client_uid)
        )
        if resolve_error:
            raise RuntimeError(resolve_error)

        if resolved_client_uid is not None:
            idle, reason = self._is_client_idle_for_switch(resolved_client_uid)
            if not idle:
                raise RuntimeError(reason)

        validated_config = validate_config(runtime_config_data)

        await self.default_context_cache.load_from_config(
            validated_config.model_copy(deep=True)
        )

        result = {
            "ok": True,
            "scope": "default" if resolved_client_uid is None else "session",
            "target_client_uid": resolved_client_uid,
            "connected_client_count": len(connected_clients),
            "conf_name": validated_config.character_config.conf_name,
            "conf_uid": validated_config.character_config.conf_uid,
            "active_project_id": validated_config.character_config.active_project_id,
            "active_project_name": validated_config.character_config.active_project_name,
            "message": "",
        }

        if resolved_client_uid is None:
            result["message"] = "Default backend context updated. The next frontend session will use the new character/project."
            return result

        context = self.client_contexts.get(resolved_client_uid)
        websocket = self.client_connections.get(resolved_client_uid)
        if not context or not websocket:
            raise RuntimeError(
                f"Target client {resolved_client_uid} disconnected before hot switch could complete."
            )

        await context.load_from_config(validated_config.model_copy(deep=True))

        history_result = await self._resume_latest_history_or_create(websocket, context)
        selected_history_uid = str(history_result.get("history_uid") or "").strip()
        selected_history_title = str(history_result.get("title") or "").strip()

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": context.live2d_model.model_info,
                    "conf_name": context.character_config.conf_name,
                    "conf_uid": context.character_config.conf_uid,
                    "client_uid": resolved_client_uid,
                }
            )
        )
        await websocket.send_text(
            json.dumps(
                {
                    "type": "config-switched",
                    "message": (
                        f"Hot switched by {trigger_source}: "
                        f"{context.character_config.conf_name}"
                    ),
                    "active_project_id": context.character_config.active_project_id,
                    "active_project_name": context.character_config.active_project_name,
                    "history_uid": selected_history_uid,
                }
            )
        )

        result["message"] = (
            f"Hot switched active session to {context.character_config.conf_name}"
        )
        result["history_uid"] = selected_history_uid
        result["history_title"] = selected_history_title
        return result

    def _init_message_handlers(self) -> Dict[str, Callable]:
        """Initialize message type to handler mapping"""
        return {
            "add-client-to-group": self._handle_group_operation,
            "remove-client-from-group": self._handle_group_operation,
            "request-group-info": self._handle_group_info,
            "fetch-history-list": self._handle_history_list_request,
            "fetch-and-set-history": self._handle_fetch_history,
            "create-new-history": self._handle_create_history,
            "delete-history": self._handle_delete_history,
            "interrupt-signal": self._handle_interrupt,
            "mic-audio-data": self._handle_audio_data,
            "mic-audio-end": self._handle_conversation_trigger,
            "raw-audio-data": self._handle_raw_audio_data,
            "text-input": self._handle_conversation_trigger,
            "ai-speak-signal": self._handle_conversation_trigger,
            "fetch-configs": self._handle_fetch_configs,
            "switch-config": self._handle_config_switch,
            "fetch-backgrounds": self._handle_fetch_backgrounds,
            "audio-play-start": self._handle_audio_play_start,
            "request-init-config": self._handle_init_config_request,
            "heartbeat": self._handle_heartbeat,
        }

    async def handle_new_connection(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle new WebSocket connection setup

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client

        Raises:
            Exception: If initialization fails
        """
        try:
            session_service_context = await self._init_service_context(
                websocket.send_text, client_uid
            )

            await self._store_client_data(
                websocket, client_uid, session_service_context
            )

            await self._send_initial_messages(
                websocket, client_uid, session_service_context
            )

            logger.info(f"Connection established for client {client_uid}")

        except Exception as e:
            logger.error(
                f"Failed to initialize connection for client {client_uid}: {e}"
            )
            await self._cleanup_failed_connection(client_uid)
            raise

    async def _store_client_data(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
    ):
        """Store client data and initialize group status"""
        self.client_connections[client_uid] = websocket
        self.client_contexts[client_uid] = session_service_context
        self.received_data_buffers[client_uid] = np.array([])
        self.pending_history_bootstrap[client_uid] = True

        self.chat_group_manager.client_group_map[client_uid] = ""
        await self.send_group_update(websocket, client_uid)

    async def _send_initial_messages(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
    ):
        """Send initial connection messages to the client"""
        await websocket.send_text(
            json.dumps({"type": "full-text", "text": "Connection established"})
        )

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": session_service_context.live2d_model.model_info,
                    "conf_name": session_service_context.character_config.conf_name,
                    "conf_uid": session_service_context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

        # Send initial group status
        await self.send_group_update(websocket, client_uid)

        # Start microphone
        await websocket.send_text(json.dumps({"type": "control", "text": "start-mic"}))

    async def _init_service_context(
        self, send_text: Callable, client_uid: str
    ) -> ServiceContext:
        """Initialize service context for a new session by cloning the default context"""
        session_service_context = ServiceContext()
        await session_service_context.load_cache(
            config=self.default_context_cache.config.model_copy(deep=True),
            system_config=self.default_context_cache.system_config.model_copy(
                deep=True
            ),
            character_config=self.default_context_cache.character_config.model_copy(
                deep=True
            ),
            live2d_model=self.default_context_cache.live2d_model,
            asr_engine=self.default_context_cache.asr_engine,
            tts_engine=self.default_context_cache.tts_engine,
            vad_engine=self.default_context_cache.vad_engine,
            agent_engine=self.default_context_cache.agent_engine,
            translate_engine=self.default_context_cache.translate_engine,
            mcp_server_registery=self.default_context_cache.mcp_server_registery,
            tool_adapter=self.default_context_cache.tool_adapter,
            send_text=send_text,
            client_uid=client_uid,
        )
        return session_service_context

    async def handle_websocket_communication(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle ongoing WebSocket communication

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client
        """
        try:
            while True:
                try:
                    data = await websocket.receive_json()
                    message_handler.handle_message(client_uid, data)
                    await self._route_message(websocket, client_uid, data)
                except WebSocketDisconnect:
                    raise
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
                    continue

        except WebSocketDisconnect:
            logger.info(f"Client {client_uid} disconnected")
            raise
        except Exception as e:
            logger.error(f"Fatal error in WebSocket communication: {e}")
            raise

    async def _route_message(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """
        Route incoming message to appropriate handler

        Args:
            websocket: The WebSocket connection
            client_uid: Client identifier
            data: Message data
        """
        msg_type = data.get("type")
        if not msg_type:
            logger.warning("Message received without type")
            return

        handler = self._message_handlers.get(msg_type)
        if handler:
            await handler(websocket, client_uid, data)
        else:
            if msg_type != "frontend-playback-complete":
                logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_group_operation(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle group-related operations"""
        operation = data.get("type")
        target_uid = data.get(
            "invitee_uid" if operation == "add-client-to-group" else "target_uid"
        )

        await handle_group_operation(
            operation=operation,
            client_uid=client_uid,
            target_uid=target_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=self.send_group_update,
        )

    async def handle_disconnect(self, client_uid: str) -> None:
        """Handle client disconnection"""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response="",
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=self.broadcast_to_group,
            )

        await handle_client_disconnect(
            client_uid=client_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=self.send_group_update,
        )

        # Clean up other client data
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        self.pending_history_bootstrap.pop(client_uid, None)
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        # Call context close to clean up resources (e.g., MCPClient)
        context = self.client_contexts.get(client_uid)
        if context:
            await context.close()

        logger.info(f"Client {client_uid} disconnected")
        message_handler.cleanup_client(client_uid)

    async def _cleanup_failed_connection(self, client_uid: str) -> None:
        """Clean up failed connection data"""
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        self.pending_history_bootstrap.pop(client_uid, None)
        self.chat_group_manager.client_group_map.pop(client_uid, None)

        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        message_handler.cleanup_client(client_uid)

    async def broadcast_to_group(
        self, group_members: list[str], message: dict, exclude_uid: str = None
    ) -> None:
        """Broadcasts a message to group members"""
        await broadcast_to_group(
            group_members=group_members,
            message=message,
            client_connections=self.client_connections,
            exclude_uid=exclude_uid,
        )

    async def send_group_update(self, websocket: WebSocket, client_uid: str):
        """Sends group information to a client"""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            current_members = self.chat_group_manager.get_group_members(client_uid)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "group-update",
                        "members": current_members,
                        "is_owner": group.owner_uid == client_uid,
                    }
                )
            )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "group-update",
                        "members": [],
                        "is_owner": False,
                    }
                )
            )

    async def _handle_interrupt(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle conversation interruption"""
        heard_response = data.get("text", "")
        context = self.client_contexts[client_uid]
        group = self.chat_group_manager.get_client_group(client_uid)

        if group and len(group.members) > 1:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response=heard_response,
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=self.broadcast_to_group,
            )
        else:
            await handle_individual_interrupt(
                client_uid=client_uid,
                current_conversation_tasks=self.current_conversation_tasks,
                context=context,
                heard_response=heard_response,
            )

    async def _handle_history_list_request(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle request for chat history list"""
        context = self.client_contexts[client_uid]
        histories = get_history_list(context.character_config.conf_uid)
        await websocket.send_text(
            json.dumps({"type": "history-list", "histories": histories})
        )

    async def _handle_fetch_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle fetching and setting specific chat history"""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        messages = self._load_history_into_context(context, history_uid)
        await websocket.send_text(
            json.dumps({"type": "history-data", "messages": messages})
        )

    async def _handle_create_history(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle creation of new chat history"""
        context = self.client_contexts[client_uid]
        force_new = bool(data.get("force_new"))
        is_bootstrap = self.pending_history_bootstrap.pop(client_uid, False)

        if is_bootstrap and not force_new:
            await self._resume_latest_history_or_create(websocket, context)
            return

        await self._create_history_for_context(websocket, context)

    async def _handle_delete_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle deletion of chat history"""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        success = delete_history(
            context.character_config.conf_uid,
            history_uid,
        )
        await websocket.send_text(
            json.dumps(
                {
                    "type": "history-deleted",
                    "success": success,
                    "history_uid": history_uid,
                }
            )
        )
        if history_uid == context.history_uid:
            context.history_uid = None

    async def _handle_audio_data(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle incoming audio data"""
        audio_data = data.get("audio", [])
        if audio_data:
            self.received_data_buffers[client_uid] = np.append(
                self.received_data_buffers[client_uid],
                np.array(audio_data, dtype=np.float32),
            )

    async def _handle_raw_audio_data(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle incoming raw audio data for VAD processing"""
        context = self.client_contexts[client_uid]
        chunk = data.get("audio", [])
        if chunk:
            for audio_bytes in context.vad_engine.detect_speech(chunk):
                if audio_bytes == b"<|PAUSE|>":
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "interrupt"})
                    )
                elif audio_bytes == b"<|RESUME|>":
                    pass
                elif len(audio_bytes) > 1024:
                    # Detected audio activity (voice)
                    self.received_data_buffers[client_uid] = np.append(
                        self.received_data_buffers[client_uid],
                        np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32),
                    )
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "mic-audio-end"})
                    )

    async def _handle_conversation_trigger(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle triggers that start a conversation"""
        await handle_conversation_trigger(
            msg_type=data.get("type", ""),
            data=data,
            client_uid=client_uid,
            context=self.client_contexts[client_uid],
            websocket=websocket,
            client_contexts=self.client_contexts,
            client_connections=self.client_connections,
            chat_group_manager=self.chat_group_manager,
            received_data_buffers=self.received_data_buffers,
            current_conversation_tasks=self.current_conversation_tasks,
            broadcast_to_group=self.broadcast_to_group,
        )

    async def _handle_fetch_configs(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle fetching available configurations"""
        context = self.client_contexts[client_uid]
        config_files = scan_config_alts_directory(context.system_config.config_alts_dir)
        await websocket.send_text(
            json.dumps({"type": "config-files", "configs": config_files})
        )

    async def _handle_config_switch(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle switching to a different configuration"""
        config_file_name = data.get("file")
        if config_file_name:
            context = self.client_contexts[client_uid]
            await context.handle_config_switch(websocket, config_file_name)

    async def _handle_fetch_backgrounds(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle fetching available background images"""
        bg_files = scan_bg_directory()
        await websocket.send_text(
            json.dumps({"type": "background-files", "files": bg_files})
        )

    async def _handle_audio_play_start(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """
        Handle audio playback start notification
        """
        group_members = self.chat_group_manager.get_group_members(client_uid)
        if len(group_members) > 1:
            display_text = data.get("display_text")
            if display_text:
                silent_payload = prepare_audio_payload(
                    audio_path=None,
                    display_text=display_text,
                    actions=None,
                    forwarded=True,
                )
                await self.broadcast_to_group(
                    group_members, silent_payload, exclude_uid=client_uid
                )

    async def _handle_group_info(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle group info request"""
        await self.send_group_update(websocket, client_uid)

    async def _handle_init_config_request(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle request for initialization configuration"""
        context = self.client_contexts.get(client_uid)
        if not context:
            context = self.default_context_cache

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": context.live2d_model.model_info,
                    "conf_name": context.character_config.conf_name,
                    "conf_uid": context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

    async def _handle_heartbeat(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle heartbeat messages from clients"""
        try:
            await websocket.send_json({"type": "heartbeat-ack"})
        except Exception as e:
            logger.error(f"Error sending heartbeat acknowledgment: {e}")
