import fnmatch
import ipaddress
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    status: str
    reason: str


class ToolPolicy:
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy if isinstance(policy, dict) else {}
        self.tools = self.policy.get("tools") if isinstance(self.policy.get("tools"), dict) else {}
        self.filesystem = (
            self.policy.get("filesystem")
            if isinstance(self.policy.get("filesystem"), dict)
            else {}
        )
        self.web = self.policy.get("web") if isinstance(self.policy.get("web"), dict) else {}
        self.default_mode = str(self.policy.get("default_mode") or "blocked").strip().lower()

    @classmethod
    def load_default(cls) -> "ToolPolicy":
        path = _default_policy_path()
        if path and path.exists():
            try:
                return cls(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning(f"Failed to load tool policy from {path}: {exc}")
        return cls({"default_mode": "blocked", "tools": {}})

    def check(self, tool_name: str, tool_args: Any) -> ToolPolicyDecision:
        tool_name = (tool_name or "").strip()
        args = tool_args if isinstance(tool_args, dict) else {}
        tool_cfg = self.tools.get(tool_name)
        if not isinstance(tool_cfg, dict):
            return ToolPolicyDecision(
                allowed=False,
                status="blocked",
                reason=f"Tool '{tool_name or 'unknown'}' is not registered in runtime policy.",
            )

        mode = str(tool_cfg.get("mode") or self.default_mode).strip().lower()
        if mode in {"blocked", "deny", "disabled"}:
            return ToolPolicyDecision(
                allowed=False,
                status="blocked",
                reason=f"Tool '{tool_name}' is disabled by runtime policy.",
            )
        if mode in {"confirm", "needs_confirmation"}:
            return ToolPolicyDecision(
                allowed=False,
                status="blocked",
                reason=f"Tool '{tool_name}' requires confirmation, but this runtime has no confirmation flow yet.",
            )

        argument_decision = self._check_argument_rules(tool_name, tool_cfg, args)
        if not argument_decision.allowed:
            return argument_decision

        path_decision = self._check_path_args(tool_name, tool_cfg, args)
        if not path_decision.allowed:
            return path_decision

        url_decision = self._check_url_args(tool_name, tool_cfg, args)
        if not url_decision.allowed:
            return url_decision

        return ToolPolicyDecision(allowed=True, status="allowed", reason="Allowed by runtime policy.")

    def _check_argument_rules(
        self,
        tool_name: str,
        tool_cfg: dict[str, Any],
        args: dict[str, Any],
    ) -> ToolPolicyDecision:
        deny_truthy_args = tool_cfg.get("deny_truthy_args") or []
        if isinstance(deny_truthy_args, list):
            for arg_name in deny_truthy_args:
                arg_key = str(arg_name)
                if _is_truthy_arg(args.get(arg_key)):
                    return ToolPolicyDecision(
                        allowed=False,
                        status="blocked",
                        reason=f"Tool '{tool_name}' cannot use argument '{arg_key}' under the current policy.",
                    )

        deny_values = tool_cfg.get("deny_values") or {}
        if isinstance(deny_values, dict):
            for arg_name, blocked_values in deny_values.items():
                arg_key = str(arg_name)
                if arg_key not in args:
                    continue
                blocked_set = _normalized_blocked_values(blocked_values)
                if _normalized_arg_value(args.get(arg_key)) in blocked_set:
                    return ToolPolicyDecision(
                        allowed=False,
                        status="blocked",
                        reason=f"Tool '{tool_name}' cannot use value '{args.get(arg_key)}' for argument '{arg_key}' under the current policy.",
                    )

        return ToolPolicyDecision(True, "allowed", "Allowed by runtime policy.")

    def _check_path_args(
        self,
        tool_name: str,
        tool_cfg: dict[str, Any],
        args: dict[str, Any],
    ) -> ToolPolicyDecision:
        path_args = tool_cfg.get("path_args") or []
        if not isinstance(path_args, list):
            return ToolPolicyDecision(True, "allowed", "Allowed by runtime policy.")

        if not bool(tool_cfg.get("allow_hidden", True)) and bool(args.get("include_hidden")):
            return ToolPolicyDecision(
                allowed=False,
                status="blocked",
                reason=f"Tool '{tool_name}' cannot include hidden files under the current policy.",
            )

        for arg_name in path_args:
            raw_path = str(args.get(str(arg_name)) or "").strip()
            if not raw_path:
                continue
            denied_reason = self._deny_reason_for_path(raw_path)
            if denied_reason:
                return ToolPolicyDecision(
                    allowed=False,
                    status="blocked",
                    reason=denied_reason,
                )
        return ToolPolicyDecision(True, "allowed", "Allowed by runtime policy.")

    def _deny_reason_for_path(self, raw_path: str) -> str:
        normalized = raw_path.replace("\\", "/").lower()
        basename = normalized.rsplit("/", 1)[-1]
        patterns = self.filesystem.get("deny_path_patterns") or []
        parts = self.filesystem.get("deny_path_parts") or []

        if isinstance(parts, list):
            segments = [segment for segment in normalized.split("/") if segment]
            for part in parts:
                part_text = str(part).strip().lower()
                if part_text and part_text in segments:
                    return f"Path is blocked by runtime policy because it contains '{part_text}'."

        if isinstance(patterns, list):
            for pattern in patterns:
                pattern_text = str(pattern).strip().replace("\\", "/").lower()
                if not pattern_text:
                    continue
                if fnmatch.fnmatch(normalized, pattern_text) or fnmatch.fnmatch(
                    basename, pattern_text
                ):
                    return f"Path is blocked by runtime policy: {raw_path}"
        return ""

    def _check_url_args(
        self,
        tool_name: str,
        tool_cfg: dict[str, Any],
        args: dict[str, Any],
    ) -> ToolPolicyDecision:
        url_args = tool_cfg.get("url_args") or []
        if not isinstance(url_args, list):
            return ToolPolicyDecision(True, "allowed", "Allowed by runtime policy.")

        for arg_name in url_args:
            raw_url = str(args.get(str(arg_name)) or "").strip()
            if not raw_url:
                continue
            denied_reason = self._deny_reason_for_url(raw_url)
            if denied_reason:
                return ToolPolicyDecision(False, "blocked", denied_reason)
        return ToolPolicyDecision(True, "allowed", "Allowed by runtime policy.")

    def _deny_reason_for_url(self, raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return "URL is blocked by runtime policy because only HTTP/HTTPS public pages are allowed."

        host = (parsed.hostname or "").strip().lower()
        if not host:
            return "URL is blocked by runtime policy because it has no hostname."

        blocked_hosts = self.web.get("blocked_hostnames") or []
        if isinstance(blocked_hosts, list) and host in {str(item).lower() for item in blocked_hosts}:
            return f"URL host '{host}' is blocked by runtime policy."

        if bool(self.web.get("block_private_networks", True)):
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return f"URL host '{host}' is blocked because private/internal addresses are not allowed."
            except ValueError:
                if host.endswith(".local") or host.endswith(".internal"):
                    return f"URL host '{host}' is blocked because private/internal hostnames are not allowed."

        return ""


def _default_policy_path() -> Path | None:
    env_path = os.getenv("KURO_TOOL_POLICY_PATH", "").strip()
    if env_path:
        return Path(env_path)

    candidates = [
        Path.cwd() / "tool_policy.json",
        Path(__file__).resolve().parents[3] / "tool_policy.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def _is_truthy_arg(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _normalized_arg_value(value: Any) -> str:
    return str(value).strip().lower()


def _normalized_blocked_values(values: Any) -> set[str]:
    if isinstance(values, list):
        return {_normalized_arg_value(item) for item in values}
    return {_normalized_arg_value(values)}
