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


# Mermaid ER type names must be bare identifiers: NUMERIC(12,2) or "timestamp with tz" break it.
_TYPE_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _er_type(raw: str) -> str:
    cleaned = _TYPE_SAFE.sub("_", raw.strip()).strip("_")
    return cleaned or "unknown"


def db_schema_to_mermaid(schema: dict[str, Any]) -> str:
    """One ER diagram covering every service, with relationships drawn from the foreign keys."""
    lines = ["erDiagram"]
    known_tables: set[str] = set()

    for service in schema.get("services", []):
        for table in service.get("tables", []):
            known_tables.add(table.get("name", ""))

    for service in schema.get("services", []):
        service_name = service.get("name", "")
        for table in service.get("tables", []):
            name = _node_id(table.get("name", ""))
            # A %% line is a Mermaid comment — it labels ownership without becoming an attribute.
            lines.append(f"    %% {service_name}")
            lines.append(f"    {name} {{")
            for column in table.get("columns", []):
                key = " PK" if column.get("primary_key") else ""
                lines.append(
                    f"        {_er_type(column.get('type', ''))} "
                    f"{_node_id(column.get('name', ''))}{key}"
                )
            lines.append("    }")

    for service in schema.get("services", []):
        for table in service.get("tables", []):
            for fk in table.get("foreign_keys", []):
                target = fk.get("references_table", "")
                if target not in known_tables:
                    continue  # referencing something outside this design; nothing to draw
                cross = fk.get("references_service") != service.get("name")
                # Dotted line = logical reference across a service boundary, not a real constraint.
                link = "}o..||" if cross else "}o--||"
                lines.append(
                    f'    {_node_id(table.get("name", ""))} {link} {_node_id(target)} : '
                    f'"{_quote(fk.get("column", ""))}"'
                )

    return "\n".join(lines)


def kafka_events_to_mermaid(events: dict[str, Any]) -> str:
    """Topic-centric view: producer -> topic -> each consumer, labelled by consumer group."""
    lines = ["flowchart LR"]
    services: set[str] = set()

    for topic in events.get("topics", []):
        services.add(topic.get("producer", ""))
        for consumer in topic.get("consumers", []):
            services.add(consumer.get("service", ""))

    for service in sorted(s for s in services if s):
        lines.append(f'    {_node_id(service)}["{_quote(service)}"]')

    for topic in events.get("topics", []):
        name = topic.get("name", "")
        topic_id = _node_id("topic_" + name)
        key = _quote(topic.get("partition_key", ""))
        partitions = topic.get("partitions", "")
        lines.append(
            f'    {topic_id}[/"{_quote(name)}<br/>key: {key} · {partitions}p"/]'
        )
        lines.append(f'    {_node_id(topic.get("producer", ""))} --> {topic_id}')
        for consumer in topic.get("consumers", []):
            lines.append(
                f'    {topic_id} -.->|"{_quote(consumer.get("consumer_group", ""))}"| '
                f'{_node_id(consumer.get("service", ""))}'
            )

    return "\n".join(lines)


RENDERERS = {
    StageType.HLD: hld_to_mermaid,
    StageType.DB_SCHEMA: db_schema_to_mermaid,
    StageType.KAFKA_EVENTS: kafka_events_to_mermaid,
}


def render_stage(stage_type: StageType, output: dict[str, Any]) -> str:
    renderer = RENDERERS.get(stage_type)
    if renderer is None:
        raise NotImplementedError(f"No diagram for stage '{stage_type.value}'")
    return renderer(output)
