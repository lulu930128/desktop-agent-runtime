"""Bounded local JSON Schema validation and explicit provider projections."""
from copy import deepcopy
import hashlib
import json
import re
from itertools import chain, islice

from jsonschema import Draft202012Validator, Draft7Validator

MAX_SCHEMA_BYTES = 256 * 1024
MAX_SCHEMA_DEPTH = 32
PROFILES = {"openai_non_strict", "openai_strict", "claude", "prompt"}
MAX_ARGUMENT_DIAGNOSTICS = 5
MAX_DIAGNOSTIC_PATH = 256
_DIAGNOSTIC_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z", re.ASCII)
_SENSITIVE_ARGUMENT_KEY = re.compile(r"credential|secret|token|password|passwd|passphrase|pwd|auth|cookie|key|bearer|signature|session|private", re.I)


class SchemaError(ValueError):
    def __init__(self, code: str, *, diagnostics=()):
        self.code = code
        self.diagnostics = tuple(diagnostics)
        super().__init__(code)


def serialized(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def schema_digest(value) -> str:
    return hashlib.sha256(serialized(value)).hexdigest()


def schema_validator(schema):
    dialect = schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
    if not isinstance(dialect, str):
        raise SchemaError("schema_dialect_unsupported")
    dialect = dialect.removesuffix("#").replace("http://", "https://", 1)
    if dialect == "https://json-schema.org/draft/2020-12/schema":
        return Draft202012Validator
    if dialect == "https://json-schema.org/draft-07/schema":
        return Draft7Validator
    raise SchemaError("schema_dialect_unsupported")


def resolved_schema(schema: dict, *, require_object=True) -> dict:
    try:
        if not isinstance(schema, dict) or (require_object and schema.get("type") != "object") or len(serialized(schema)) > MAX_SCHEMA_BYTES:
            raise SchemaError("schema_invalid")
        validator_class = schema_validator(schema)
        validator_class.check_schema(schema)

        def walk(node, depth=0, refs=()):
            if depth > MAX_SCHEMA_DEPTH:
                raise SchemaError("schema_depth_exceeded")
            if isinstance(node, list):
                return [walk(v, depth+1, refs) for v in node]
            if not isinstance(node, dict):
                return node
            if depth and "$id" in node:
                raise SchemaError("schema_reference_unsupported")
            if "$dynamicRef" in node or "$recursiveRef" in node:
                raise SchemaError("provider_schema_unsupported")
            if "$ref" in node:
                ref = node["$ref"]
                if not isinstance(ref, str) or not ref.startswith("#/") or ref in refs:
                    raise SchemaError("schema_reference_unsupported")
                target = schema
                for part in ref[2:].split('/'):
                    token = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(target, list):
                        if not re.fullmatch(r"0|[1-9][0-9]*", token):
                            raise SchemaError("schema_reference_unsupported")
                        target = target[int(token)]
                    else:
                        target = target[token]
                value = walk(target, depth+1, (*refs, ref))
                if validator_class is Draft7Validator:
                    # Draft 7 ignores assertion siblings of $ref.
                    return value
                siblings = {k: v for k, v in node.items() if k != "$ref"}
                return {"allOf": [value, walk(siblings, depth+1, refs)]} if siblings else value
            result = {}
            for key, value in node.items():
                if key in {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}:
                    result[key] = {name: walk(child, depth+1, refs) for name, child in value.items()}
                elif key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                    result[key] = [walk(child, depth+1, refs) for child in value]
                elif key in {"items", "contains", "additionalProperties", "unevaluatedProperties", "unevaluatedItems", "propertyNames", "not", "if", "then", "else", "contentSchema"}:
                    result[key] = walk(value, depth+1, refs)
                else:
                    # enum/default/examples are data, even when they contain $ref.
                    result[key] = deepcopy(value)
            if len(serialized(result)) > MAX_SCHEMA_BYTES:
                raise SchemaError("schema_too_large")
            return result

        return walk(schema)
    except SchemaError:
        raise
    except Exception:
        raise SchemaError("schema_invalid") from None


def provider_schema(schema: dict, profile="openai_non_strict") -> dict:
    if profile not in PROFILES:
        raise SchemaError("provider_schema_unsupported")
    value = resolved_schema(schema)
    if profile == "openai_strict":
        # Do not change optionality or close open objects to make strict mode fit.
        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object" and (
                    node.get("additionalProperties") is not False
                    or set(node.get("required", [])) != set(node.get("properties", {}))
                ):
                    raise SchemaError("provider_schema_unsupported")
                if any(k in node for k in ("allOf", "not", "if", "then", "else", "patternProperties")):
                    raise SchemaError("provider_schema_unsupported")
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        check(value)
    return deepcopy(value)


def _json_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "non_json"


def _argument_diagnostics(errors, schema):
    # Paths use schema fields, or bounded non-sensitive identifiers for forbidden
    # extra fields. Never copy ValidationError.message/instance or enum/const values.
    fields = set()

    def collect(node):
        if isinstance(node, dict):
            for key in ("properties", "required"):
                fields.update(node.get(key, ()))
            for key, child in node.items():
                if key not in {"enum", "const", "default", "examples"}:
                    collect(child)
        elif isinstance(node, list):
            for child in node:
                collect(child)

    collect(schema)
    diagnostics = []

    def add(error, depth=0):
        if len(diagnostics) >= MAX_ARGUMENT_DIAGNOSTICS or depth > MAX_SCHEMA_DEPTH:
            return
        parts = [str(p) if isinstance(p, int) or p in fields else "*"
                 for p in islice(error.absolute_path, MAX_SCHEMA_DEPTH)]
        keyword, rule = error.validator, error.validator_value
        expected_type = error.schema.get("type", "unspecified") if isinstance(error.schema, dict) else "unspecified"
        expected = {"constraint": keyword}
        if keyword == "type":
            expected = {"type": rule}
        elif keyword in {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
                         "minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"}:
            expected = {keyword: rule}
        elif keyword in {"enum", "anyOf", "oneOf", "allOf"}:
            expected = {keyword + "_count": len(rule)}
        elif keyword in {"additionalProperties", "unevaluatedProperties", "uniqueItems"} and isinstance(rule, bool):
            expected = {keyword: rule}
        if len(serialized(expected)) > 256:
            expected = {"constraint": keyword}
        if keyword == "additionalProperties" and rule is False and isinstance(error.instance, dict):
            properties = error.schema.get("properties", {})
            patterns = error.schema.get("patternProperties", {})
            for name, value in error.instance.items():
                if name in properties or any(re.search(pattern, name) for pattern in patterns):
                    continue
                field = name if (_DIAGNOSTIC_IDENTIFIER.fullmatch(name)
                                 and not _SENSITIVE_ARGUMENT_KEY.search(name)) else "*"
                path = "$" + "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in [*parts, field])
                diagnostics.append({"path": path[:MAX_DIAGNOSTIC_PATH], "keyword": keyword,
                                    "expected_rule": expected, "expected_type": "absent",
                                    "actual_type": _json_type(value)})
                if len(diagnostics) >= MAX_ARGUMENT_DIAGNOSTICS:
                    return
            return
        # Missing required fields have no instance at their path.
        missing = list(islice((p for p in rule if p not in error.instance), MAX_ARGUMENT_DIAGNOSTICS)) if keyword == "required" else []
        for field in missing or [None]:
            path_parts = parts + ([field] if field is not None else [])
            path = "$" + "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in path_parts)
            diagnostics.append({"path": path[:MAX_DIAGNOSTIC_PATH], "keyword": keyword,
                                "expected_rule": expected,
                                "expected_type": error.schema.get("properties", {}).get(field, {}).get("type", "unspecified") if field is not None else expected_type,
                                "actual_type": "missing" if field is not None else _json_type(error.instance)})
            if len(diagnostics) >= MAX_ARGUMENT_DIAGNOSTICS:
                return
        for child in error.context:
            add(child, depth + 1)
            if len(diagnostics) >= MAX_ARGUMENT_DIAGNOSTICS:
                return

    for error in errors:
        add(error)
        if len(diagnostics) >= MAX_ARGUMENT_DIAGNOSTICS:
            break
    return diagnostics


def validate_arguments(schema: dict, arguments) -> None:
    if not isinstance(arguments, dict):
        raise SchemaError("invalid_arguments", diagnostics=[{
            "path": "$", "keyword": "type", "expected_rule": {"type": "object"},
            "expected_type": "object", "actual_type": _json_type(arguments),
        }])
    try:
        serialized(arguments)  # Reject non-JSON values and NaN/Infinity.
        resolved = resolved_schema(schema)
        validator = schema_validator(schema)(resolved)
        errors = validator.iter_errors(arguments)
        first = next(errors, None)
        if first is not None:
            raise SchemaError("invalid_arguments", diagnostics=_argument_diagnostics(chain([first], errors), resolved))
    except SchemaError:
        raise
    except Exception:
        raise SchemaError("invalid_arguments", diagnostics=[{
            "path": "$", "keyword": "json", "expected_rule": {"constraint": "finite_json"},
            "expected_type": "object", "actual_type": _json_type(arguments),
        }]) from None
