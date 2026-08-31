"""Cross-stage consistency checks.

Nothing stops Claude from producing a Stage 2 HLD that quietly contradicts the Stage 1 boundaries
you approved — inventing a service, or dropping one. Schema validation cannot catch that, because
the shape is perfectly valid; only the *meaning* is wrong.

These checks run right after schema validation. A failure is raised as ConsistencyError, which the
Stage Executor treats exactly like a schema failure: feed the problem back and ask for a fix.
"""

from typing import Any, Callable

from app.ai.contracts import HLDOutput, LLDOutput, StageContract
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


# One optional checker per stage. Stages with no entry are schema-validated only.
CROSS_STAGE_CHECKS: dict[StageType, Callable[[Any, dict[str, Any]], list[str]]] = {
    StageType.HLD: check_hld,
    StageType.LLD: check_lld,
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
