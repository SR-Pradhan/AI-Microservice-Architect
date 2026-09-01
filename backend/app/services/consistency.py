"""Cross-stage consistency checks.

Nothing stops Claude from producing a Stage 2 HLD that quietly contradicts the Stage 1 boundaries
you approved — inventing a service, or dropping one. Schema validation cannot catch that, because
the shape is perfectly valid; only the *meaning* is wrong.

These checks run right after schema validation. A failure is raised as ConsistencyError, which the
Stage Executor treats exactly like a schema failure: feed the problem back and ask for a fix.
"""

import re
from typing import Any, Callable

from app.ai.contracts import (
    DBSchemaOutput,
    HLDOutput,
    InfraOutput,
    KafkaEventsOutput,
    LLDOutput,
    StageContract,
)
from app.models.enums import StageType


class ConsistencyError(ValueError):
    """The output is schema-valid but contradicts an earlier approved stage."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def check_hld(hld: HLDOutput, prior_outputs: dict[str, Any]) -> list[str]:
    """Every service name in the HLD must come from the approved Stage 1 boundaries."""
    boundaries = prior_outputs.get(StageType.BOUNDARIES.value) or {}
    approved = {s["name"] for s in boundaries.get("services", [])}
    if not approved:
        return []  # nothing to check against

    problems: list[str] = []

    def check_name(name: str, where: str) -> None:
        if name not in approved:
            problems.append(
                f"{where} refers to '{name}', which is not one of the approved Stage 1 services "
                f"({', '.join(sorted(approved))})"
            )

    hld_names = {s.name for s in hld.services}
    for service in hld.services:
        check_name(service.name, "services[]")
    for missing in sorted(approved - hld_names):
        problems.append(f"Approved Stage 1 service '{missing}' is missing from the HLD services[]")

    for call in hld.sync_calls:
        check_name(call.caller, f"sync_calls[{call.caller}->{call.callee}].caller")
        check_name(call.callee, f"sync_calls[{call.caller}->{call.callee}].callee")
        if call.caller == call.callee:
            problems.append(f"sync_calls contains a self-call on '{call.caller}'")

    for flow in hld.async_flows:
        check_name(flow.producer, f"async_flows[{flow.event}].producer")
        for consumer in flow.consumers:
            check_name(consumer, f"async_flows[{flow.event}].consumers")
        if flow.producer in flow.consumers:
            problems.append(f"async_flows['{flow.event}'] has '{flow.producer}' consuming its own event")

    for dependency in hld.external_dependencies:
        for user in dependency.used_by:
            check_name(user, f"external_dependencies[{dependency.name}].used_by")

    return problems


def check_lld(lld: LLDOutput, prior_outputs: dict[str, Any]) -> list[str]:
    """The LLD must actually implement the HLD.

    Two failures matter most, and neither is visible to schema validation:
      * a synchronous call in the HLD that no endpoint on the callee can receive;
      * an event in the HLD that its producer never publishes or a consumer never consumes.
    Either one means the design does not hold together.
    """
    hld = prior_outputs.get(StageType.HLD.value) or {}
    hld_names = {s["name"] for s in hld.get("services", [])}
    if not hld_names:
        return []

    problems: list[str] = []
    lld_names = {s.name for s in lld.services}

    for name in sorted(lld_names - hld_names):
        problems.append(
            f"LLD describes '{name}', which is not one of the HLD services "
            f"({', '.join(sorted(hld_names))})"
        )
    for name in sorted(hld_names - lld_names):
        problems.append(f"HLD service '{name}' has no low-level design")

    by_name = {s.name: s for s in lld.services}

    # Every sync call in the HLD needs a real endpoint on the callee that names the caller.
    for call in hld.get("sync_calls", []):
        caller, callee = call.get("caller", ""), call.get("callee", "")
        service = by_name.get(callee)
        if service is None:
            continue  # already reported as a missing service
        if not any(caller in endpoint.called_by for endpoint in service.endpoints):
            problems.append(
                f"HLD has {caller} calling {callee}, but no endpoint on {callee} lists "
                f"'{caller}' in called_by"
            )

    # Every event in the HLD must be published and consumed by the services the HLD says.
    for flow in hld.get("async_flows", []):
        event = flow.get("event", "")
        producer = by_name.get(flow.get("producer", ""))
        if producer is not None and event not in producer.published_events:
            problems.append(
                f"HLD says {producer.name} publishes '{event}', but its published_events does not "
                f"list it (has: {producer.published_events or 'nothing'})"
            )
        for consumer_name in flow.get("consumers", []):
            consumer = by_name.get(consumer_name)
            if consumer is not None and event not in consumer.consumed_events:
                problems.append(
                    f"HLD says {consumer_name} consumes '{event}', but its consumed_events does "
                    f"not list it (has: {consumer.consumed_events or 'nothing'})"
                )

    # called_by must name a real service, or the literal 'public'.
    for service in lld.services:
        for endpoint in service.endpoints:
            for caller in endpoint.called_by:
                if caller != "public" and caller not in hld_names:
                    problems.append(
                        f"{service.name} {endpoint.method} {endpoint.path} is called_by "
                        f"'{caller}', which is neither a known service nor 'public'"
                    )

    return problems


def check_db_schema(schema: DBSchemaOutput, prior_outputs: dict[str, Any]) -> list[str]:
    """The schema must store exactly what the LLD defined, in the engine the HLD chose."""
    hld = prior_outputs.get(StageType.HLD.value) or {}
    lld = prior_outputs.get(StageType.LLD.value) or {}
    lld_services = {s["name"]: s for s in lld.get("services", [])}
    if not lld_services:
        return []

    problems: list[str] = []
    schema_services = {s.name: s for s in schema.services}

    for name in sorted(set(schema_services) - set(lld_services)):
        problems.append(f"Schema describes '{name}', which has no low-level design")
    for name in sorted(set(lld_services) - set(schema_services)):
        problems.append(f"Service '{name}' has no datastore schema")

    engines = {s["name"]: s["datastore"] for s in hld.get("services", [])}
    # An entity belongs to exactly one service; used to catch a service storing another's data.
    entity_owner = {
        entity["name"]: service["name"]
        for service in lld.get("services", [])
        for entity in service.get("entities", [])
    }

    for name, service in schema_services.items():
        expected_engine = engines.get(name)
        if expected_engine and expected_engine.lower() not in service.engine.lower():
            problems.append(
                f"{name} uses engine '{service.engine}', but the HLD chose '{expected_engine}'"
            )

        owned = {e["name"] for e in lld_services.get(name, {}).get("entities", [])}
        stored = {t.entity for t in service.tables}
        for missing in sorted(owned - stored):
            problems.append(f"{name} entity '{missing}' has no table")
        for extra in sorted(stored - owned):
            owner = entity_owner.get(extra)
            if owner and owner != name:
                problems.append(
                    f"{name} has a table for entity '{extra}', which is owned by {owner} — "
                    f"each service must own its own data"
                )
            elif not owner:
                problems.append(f"{name} has a table for '{extra}', which is not an LLD entity")

        for table in service.tables:
            column_names = {c.name for c in table.columns}
            if not any(c.primary_key for c in table.columns):
                problems.append(f"{name}.{table.name} has no primary key column")
            for index in table.indexes:
                for column in index.columns:
                    if column not in column_names:
                        problems.append(
                            f"{name}.{table.name} index '{index.name}' uses column '{column}', "
                            f"which does not exist on that table"
                        )
            for fk in table.foreign_keys:
                if fk.column not in column_names:
                    problems.append(
                        f"{name}.{table.name} foreign key uses column '{fk.column}', which does "
                        f"not exist on that table"
                    )
                if fk.references_service not in lld_services:
                    problems.append(
                        f"{name}.{table.name} foreign key references unknown service "
                        f"'{fk.references_service}'"
                    )

    return problems


def check_kafka_events(events: KafkaEventsOutput, prior_outputs: dict[str, Any]) -> list[str]:
    """The spec's explicit Stage 5 requirement.

    Every consumer a topic lists must actually be a subscriber in the Stage 3 LLD, and every event
    in the HLD must have a topic. Without this, the event contracts drift from the design they are
    supposed to implement and nothing else would ever notice.
    """
    hld = prior_outputs.get(StageType.HLD.value) or {}
    lld = prior_outputs.get(StageType.LLD.value) or {}
    flows = {f["event"]: f for f in hld.get("async_flows", [])}
    if not flows:
        return []

    problems: list[str] = []
    topics = {t.name: t for t in events.topics}

    for missing in sorted(set(flows) - set(topics)):
        problems.append(f"HLD event '{missing}' has no topic")
    for extra in sorted(set(topics) - set(flows)):
        problems.append(f"Topic '{extra}' does not correspond to any event in the HLD")

    lld_services = {s["name"]: s for s in lld.get("services", [])}

    for name, topic in topics.items():
        flow = flows.get(name)
        if flow is None:
            continue  # already reported as an extra topic

        if topic.producer != flow["producer"]:
            problems.append(
                f"Topic '{name}' is produced by {topic.producer}, but the HLD says "
                f"{flow['producer']}"
            )

        listed = {c.service for c in topic.consumers}
        expected = set(flow.get("consumers", []))
        for missing in sorted(expected - listed):
            problems.append(f"Topic '{name}' does not list {missing}, which consumes it in the HLD")
        for extra in sorted(listed - expected):
            problems.append(f"Topic '{name}' lists consumer {extra}, which does not consume it in the HLD")

        # The spec's requirement: a consumer must actually declare a subscription in its LLD.
        for consumer in topic.consumers:
            service = lld_services.get(consumer.service)
            if service is None:
                problems.append(f"Topic '{name}' lists unknown service '{consumer.service}'")
            elif name not in service.get("consumed_events", []):
                problems.append(
                    f"Topic '{name}' lists {consumer.service} as a consumer, but that service's "
                    f"LLD does not declare '{name}' in consumed_events"
                )

        producer_lld = lld_services.get(topic.producer)
        if producer_lld is not None and name not in producer_lld.get("published_events", []):
            problems.append(
                f"Topic '{name}' is produced by {topic.producer}, but that service's LLD does not "
                f"declare it in published_events"
            )

        # Two services sharing a consumer group would steal each other's messages.
        groups: dict[str, str] = {}
        for consumer in topic.consumers:
            owner = groups.get(consumer.consumer_group)
            if owner and owner != consumer.service:
                problems.append(
                    f"Topic '{name}': {consumer.service} and {owner} share consumer group "
                    f"'{consumer.consumer_group}' — they would steal each other's messages"
                )
            groups[consumer.consumer_group] = consumer.service

        field_names = {f.name for f in topic.payload_fields}
        if topic.partition_key not in field_names:
            problems.append(
                f"Topic '{name}' partitions on '{topic.partition_key}', which is not one of its "
                f"payload fields ({', '.join(sorted(field_names))})"
            )

    return problems


def _engine_stem_haystack(image: str) -> str:
    """The image name with punctuation stripped, so a stem can be searched inside it."""
    return re.sub(r"[^a-z0-9]", "", image.lower())


def _engine_stem(text: str) -> str:
    """A short normalised stem for matching an engine name against a Docker image.

    Exact matching fails on the obvious pairs — engine "PostgreSQL" vs image "postgres:16-alpine",
    "MongoDB" vs "mongo:7". Stripping punctuation and taking the first five characters matches every
    common engine (postg, mongo, redis, mysql, elast) without a hand-maintained alias table.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())[:5]


def check_infra(infra: InfraOutput, prior_outputs: dict[str, Any]) -> list[str]:
    """The deployment config must actually be deployable, and match the design above it."""
    lld = prior_outputs.get(StageType.LLD.value) or {}
    db = prior_outputs.get(StageType.DB_SCHEMA.value) or {}
    lld_services = {s["name"]: s for s in lld.get("services", [])}
    if not lld_services:
        return []

    problems: list[str] = []
    infra_services = {s.name: s for s in infra.services}

    for name in sorted(set(infra_services) - set(lld_services)):
        problems.append(f"Infra describes '{name}', which has no low-level design")
    for name in sorted(set(lld_services) - set(infra_services)):
        problems.append(f"Service '{name}' has no deployment configuration")

    # Two services on the same port cannot both bind it in docker-compose.
    by_port: dict[int, str] = {}
    for name, service in sorted(infra_services.items()):
        clash = by_port.get(service.port)
        if clash:
            problems.append(f"{name} and {clash} both use port {service.port}")
        by_port[service.port] = name

        if ":" not in service.base_image or service.base_image.endswith(":latest"):
            problems.append(
                f"{name} base image '{service.base_image}' is not pinned to a specific tag"
            )

    components = {c.name: c for c in infra.infra_components}
    kafka_components = {n for n, c in components.items() if "kafka" in c.image.lower()}
    engines = {s["name"]: s["engine"] for s in db.get("services", [])}

    for name, service in infra_services.items():
        for dependency in service.depends_on:
            if dependency not in components:
                problems.append(
                    f"{name} depends on '{dependency}', which is not a declared infra component"
                )

        lld_service = lld_services.get(name, {})
        uses_events = bool(lld_service.get("published_events") or lld_service.get("consumed_events"))
        if uses_events and not (set(service.depends_on) & kafka_components):
            problems.append(
                f"{name} publishes or consumes events but does not depend on a Kafka component"
            )

        engine = engines.get(name)
        if engine:
            # The service must depend on a component actually running its datastore engine.
            stem = _engine_stem(engine)
            matched = any(
                stem in _engine_stem_haystack(components[d].image)
                for d in service.depends_on
                if d in components
            )
            if not matched:
                problems.append(
                    f"{name} stores data in {engine} but depends on no component running it "
                    f"(depends_on: {service.depends_on or 'nothing'})"
                )

    # Service-to-service hostnames must be the generated DNS name (order-service), not the design
    # name (OrderService). PascalCase in a connection string simply will not resolve.
    from app.services.export import kebab

    from app.services.export import container_port_for

    dns_names = {name: kebab(name) for name in infra_services}
    # Inside the compose/k8s network a service reaches a component on its CONTAINER port. The
    # component's declared port is the host mapping, and connecting to it from inside fails.
    component_ports = {
        c.name: container_port_for(c.image, c.port) for c in infra.infra_components
    }
    for name, service in infra_services.items():
        for env in service.env_vars:
            for other, dns in dns_names.items():
                if other != dns and re.search(rf"\b{re.escape(other)}\b", env.value):
                    problems.append(
                        f"{name} env var {env.name} refers to host '{other}', but the generated "
                        f"service is named '{dns}' — use '{dns}' or it will not resolve"
                    )
            for component, inside in component_ports.items():
                match = re.search(rf"\b{re.escape(component)}:(\d+)", env.value)
                if match and int(match.group(1)) != inside:
                    problems.append(
                        f"{name} env var {env.name} connects to {component} on port "
                        f"{match.group(1)}, but inside the network it listens on {inside}"
                    )
            if not env.secret and re.search(r"://[^/\s:@]+:[^/\s@]+@", env.value):
                problems.append(
                    f"{name} env var {env.name} embeds credentials in its value but is not marked "
                    f"secret — it would be written into a ConfigMap"
                )

    for component in infra.infra_components:
        for user in component.used_by:
            if user not in infra_services:
                problems.append(
                    f"Infra component '{component.name}' is used_by unknown service '{user}'"
                )

    return problems


# One optional checker per stage. Stages with no entry are schema-validated only.
CROSS_STAGE_CHECKS: dict[StageType, Callable[[Any, dict[str, Any]], list[str]]] = {
    StageType.HLD: check_hld,
    StageType.LLD: check_lld,
    StageType.DB_SCHEMA: check_db_schema,
    StageType.KAFKA_EVENTS: check_kafka_events,
    StageType.INFRA: check_infra,
}


def check_consistency(
    stage_type: StageType, output: StageContract, prior_outputs: dict[str, Any]
) -> None:
    """Raises ConsistencyError if the output contradicts an earlier approved stage."""
    checker = CROSS_STAGE_CHECKS.get(stage_type)
    if checker is None:
        return
    problems = checker(output, prior_outputs)
    if problems:
        raise ConsistencyError(problems)
