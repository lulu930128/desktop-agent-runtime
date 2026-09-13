"""Bounded local JSON Schema validation and explicit provider projections."""
from copy import deepcopy
import hashlib
import json

from jsonschema import Draft202012Validator, Draft7Validator

MAX_SCHEMA_BYTES = 256 * 1024
MAX_SCHEMA_DEPTH = 32
PROFILES = {"openai_non_strict", "openai_strict", "claude", "prompt"}


class SchemaError(ValueError):
    def __init__(self, code: str):
        self.code = code
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
                    target = target[part.replace('~1', '/').replace('~0', '~')]
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


def validate_arguments(schema: dict, arguments) -> None:
    if not isinstance(arguments, dict):
        raise SchemaError("invalid_arguments")
    try:
        serialized(arguments)  # Reject non-JSON values and NaN/Infinity.
        validator = schema_validator(schema)(resolved_schema(schema))
        if next(validator.iter_errors(arguments), None) is not None:
            raise SchemaError("invalid_arguments")
    except SchemaError:
        raise
    except Exception:
        raise SchemaError("invalid_arguments") from None
