import fnmatch
import ipaddress
import json
import os
import math
import hashlib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from .tool_identity import legacy_canonical, legacy_name


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    status: str
    reason: str
    reason_code: str = "argument_policy"


def mode_decision(mode: Any) -> ToolPolicyDecision:
    if not isinstance(mode, str):
        return ToolPolicyDecision(False, "blocked", "Invalid policy mode.", "invalid_policy_config")
    mode = mode.strip().lower()
    if mode == "read_only":
        return ToolPolicyDecision(True, "allowed", "Configured for bounded read-only use; runtime adoption unverified.", "read_only")
    code = ("policy_disabled" if mode in {"blocked", "deny", "disabled"} else
            "confirmation_required" if mode in {"confirm", "needs_confirmation"} else
            "unsupported_policy_mode" if mode == "scoped_auto" else "unknown_policy_mode")
    return ToolPolicyDecision(False, "blocked", {
        "policy_disabled": "Disabled by policy.",
        "confirmation_required": "Confirmation required; no execution queue is available.",
        "unsupported_policy_mode": "Policy mode is not implemented.",
        "unknown_policy_mode": "Unknown policy mode.",
    }[code], code)


class ToolPolicy:
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = deepcopy(policy) if isinstance(policy, dict) else {}
        self.tools = self.policy.get("tools") if isinstance(self.policy.get("tools"), dict) else {}
        self.filesystem = (
            self.policy.get("filesystem")
            if isinstance(self.policy.get("filesystem"), dict)
            else {}
        )
        self.web = self.policy.get("web") if isinstance(self.policy.get("web"), dict) else {}
        self.default_mode = self.policy.get("default_mode", "blocked")
        self.valid = isinstance(self.policy.get("tools", {}), dict)
        for section, list_keys, bool_keys in (
            ("filesystem", ("deny_path_patterns", "deny_path_parts"), ()),
            ("web", ("blocked_hostnames",), ("block_private_networks",)),
        ):
            value = self.policy.get(section, {})
            self.valid = self.valid and isinstance(value, dict)
            if isinstance(value, dict):
                self.valid = self.valid and all(_string_list(value[k]) for k in list_keys if k in value)
                self.valid = self.valid and all(type(value[k]) is bool for k in bool_keys if k in value)
        try:
            serialized = json.dumps(self.policy, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            self.valid = False
            serialized = "invalid_policy_config"
        self.digest = hashlib.sha256(serialized.encode()).hexdigest()

    @classmethod
    def load_default(cls) -> "ToolPolicy":
        path = _default_policy_path()
        if path and path.exists():
            try:
                return cls(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("Failed to load tool policy; using fail-closed defaults.")
        return cls({"default_mode": "blocked", "tools": {}})

    def check(self, tool_name: str, tool_args: Any) -> ToolPolicyDecision:
        tool_name = tool_name.strip() if isinstance(tool_name, str) else ""
        args = tool_args
        if not self.valid or not isinstance(args, dict):
            return ToolPolicyDecision(False, "blocked", "Invalid policy configuration or arguments.", "invalid_policy_config")
        canonical = legacy_canonical(tool_name)
        raw = legacy_name(canonical)
        tool_cfg = self.tools.get(canonical, self.tools.get(raw))
        # A legacy deny remains a deny during an incremental configuration migration.
        if canonical in self.tools and raw != canonical and raw in self.tools:
            legacy_cfg = self.tools[raw]
            if not isinstance(legacy_cfg, dict) or not mode_decision(legacy_cfg.get("mode", self.default_mode)).allowed:
                tool_cfg = legacy_cfg
        if not isinstance(tool_cfg, dict):
            return ToolPolicyDecision(
                allowed=False,
                status="blocked",
                reason="Tool is not registered in runtime policy.",
                reason_code="unregistered_tool",
            )

        if not _valid_tool_config(tool_cfg):
            return ToolPolicyDecision(False, "blocked", "Invalid tool policy rules.", "invalid_policy_config")
        decision = mode_decision(tool_cfg.get("mode", self.default_mode))
        if not decision.allowed:
            return decision

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
                        reason=f"Tool argument '{arg_key}' is blocked by policy.",
                    )

        max_numeric_args = tool_cfg.get("max_numeric_args") or {}
        if isinstance(max_numeric_args, dict):
            for arg_path, max_value in max_numeric_args.items():
                arg_key = str(arg_path)
                value = _nested_arg_value(args, arg_key)
                if value is None:
                    continue
                numeric_value = _numeric_arg_value(value)
                numeric_limit = _numeric_arg_value(max_value)
                if numeric_value is None or numeric_limit is None:
                    return ToolPolicyDecision(
                        allowed=False,
                        status="blocked",
                        reason=f"Tool '{tool_name}' cannot use non-numeric value for argument '{arg_key}' under the current policy.",
                    )
                if numeric_value > numeric_limit:
                    return ToolPolicyDecision(
                        allowed=False,
                        status="blocked",
                        reason=f"Tool '{tool_name}' cannot use argument '{arg_key}' above {numeric_limit:g} under the current policy.",
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
                    return "Path is blocked by runtime policy."
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
        try:
            parsed = urlparse(raw_url)
            host = (parsed.hostname or "").strip().lower()
            parsed.port  # Validate malformed ports without reflecting the URL.
        except ValueError:
            return "URL is malformed."
        if parsed.scheme.lower() not in {"http", "https"}:
            return "URL is blocked by runtime policy because only HTTP/HTTPS public pages are allowed."

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


def _nested_arg_value(args: dict[str, Any], arg_path: str) -> Any:
    current: Any = args
    for part in arg_path.split("."):
        if not part or not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _numeric_arg_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    except (TypeError, ValueError):
        return None


def _normalized_arg_value(value: Any) -> str:
    return str(value).strip().lower()


def _normalized_blocked_values(values: Any) -> set[str]:
    if isinstance(values, list):
        return {_normalized_arg_value(item) for item in values}
    return {_normalized_arg_value(values)}


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) and bool(x.strip()) for x in value)


def _valid_tool_config(cfg: dict[str, Any]) -> bool:
    known = {"mode", "category", "path_args", "url_args", "deny_truthy_args", "deny_values", "max_numeric_args", "allow_hidden", "block_private_urls"}
    if set(cfg) - known:
        return False
    for key in ("path_args", "url_args", "deny_truthy_args"):
        if key in cfg and not _string_list(cfg[key]):
            return False
    for key in ("allow_hidden", "block_private_urls"):
        if key in cfg and type(cfg[key]) is not bool:
            return False
    if "deny_values" in cfg:
        values = cfg["deny_values"]
        if not isinstance(values, dict) or not all(isinstance(k, str) and k and isinstance(v, list) and all(type(x) in (str, bool, int, float) for x in v) for k, v in values.items()):
            return False
    if "max_numeric_args" in cfg:
        values = cfg["max_numeric_args"]
        if not isinstance(values, dict) or not all(isinstance(k, str) and all(k.split('.')) and _numeric_arg_value(v) is not None for k, v in values.items()):
            return False
    return True
