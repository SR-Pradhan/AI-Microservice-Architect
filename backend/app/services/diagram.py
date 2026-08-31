"""Diagram Renderer — turns stage JSON into Mermaid syntax for the frontend to draw.

Rendering happens here rather than in React so the diagram logic is tested once, server-side, and
every client (UI, export, docs) draws the same picture.
"""

import re
from typing import Any

from app.models.enums import StageType

# Mermaid node ids must be plain identifiers, so service names are sanitised into ids and the real
# name is kept as the visible label.
_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _node_id(name: str) -> str:
    cleaned = _ID_SAFE.sub("_", name.strip()) or "unnamed"
    return cleaned if cleaned[0].isalpha() else f"n_{cleaned}"


def _quote(text: str) -> str:
    """Mermaid labels are quoted; a double quote inside one would end the label early."""
    return text.replace('"', "'").replace("\n", " ").strip()


def hld_to_mermaid(hld: dict[str, Any]) -> str:
    """Service map: solid arrows are synchronous calls, dotted arrows are async events."""
    lines = ["flowchart LR"]

    for service in hld.get("services", []):
        name = service.get("name", "")
        datastore = (service.get("datastore") or "").strip()
        # <br/> is the one HTML tag Mermaid reliably keeps under securityLevel 'strict'.
        label = f"{_quote(name)}<br/>({_quote(datastore)})" if datastore else _quote(name)
        lines.append(f'    {_node_id(name)}["{label}"]')

    for dependency in hld.get("external_dependencies", []):
        name = dependency.get("name", "")
        lines.append(f'    {_node_id("ext_" + name)}(["{_quote(name)}"])')

    if hld.get("async_flows"):
        # One broker node makes it visually obvious which paths are event-driven.
        lines.append('    broker{{"Event Broker (Kafka)"}}')

    for call in hld.get("sync_calls", []):
        caller, callee = call.get("caller", ""), call.get("callee", "")
        lines.append(
            f'    {_node_id(caller)} -->|"{_quote(call.get("protocol", "REST"))}"| {_node_id(callee)}'
        )

    for flow in hld.get("async_flows", []):
        event = _quote(flow.get("event", ""))
        lines.append(f'    {_node_id(flow.get("producer", ""))} -.->|"{event}"| broker')
        for consumer in flow.get("consumers", []):
            lines.append(f'    broker -.->|"{event}"| {_node_id(consumer)}')

    for dependency in hld.get("external_dependencies", []):
        target = _node_id("ext_" + dependency.get("name", ""))
        for user in dependency.get("used_by", []):
            lines.append(f"    {_node_id(user)} --> {target}")

    return "\n".join(lines)


RENDERERS = {StageType.HLD: hld_to_mermaid}


def render_stage(stage_type: StageType, output: dict[str, Any]) -> str:
    renderer = RENDERERS.get(stage_type)
    if renderer is None:
        raise NotImplementedError(f"No diagram for stage '{stage_type.value}'")
    return renderer(output)
