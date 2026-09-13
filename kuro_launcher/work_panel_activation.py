"""Work Panel activation diagnostics; lifecycle ownership stays in the controller."""

import json
import threading
from typing import Callable


MAX_WORK_PANEL_RECOVERY_ATTEMPTS = 1
_LOG_LOCK = threading.Lock()


class WorkPanelActivationError(RuntimeError):
    def __init__(self, result: dict, message: str):
        self.result = dict(result)
        super().__init__(f"{result['failure_code']} / request_id={result['request_id']}\n{message}")


def record_activation(event: str, result: dict, log: Callable[[str], None]) -> None:
    # Only caller-built lifecycle fields are passed here, never tool/chat payloads.
    line = "[work-panel] " + json.dumps({"event": event, **result}, ensure_ascii=False)
    with _LOG_LOCK:
        print(line, flush=True)
    log(line)


def window_failure_code(state: object) -> str:
    if not isinstance(state, dict) or state.get("contractVersion") != 1:
        return "WP_WINDOW_CONTRACT_UNSUPPORTED"
    if state.get("exists") is not True:
        return "WP_WINDOW_NOT_CREATED"
    if state.get("rendererReady") is not True or state.get("responsive") is not True or state.get("loading") is not False:
        return "WP_RENDERER_NOT_READY"
    if state.get("visible") is not True or state.get("minimized") is not False:
        return "WP_WINDOW_NOT_VISIBLE"
    if state.get("displayMatch") is not True:
        return "WP_WINDOW_OFFSCREEN"
    # Focus is diagnostic: switching apps must not restart a healthy shell.
    return ""
