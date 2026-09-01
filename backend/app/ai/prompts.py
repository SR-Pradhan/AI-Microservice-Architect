"""One focused prompt per stage.

Deliberate rule from the spec: a stage receives ONLY the approved output of prior stages, never a
running conversation. Tight context, no drift.
"""

import json
from typing import Any

from app.models.enums import StageType

SYSTEM_PROMPT = (
    "You are a senior distributed-systems architect. You design microservice architectures that "
    "are pragmatic and implementable, not academic. You avoid both extremes: a distributed "
    "monolith with one giant service, and nano-services split so finely that every user action "
    "needs six network hops. Every decision you make must be justifiable to an engineering team."
)

BOUNDARIES_INSTRUCTIONS = """\
Decompose the system below into microservices.

Rules you must follow:
- Split by business capability and data ownership, NOT by technical layer. "OrderService" is a
  service; "DatabaseService", "ControllerService" or "UtilService" are not.
- Each service owns its own data. If two services would both write the same entity, that is a sign
  the boundary is wrong.
- Aim for 4-8 services for a typical system. Only exceed that if the description genuinely demands it.
- Do not invent capabilities the description never mentions. Stay inside the described scope.
- In boundaries_rationale, be explicit about which splits were judgement calls and what the
  alternative was, so a human reviewer knows exactly what to push back on.
"""


HLD_INSTRUCTIONS = """\
Produce the high-level design for the services below.

Rules you must follow:
- Use ONLY the service names from the approved boundaries, spelled exactly. Do not invent a service,
  do not rename one, and do not omit one.
- Choose sync vs async deliberately. A call is synchronous only when the caller genuinely cannot
  continue without the answer (e.g. checking stock before confirming an order). Everything else —
  notifications, analytics, downstream side effects — must be an async event.
- Prefer async. Every synchronous call is a runtime coupling: if the callee is down, the caller is
  degraded too.
- Name events in dot.case describing something that already happened: order.created, not create_order.
- Give each service its own datastore. Two services sharing one database is a boundary failure.
- In design_notes, state the main failure modes: what breaks if each hot path goes down.
"""

LLD_INSTRUCTIONS = """\
Produce the low-level design for every service in the approved high-level design.

Rules you must follow:
- Cover EVERY service from the HLD, spelled exactly. Do not add or omit one.
- Every synchronous call in the HLD must appear as a real endpoint on the callee, and that
  endpoint's called_by must list the caller. A call in the HLD with no endpoint to receive it is a
  broken design.
- Every event in the HLD must appear in its producer's published_events and in each consumer's
  consumed_events, spelled exactly as in the HLD.
- Use 'public' in called_by for endpoints a client or gateway calls directly.
- Entities are the data this service owns. Do not duplicate another service's entity; reference it
  by id instead (e.g. Order has a userId field, not an embedded User).
- Pick a concrete tech_stack per service and say why it fits that service's workload.
- internal_logic_notes is where the real engineering goes: transaction boundaries, idempotency keys,
  what happens on retry, ordering guarantees. Be specific, not generic.
"""

DB_SCHEMA_INSTRUCTIONS = """\
Design the datastore for every service in the approved low-level design.

Rules you must follow:
- Cover EVERY service, spelled exactly, and use the exact engine that service was given in the HLD.
  Do not switch a service to a different database.
- Every entity from the LLD must have exactly one table. Do not create a table for another
  service's entity — each service owns its own data.
- Every table needs a primary key column.
- For a non-relational engine (Redis, MongoDB, ...), still describe it as tables and columns:
  the collection or key pattern is the table, its fields are the columns. Say so in notes.
- Index only what a real query needs, and state that query in the rationale. Do not add indexes
  speculatively — every index costs write throughput.
- Index columns must be columns that actually exist on that table.
- A foreign key to a table in ANOTHER service is a logical reference only, never a database
  constraint — a real FK across services couples their datastores and breaks the boundary.
- In notes, cover partitioning or sharding, retention, and the hot read/write paths.
"""

KAFKA_EVENTS_INSTRUCTIONS = """\
Define the Kafka event contract for every asynchronous flow in the approved high-level design.

Rules you must follow:
- One topic per event in the HLD, named exactly as the HLD names it. Do not invent topics for
  events that are not in the design, and do not drop any.
- The producer and the consumer services must match the HLD exactly.
- partition_key MUST be one of the fields you list in payload_fields. Choose it for ordering:
  events sharing that key are delivered in order, so use the id of the aggregate whose sequence
  matters (usually the order or the entity being changed), never a random or timestamp field.
- Explain the ordering guarantee your partition key actually buys in ordering_notes.
- Give every consumer its own consumer_group. Two different services must never share a group —
  they would steal each other's messages instead of both receiving them.
- The payload carries what a consumer needs to act without calling back to the producer, but it is
  not the whole entity. Include ids, the changed state, and a timestamp.
- Set retention deliberately: short for transient notifications, long or compacted for events that
  rebuild state.
- dead_letter_strategy must say concretely how many retries, with what backoff, and where a
  poison message ends up.
"""

INFRA_INSTRUCTIONS = """\
Define the deployment configuration for every service in the approved design.

You are NOT writing YAML. You describe the facts; the Dockerfiles, docker-compose.yml and
Kubernetes manifests are generated from what you return, so be precise rather than verbose.

Rules you must follow:
- Cover EVERY service, spelled exactly as in the low-level design.
- base_image is the RUNTIME image, pinned to a specific tag. Never 'latest', and never an SDK or
  build image: 'golang:1.22' ships the whole Go toolchain to production, and a JDK image ships a
  compiler you do not need at runtime.
- For a COMPILED language (Go, Java, Rust, .NET) you must use a multi-stage build: set
  builder_image to the SDK image, put the compile steps in builder_steps, list the produced
  artifacts in copy_from_builder, and set base_image to a slim runtime — alpine or distroless for
  Go and Rust, a JRE image for Java. This is the difference between a 900MB image and a 30MB one.
- For an INTERPRETED language (Node, Python, Ruby) leave builder_image null.
- The build stage runs in /app, so every path in copy_from_builder must start with /app —
  '/app/target/order-service.jar', never '/target/order-service.jar'.
- If start_command hardcodes a port, it must be the same port you declared.
- If start_command runs something that has to be produced first — 'node dist/main.js' needs
  'npm run build', a jar needs a compile — then the step that produces it MUST be in the build.
  A service that installs only production dependencies and then starts a file nothing built will
  crash on boot.
- build_steps are the Dockerfile lines between the base image and the start command, in order.
  Do not include FROM, EXPOSE, WORKDIR or CMD — those are generated for you. Copy the dependency
  manifest and install dependencies BEFORE copying the source, so Docker's layer cache works.
- port must be unique across all services — two services cannot bind the same port in compose.
- Declare one infra_component per backing store the design actually uses. Each service that owns a
  database gets its own component, because services must not share a datastore. Add exactly one
  Kafka component if the design has any events.
- depends_on must name infra_components you declared. A service that publishes or consumes events
  depends on Kafka. A service with its own datastore depends on that datastore.
- env_vars must include the connection details a service needs (its database URL, the Kafka
  brokers). Mark anything credential-like as secret — and note that a URL with the password
  embedded in it (postgresql://user:pass@host/db) IS credential-like.
- Service-to-service hostnames use the DEPLOYED name, which is the service name in lower kebab
  case: OrderService is reachable at 'order-service', never at 'OrderService'. Getting this wrong
  means the hostname does not resolve at runtime.
- A service reaches a datastore on that datastore's own internal port, not the host port you
  declared for it: Postgres is always 5432 inside the network, Mongo 27017, Redis 6379.
- Set resource requests and limits deliberately per workload — a cache-backed read service is not
  the same shape as a payments service.
"""

STAGE_INSTRUCTIONS = {
    StageType.BOUNDARIES: BOUNDARIES_INSTRUCTIONS,
    StageType.HLD: HLD_INSTRUCTIONS,
    StageType.LLD: LLD_INSTRUCTIONS,
    StageType.DB_SCHEMA: DB_SCHEMA_INSTRUCTIONS,
    StageType.KAFKA_EVENTS: KAFKA_EVENTS_INSTRUCTIONS,
    StageType.INFRA: INFRA_INSTRUCTIONS,
}


def build_stage_prompt(
    stage_type: StageType, raw_description: str, prior_outputs: dict[str, Any]
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for a stage."""
    instructions = STAGE_INSTRUCTIONS.get(stage_type)
    if instructions is None:
        raise NotImplementedError(f"No prompt template for stage '{stage_type.value}' yet")

    sections = [
        instructions,
        "## System description\n" + raw_description.strip(),
    ]
    if prior_outputs:
        sections.append(
            "## Approved output of previous stages\n```json\n"
            + json.dumps(prior_outputs, indent=2)
            + "\n```"
        )
    return SYSTEM_PROMPT, "\n\n".join(sections)
