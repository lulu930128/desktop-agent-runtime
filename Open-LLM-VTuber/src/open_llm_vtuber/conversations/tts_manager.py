import asyncio
import json
import re
import uuid
import time
from datetime import datetime
from typing import List, Optional, Dict
from loguru import logger

from ..agent.output_types import DisplayText, Actions
from ..live2d_model import Live2dModel
from ..tts.tts_interface import TTSInterface
from ..utils.stream_audio import prepare_audio_payload
from .types import WebSocketSend


class TTSTaskManager:
    """Serializes TTS inference and delivers payloads in their original order."""

    def __init__(self) -> None:
        self.task_list: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        # Queue to store ordered payloads
        self._payload_queue: asyncio.Queue[Dict] = asyncio.Queue()
        # Task to handle sending payloads in order
        self._sender_task: Optional[asyncio.Task] = None
        # Counter for maintaining order
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        self._failed_speech_groups: set[object] = set()
        self.missing_units: set[int] = set()
        self.failed_segments: set[int] = set()
        self.audio_seconds = 0.0
        self.voice_task_count = 0
        self.audio_output_count = 0
        self.speech_fallback_count = 0
        self.speech_metrics = {"started_at": time.monotonic(), "bridge_requests": 0}
        self._deferred_speech_display_parts: List[str] = []
        self._deferred_speech_tts_parts: List[str] = []
        self._deferred_speech_display: Optional[DisplayText] = None
        self._deferred_speech_actions: Optional[Actions] = None
        self._deferred_speech_tags: List[str] = []

    def has_voice_output(self) -> bool:
        return self.voice_task_count > 0

    def can_queue_speech_fallback(self) -> bool:
        return not self.has_voice_output() and self.speech_fallback_count == 0

    def mark_speech_fallback_queued(self) -> None:
        self.speech_fallback_count += 1

    def add_deferred_speech(
        self,
        *,
        display_text: str,
        tts_text: str,
        display: Optional[DisplayText],
        actions: Optional[Actions],
        emotion_tags: Optional[List[str]] = None,
    ) -> None:
        if display_text:
            self._deferred_speech_display_parts.append(str(display_text))
        if tts_text:
            self._deferred_speech_tts_parts.append(str(tts_text))
        if display is not None:
            self._deferred_speech_display = display
        if actions is not None:
            self._deferred_speech_actions = actions
        if emotion_tags:
            self._deferred_speech_tags.extend(str(tag) for tag in emotion_tags if tag)

    def pop_deferred_speech(self) -> Optional[Dict]:
        if (
            not self._deferred_speech_display_parts
            and not self._deferred_speech_tts_parts
        ):
            return None

        payload = {
            "display_text": "".join(self._deferred_speech_display_parts),
            "tts_text": "".join(self._deferred_speech_tts_parts),
            "display": self._deferred_speech_display,
            "actions": self._deferred_speech_actions,
            "emotion_tags": list(self._deferred_speech_tags),
        }
        self._deferred_speech_display_parts.clear()
        self._deferred_speech_tts_parts.clear()
        self._deferred_speech_display = None
        self._deferred_speech_actions = None
        self._deferred_speech_tags.clear()
        return payload

    async def speak(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
        *, display_append: bool = False, speech_group: Optional[object] = None, segment_id: Optional[int] = None,
    ) -> None:
        """
        Queue a TTS task while maintaining order of delivery.

        Args:
            tts_text: Text to synthesize
            display_text: Text to display in UI
            actions: Live2D model actions
            live2d_model: Live2D model instance
            tts_engine: TTS engine instance
            websocket_send: WebSocket send function
        """
        # Treat "numbers-only" / list markers as empty to avoid speaking "1." "2." etc.
        if segment_id is None and len(re.sub(r"[\s\d\-–—•·.,!?，。！？'\"』」）】]+", "", tts_text)) == 0:
            logger.debug("Empty TTS text, sending silent display payload")
            # Get current sequence number for silent payload
            current_sequence = self._sequence_counter
            self._sequence_counter += 1

            # Start sender task if not running
            if not self._sender_task or self._sender_task.done():
                self._sender_task = asyncio.create_task(
                    self._process_payload_queue(websocket_send)
                )

            await self._send_silent_payload(display_text, actions, current_sequence, display_append=display_append)
            return

        logger.debug("Queuing TTS segment={} characters={}", segment_id, len(tts_text))
        self.voice_task_count += 1

        # Get current sequence number
        current_sequence = self._sequence_counter
        self._sequence_counter += 1

        # Start sender task if not running
        if not self._sender_task or self._sender_task.done():
            self._sender_task = asyncio.create_task(
                self._process_payload_queue(websocket_send)
            )

        # Create and queue the TTS task
        task = asyncio.create_task(
            self._process_tts(
                tts_text=tts_text,
                display_text=display_text,
                actions=actions,
                live2d_model=live2d_model,
                tts_engine=tts_engine,
                sequence_number=current_sequence,
                speech_group=speech_group, segment_id=segment_id,
            )
        )
        self.task_list.append(task)

    async def _process_payload_queue(self, websocket_send: WebSocketSend) -> None:
        """
        Process and send payloads in correct order.
        Runs continuously until all payloads are processed.
        """
        buffered_payloads: Dict[int, Dict] = {}

        while True:
            try:
                # Get payload from queue
                payload, sequence_number = await self._payload_queue.get()
                buffered_payloads[sequence_number] = payload

                # Send payloads in order
                while self._next_sequence_to_send in buffered_payloads:
                    next_payload = buffered_payloads.pop(self._next_sequence_to_send)
                    try:
                        await websocket_send(json.dumps(next_payload))
                        if next_payload.get("audio"):
                            logger.info("speech_timing event=websocket_audio_sent seq={} at={}", self._next_sequence_to_send, time.monotonic())
                    except Exception as e:
                        if next_payload.get("segment_id") is not None:
                            self.failed_segments.add(next_payload["segment_id"])
                        # Never let a transient websocket error kill the sender loop.
                        logger.warning(
                            f"WebSocket send failed (seq={self._next_sequence_to_send}): {e}"
                        )
                    finally:
                        # Advance sequence to avoid deadlock on a single failed send.
                        self._next_sequence_to_send += 1

                self._payload_queue.task_done()

            except asyncio.CancelledError:
                break

    async def _send_silent_payload(
        self,
        display_text: DisplayText,
        actions: Optional[Actions],
        sequence_number: int,
        *, display_append: bool = False,
    ) -> None:
        """Queue a silent audio payload"""
        audio_payload = prepare_audio_payload(
            audio_path=None,
            display_text=display_text,
            actions=actions,
        )
        if display_append:
            audio_payload["display_contract"] = "kuro.speech-lanes.v1"
            audio_payload["display_append"] = True
        await self._payload_queue.put((audio_payload, sequence_number))

    async def _process_tts(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        sequence_number: int,
        speech_group: Optional[object] = None, segment_id: Optional[int] = None,
    ) -> None:
        """Process TTS generation and queue the result for ordered delivery"""
        audio_file_path = None
        queued = time.monotonic()
        skipped = False
        groups = speech_group if isinstance(speech_group, frozenset) else ({speech_group} if speech_group is not None else set())
        try:
            async with self._lock:
                skipped = bool(groups & self._failed_speech_groups)
                if not skipped:
                    started = time.monotonic()
                    logger.info("speech_timing event=tts_request seq={} at={} queue_s={}",
                                sequence_number, started, started - queued)
                    try:
                        audio_file_path = await self._generate_audio(tts_engine, tts_text)
                    except Exception:
                        if speech_group is not None:
                            self._failed_speech_groups.update(groups)
                        raise
                    finally:
                        logger.info("speech_timing event=tts_complete seq={} at={} duration_s={} available={}",
                                    sequence_number, time.monotonic(), time.monotonic() - started, bool(audio_file_path))
                    if not audio_file_path and speech_group is not None:
                        self._failed_speech_groups.update(groups)
            payload = prepare_audio_payload(
                audio_path=audio_file_path,
                display_text=display_text,
                actions=actions,
            )
            # Queue the payload with its sequence number
            payload['speech_status'] = 'skipped_after_failure' if skipped else ('available' if audio_file_path else 'unavailable')
            if segment_id is not None:
                payload["segment_id"] = segment_id
                if not audio_file_path:
                    self.failed_segments.add(segment_id)
            if audio_file_path:
                self.audio_seconds += payload.get("audio_seconds", 0)
                self.audio_output_count += 1
            await self._payload_queue.put((payload, sequence_number))

        except Exception as e:
            if speech_group is not None:
                self._failed_speech_groups.update(groups)
            logger.error(f"Error preparing audio payload: {e}")
            # Queue silent payload for error case
            payload = prepare_audio_payload(
                audio_path=None,
                display_text=display_text,
                actions=actions,
            )
            payload['speech_status'] = 'unavailable'
            if segment_id is not None:
                payload['segment_id'] = segment_id
                self.failed_segments.add(segment_id)
            await self._payload_queue.put((payload, sequence_number))

        finally:
            if audio_file_path:
                tts_engine.remove_file(audio_file_path)
                logger.debug("Audio cache file cleaned.")

    async def _generate_audio(self, tts_engine: TTSInterface, text: str) -> str:
        """Generate audio file from text"""
        logger.debug("Generating audio; characters={}", len(text))
        generation = asyncio.create_task(tts_engine.async_generate_audio(
            text=text,
            file_name_no_ext=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
        ))
        try:
            return await asyncio.shield(generation)
        except asyncio.CancelledError:
            if getattr(tts_engine, "cancellation_safe", False) is True:
                generation.cancel()
                raise
            # A synchronous HTTP/GPU operation running in to_thread cannot be
            # killed. Let it finish, discard its result and remove its cache;
            # never enqueue stale speech into this or the next turn.
            def discard_result(task):
                if task.cancelled():
                    return
                try:
                    path = task.result()
                    if path:
                        tts_engine.remove_file(path)
                except Exception:
                    logger.warning("Cancelled TTS generation cleanup failed")
            generation.add_done_callback(discard_result)
            raise

    def clear(self) -> None:
        """Clear all pending tasks and reset state"""
        for task in self.task_list:
            if not task.done():
                task.cancel()
        self.task_list.clear()
        if self._sender_task:
            self._sender_task.cancel()
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        self._failed_speech_groups.clear()
        # Create a new queue to clear any pending items
        self._payload_queue = asyncio.Queue()
        self._deferred_speech_display_parts.clear()
        self._deferred_speech_tts_parts.clear()
        self._deferred_speech_display = None
        self._deferred_speech_actions = None
        self._deferred_speech_tags.clear()
