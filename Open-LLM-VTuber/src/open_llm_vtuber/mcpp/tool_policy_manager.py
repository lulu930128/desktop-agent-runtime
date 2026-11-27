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
from .server_registry import OWNER_SERVICES, HTTP_READ_TOOLS, http_arguments_allowed
from .tool_schema import resolved_schema


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
        self.owner_services = {s for s in OWNER_SERVICES if isinstance(self.policy.get("owner_services"), list) and s in self.policy["owner_services"]}
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
        server_id, _, wire_name = canonical.partition("::")
        if server_id in HTTP_READ_TOOLS:
            if wire_name not in HTTP_READ_TOOLS[server_id]:
                return ToolPolicyDecision(False, "blocked", "HTTP tool is outside the public read-only subset.", "http_tool_denied")
            if not http_arguments_allowed(server_id, args):
                return ToolPolicyDecision(False, "blocked", "HTTP connection options and restricted scopes are not enabled.", "http_arguments_denied")
        # Historical owner pins are not compatibility routes to OMI Search.
        if canonical.startswith("omi-market::"):
            return ToolPolicyDecision(False, "blocked", "Retired market server.", "retired_server")
        raw = legacy_name(canonical)
        tool_cfg = self.tools.get(canonical, self.tools.get(raw))
        # A legacy deny remains a deny during an incremental configuration migration.
        if canonical in self.tools and raw != canonical and raw in self.tools:
            legacy_cfg = self.tools[raw]
            if (not isinstance(legacy_cfg, dict) or legacy_cfg.get("enabled", True) is not True
                    or not mode_decision(legacy_cfg.get("mode", self.default_mode)).allowed):
                tool_cfg = legacy_cfg
        if server_id in self.owner_services and canonical not in self.tools and raw not in self.tools:
            tool_cfg = {"mode": "owner"}
        if not isinstance(tool_cfg, dict):
            return ToolPolicyDecision(
                allowed=False,
                status="blocked",
                reason="Tool is not registered in runtime policy.",
                reason_code="unregistered_tool",
            )

        if not _valid_tool_config(tool_cfg):
            return ToolPolicyDecision(False, "blocked", "Invalid tool policy rules.", "invalid_policy_config")
        if tool_cfg.get("enabled", True) is False:
            return ToolPolicyDecision(False, "blocked", "Disabled by user setting.", "tool_disabled")
        if tool_cfg.get("mode") == "owner" and server_id in self.owner_services:
            decision = ToolPolicyDecision(True, "allowed", "Authorized service; invocation subject to owner policy.", "owner_authorized")
        else:
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

        return decision

    def llm_schema(self, tool_name: str, schema: dict) -> dict:
        """Narrow OMI's provider descriptor without changing its wire contract."""
        value = deepcopy(schema)
        identity = legacy_canonical(tool_name)
        if identity.partition("::")[0] in self.owner_services or identity != "omi-search::omi_ask" or not self.check(identity, {}).allowed:
            return value
        cfg = self.tools.get(identity, self.tools.get(legacy_name(identity), {}))
        properties = value.get("properties", {})
        for name, allowed in cfg.get("allow_values", {}).items():
            node = properties.get(name)
            if not isinstance(node, dict):
                continue
            permitted = [x for x in allowed if "enum" not in node or any(
                type(x) is type(y) and x == y for y in node["enum"])]
            node["enum"] = deepcopy(permitted)
            if len(permitted) == 1:
                node["default"] = deepcopy(permitted[0])
                node["description"] = "Kuro read-only policy fixes this argument to the declared value."
        for path, limit in cfg.get("max_numeric_args", {}).items():
            node = value
            for part in path.split("."):
                node = node.get("properties", {}).get(part, {})
            if node.get("type") not in {"integer", "number"}:
                continue
            node["maximum"] = min(node.get("maximum", limit), limit)
            if "default" in node:
                node["default"] = min(node["default"], node["maximum"])
            if node.get("minimum") == node["maximum"]:
                node["enum"] = [node["maximum"]]
            node["description"] = "Kuro policy upper bound; omitted arguments use this default."
        if "realtime_policy" in properties:
            properties["realtime_policy"]["default"] = "cache_only"
        if "refresh_policy" in properties:
            properties["refresh_policy"]["default"] = {"mode": "off", "before_answer": False}
            for name, default in (("mode", "off"), ("before_answer", False)):
                if name in properties["refresh_policy"].get("properties", {}):
                    properties["refresh_policy"]["properties"][name]["default"] = default
        if "target" in properties:
            properties["target"]["description"] = (
                "For a market overview use {type: market, market: US} (or the requested market). "
                "market belongs inside target, never at the argument root.")
        return value

    def prepare_arguments(self, tool_name: str, args: Any, schema: dict) -> Any:
        """Supply declared OMI defaults and repair only the known market placement."""
        identity = legacy_canonical(tool_name)
        if identity.partition("::")[0] in self.owner_services or identity != "omi-search::omi_ask" or not isinstance(args, dict) or not self.check(identity, {}).allowed:
            return args
        effective = self.llm_schema(identity, resolved_schema(schema))
        properties = effective.get("properties", {})
        value = deepcopy(args)
        # Do not infer market intent, overwrite a target, or drop unknown fields.
        target = value.get("target", {})
        market = value.get("market")
        if (isinstance(market, str) and market.strip() and "market" not in properties
                and "market" in properties.get("target", {}).get("properties", {})
                and isinstance(target, dict) and target.get("type", "market") == "market"
                and target.get("market", market) == market):
            value["target"] = {"type": "market", **target, "market": value.pop("market")}
        for name in ("contract_version", "mode", "refresh_if_missing", "realtime_policy", "refresh_policy"):
            if name not in value and "default" in properties.get(name, {}):
                value[name] = deepcopy(properties[name]["default"])
        budget_schema = properties.get("tool_budget", {}).get("properties", {})
        budget = value.get("tool_budget", {})
        if isinstance(budget, dict) and budget_schema:
            value["tool_budget"] = {**{k: deepcopy(v["default"]) for k, v in budget_schema.items()
                                       if "default" in v}, **budget}
        return value

    def argument_hint(self, tool_name: str) -> str:
        if legacy_canonical(tool_name).partition("::")[0] in self.owner_services or legacy_canonical(tool_name) != "omi-search::omi_ask":
            return ""
        cfg = self.tools.get("omi-search::omi_ask", self.tools.get(legacy_name(tool_name), {}))
        return (" Primary entry point for natural-language market questions, including yesterday's US market: "
                "call omi_ask first, before specialist read tools. Preserve the user's relative-date question "
                "for OMI to resolve; do not guess a trade_date. "
                "Use target.type=market and target.market for a market overview; never root market. "
                "Correct the rejected arguments before retrying. Kuro allowed values: "
                + json.dumps(cfg.get("allow_values", {}), sort_keys=True)
                + "; numeric upper bounds: " + json.dumps(cfg.get("max_numeric_args", {}), sort_keys=True) + ".")

    def _check_argument_rules(
        self,
        tool_name: str,
        tool_cfg: dict[str, Any],
        args: dict[str, Any],
    ) -> ToolPolicyDecision:
        for key in tool_cfg.get("deny_present_args", []):
            if key in args:
                return ToolPolicyDecision(False, "blocked", "Retired or privileged argument is not accepted.")
        for key, values in tool_cfg.get("allow_values", {}).items():
            if key in args and not any(type(args[key]) is type(value) and args[key] == value for value in values):
                return ToolPolicyDecision(False, "blocked", "Argument is outside the permitted read-only values.")
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
            # Project Workspace's batch schema is files: [{path, ...}].
            # Check each path with the same layered policy as single reads.
            if arg_name == "files[].path":
                files = args.get("files", [])
                if not isinstance(files, list) or any(
                    not isinstance(row, dict) or not isinstance(row.get("path"), str)
                    for row in files
                ):
                    return ToolPolicyDecision(False, "blocked", "Invalid batch paths.")
                paths = [row["path"] for row in files]
            else:
                paths = [str(args.get(str(arg_name)) or "")]
            for raw_path in paths:
                denied_reason = self._deny_reason_for_path(raw_path.strip())
                if denied_reason:
                    return ToolPolicyDecision(False, "blocked", denied_reason)
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
    known = {"mode", "enabled", "category", "path_args", "url_args", "deny_truthy_args", "deny_values", "max_numeric_args", "allow_hidden", "block_private_urls", "deny_present_args", "allow_values"}
    if set(cfg) - known:
        return False
    for key in ("path_args", "url_args", "deny_truthy_args", "deny_present_args"):
        if key in cfg and not _string_list(cfg[key]):
            return False
    for key in ("allow_hidden", "block_private_urls", "enabled"):
        if key in cfg and type(cfg[key]) is not bool:
            return False
    for key in ("deny_values", "allow_values"):
        if key in cfg:
            values = cfg[key]
            if not isinstance(values, dict) or not all(isinstance(k, str) and k and isinstance(v, list) and all(type(x) in (str, bool, int, float) for x in v) for k, v in values.items()):
                return False
    if "max_numeric_args" in cfg:
        values = cfg["max_numeric_args"]
        if not isinstance(values, dict) or not all(isinstance(k, str) and all(k.split('.')) and _numeric_arg_value(v) is not None for k, v in values.items()):
            return False
    return True
