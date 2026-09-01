"""Translate a Pydantic JSON Schema into the subset Gemini accepts.

Pydantic emits standard JSON Schema. Gemini's `response_schema` understands only a subset of it and
returns 400 INVALID_ARGUMENT on anything else — notably `additionalProperties`, which Pydantic adds
for every model because our contracts set `extra="forbid"`. It also does not resolve `$ref`/`$defs`,
so nested models must be inlined.

This converter therefore does two things: dereference, and drop what Gemini does not understand.
Constraints that get dropped are not lost — the response is still validated against the real
Pydantic model afterwards, which is where every rule is actually enforced.
"""

from typing import Any

# Fields Gemini's Schema type accepts. Anything else is silently dropped.
_SUPPORTED_KEYS = frozenset(
    {
        "type",
        "format",
        "description",
        "nullable",
        "enum",
        "items",
        "properties",
        "required",
        "anyOf",
        "minItems",
        "maxItems",
    }
)


def to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Returns a dereferenced, Gemini-safe copy of a Pydantic-generated JSON Schema."""
    defs = schema.get("$defs", {})
    return _convert(schema, defs)


def _convert(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_convert(item, defs) for item in node]
    if not isinstance(node, dict):
        return node

    # Inline $ref — Gemini has no $defs to look them up in.
    ref = node.get("$ref")
    if ref:
        name = ref.rsplit("/", 1)[-1]
        target = defs.get(name)
        if target is None:
            raise ValueError(f"Cannot resolve schema reference {ref!r}")
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _convert(merged, defs)

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _SUPPORTED_KEYS:
            continue  # additionalProperties, title, default, $defs, ... — all rejected by Gemini
        if key == "properties":
            result[key] = {name: _convert(sub, defs) for name, sub in value.items()}
        elif key in ("items", "anyOf"):
            result[key] = _convert(value, defs)
        else:
            result[key] = value

    # A Literal of one value becomes {"const": x}; Gemini understands enum, not const.
    if "const" in node and "enum" not in result:
        result["enum"] = [node["const"]]
        result.setdefault("type", "string")

    return result
