"""Output contracts for each pipeline stage.

Every stage's output shape is a Pydantic model. That one definition does three jobs: it is the
JSON schema Claude is forced to produce, it validates what comes back, and it documents the
stage. Adding a stage means adding a model here and registering it in STAGE_CONTRACTS.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import StageType


class StageContract(BaseModel):
    """Base for every stage output. Forbids unknown keys so drift is caught, not absorbed."""

    model_config = ConfigDict(extra="forbid")


class ServiceBoundary(StageContract):
    name: str = Field(description="PascalCase service name, e.g. OrderService")
    responsibility: str = Field(description="One or two sentences: what this service owns")
    domain: str = Field(description="Business domain it belongs to, e.g. Orders")
    key_entities: list[str] = Field(
        default_factory=list, description="Main data entities this service is the source of truth for"
    )


class BoundariesOutput(StageContract):
    """Stage 1 output: the service decomposition."""

    services: list[ServiceBoundary] = Field(min_length=2, max_length=15)
    boundaries_rationale: str = Field(
        description="Why the system was split this way, and which splits were judgement calls"
    )


class HLDService(StageContract):
    name: str = Field(description="Must exactly match a service name from Stage 1")
    datastore: str = Field(description="e.g. PostgreSQL, MongoDB, Redis, or 'none'")
    scaling_notes: str = Field(description="What makes this service scale, or its main bottleneck")


class SyncCall(StageContract):
    """A request/response call. The caller blocks waiting for the callee."""

    caller: str
    callee: str
    purpose: str = Field(description="Why this call is synchronous rather than an event")
    protocol: Literal["REST", "gRPC", "GraphQL"] = "REST"


class AsyncFlow(StageContract):
    """A fire-and-forget event. The producer does not wait."""

    event: str = Field(description="Event name in dot.case, e.g. order.created")
    producer: str
    consumers: list[str] = Field(min_length=1)
    purpose: str


class ExternalDependency(StageContract):
    name: str = Field(description="Third-party system, e.g. Stripe, SendGrid, S3")
    used_by: list[str] = Field(min_length=1)
    purpose: str


class HLDOutput(StageContract):
    """Stage 2 output: the service map and how services talk to each other."""

    services: list[HLDService] = Field(min_length=2)
    sync_calls: list[SyncCall] = Field(
        default_factory=list, description="Calls where the caller must wait for an answer"
    )
    async_flows: list[AsyncFlow] = Field(
        default_factory=list, description="Events published to a broker; the producer does not wait"
    )
    external_dependencies: list[ExternalDependency] = Field(default_factory=list)
    design_notes: str = Field(
        description="Key decisions: what is sync vs async and why, and the main failure modes"
    )


class DataField(StageContract):
    """One field of an entity, request body or response body."""

    name: str
    type: Literal[
        "string", "uuid", "integer", "decimal", "boolean", "timestamp", "array", "object"
    ]
    required: bool = True
    description: str


class Entity(StageContract):
    name: str = Field(description="PascalCase entity name, e.g. Order")
    description: str
    fields: list[DataField] = Field(min_length=1)


class ApiEndpoint(StageContract):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(description="e.g. /orders/{orderId} — path params in braces")
    summary: str
    request_fields: list[DataField] = Field(
        default_factory=list, description="Body fields. Empty for GET/DELETE."
    )
    response_fields: list[DataField] = Field(default_factory=list)
    called_by: list[str] = Field(
        default_factory=list,
        description="Service names that call this endpoint, or 'public' for client-facing ones",
    )


class ServiceLLD(StageContract):
    name: str = Field(description="Must exactly match a service name from Stage 2")
    tech_stack: str = Field(
        description="Runtime and framework, e.g. 'Java / Spring Boot' or 'Python / FastAPI'. "
        "Stage 6 infers the Dockerfile from this."
    )
    entities: list[Entity] = Field(min_length=1)
    endpoints: list[ApiEndpoint] = Field(min_length=1)
    published_events: list[str] = Field(
        default_factory=list, description="Event names this service publishes, from the HLD"
    )
    consumed_events: list[str] = Field(default_factory=list)
    internal_logic_notes: str = Field(
        description="The non-obvious logic: transactions, idempotency, ordering, retries"
    )


class LLDOutput(StageContract):
    """Stage 3 output: the internals of every service."""

    services: list[ServiceLLD] = Field(min_length=2)


class Column(StageContract):
    """A column in a relational table, or a field in a document / key-value record."""

    name: str = Field(description="snake_case, e.g. total_amount")
    type: str = Field(description="Store-native type, e.g. UUID, TEXT, NUMERIC(12,2), TIMESTAMPTZ")
    nullable: bool = False
    primary_key: bool = False
    description: str


class Index(StageContract):
    name: str
    columns: list[str] = Field(min_length=1, description="Must be columns of this table")
    unique: bool = False
    rationale: str = Field(description="Which query this index exists to serve")


class ForeignKeyRef(StageContract):
    """A reference to another entity.

    Within a service this is a real FK constraint. Across services it is a *logical* reference only —
    a database-level FK between services would couple their datastores and break the boundary.
    """

    column: str
    references_table: str
    references_service: str = Field(
        description="The service that owns the referenced table. May be this same service."
    )


class Table(StageContract):
    name: str = Field(description="snake_case plural, e.g. orders")
    entity: str = Field(description="The Stage 3 entity this table stores, spelled exactly")
    columns: list[Column] = Field(min_length=1)
    indexes: list[Index] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyRef] = Field(default_factory=list)


class ServiceSchema(StageContract):
    name: str = Field(description="Must exactly match a service name from Stage 2")
    engine: str = Field(description="Must match the datastore chosen for this service in Stage 2")
    tables: list[Table] = Field(
        min_length=1, description="Tables, collections or key patterns depending on the engine"
    )
    notes: str = Field(description="Partitioning, retention, hot paths, migration concerns")


class DBSchemaOutput(StageContract):
    """Stage 4 output: the physical datastore design for every service."""

    services: list[ServiceSchema] = Field(min_length=2)


class TopicConsumer(StageContract):
    service: str = Field(description="Must be a service that consumes this event in the HLD")
    consumer_group: str = Field(description="Kafka consumer group id, e.g. inventory-service-group")
    purpose: str = Field(description="What this consumer does when the event arrives")


class KafkaTopic(StageContract):
    name: str = Field(description="Must exactly match an event name from the HLD, e.g. order.placed")
    producer: str
    consumers: list[TopicConsumer] = Field(min_length=1)
    partition_key: str = Field(
        description="A field from payload_fields. Determines ordering — events sharing this key "
        "are delivered in order."
    )
    partitions: int = Field(ge=1, le=64)
    retention: str = Field(description="e.g. '7 days' or 'compacted'")
    payload_fields: list[DataField] = Field(min_length=1)
    ordering_notes: str = Field(description="Why this partition key, and what ordering it guarantees")


class KafkaEventsOutput(StageContract):
    """Stage 5 output: the event contracts behind every async flow in the HLD."""

    topics: list[KafkaTopic] = Field(min_length=1)
    dead_letter_strategy: str = Field(
        description="What happens to a message a consumer cannot process: retries, backoff, DLQ"
    )
    schema_evolution_notes: str = Field(
        description="How a field is added or removed without breaking existing consumers"
    )


class EnvVar(StageContract):
    name: str = Field(description="UPPER_SNAKE_CASE, e.g. DATABASE_URL")
    value: str = Field(description="The value, or a placeholder like 'changeme' for a secret")
    secret: bool = Field(default=False, description="True if this must come from a k8s Secret")
    description: str


class InfraComponent(StageContract):
    """A backing service the generated system needs: a database, the broker, a cache."""

    name: str = Field(description="Compose service name, e.g. orders-postgres")
    image: str = Field(description="Docker image with a pinned tag, e.g. postgres:16-alpine")
    port: int = Field(ge=1, le=65535)
    used_by: list[str] = Field(min_length=1, description="Services that connect to this component")


class ServiceInfra(StageContract):
    name: str = Field(description="Must exactly match a service name from Stage 3")
    base_image: str = Field(
        description="The RUNTIME image, pinned. For a compiled language this is a slim runtime "
        "(alpine, distroless, a JRE) — never the SDK or build image."
    )
    # Optional so a project generated before multi-stage support still validates.
    builder_image: str | None = Field(
        default=None,
        description="For compiled languages (Go, Java, Rust, .NET): the SDK image used to build. "
        "Leave null for interpreted languages that need no build stage.",
    )
    builder_steps: list[str] = Field(
        default_factory=list, description="Build stage steps, in order. Only if builder_image is set."
    )
    copy_from_builder: list[str] = Field(
        default_factory=list,
        description="Paths to copy out of the build stage into the runtime image, "
        "e.g. ['/app/target/order-service.jar']",
    )
    build_steps: list[str] = Field(
        default_factory=list,
        description="Runtime-stage RUN/COPY steps, in order, without FROM/WORKDIR/EXPOSE/CMD — "
        "those are generated. May be empty when everything comes from copy_from_builder.",
    )
    start_command: str = Field(description="The container's start command, e.g. 'java -jar app.jar'")
    port: int = Field(ge=1, le=65535, description="Container port. Must be unique across services.")
    health_check_path: str = Field(description="HTTP path for liveness/readiness, e.g. /health")
    env_vars: list[EnvVar] = Field(default_factory=list)
    replicas: int = Field(ge=1, le=20)
    cpu_request: str = Field(description="k8s CPU request, e.g. '100m'")
    cpu_limit: str = Field(description="k8s CPU limit, e.g. '500m'")
    memory_request: str = Field(description="k8s memory request, e.g. '256Mi'")
    memory_limit: str = Field(description="k8s memory limit, e.g. '512Mi'")
    depends_on: list[str] = Field(
        default_factory=list, description="Names of infra_components this service needs"
    )


class InfraOutput(StageContract):
    """Stage 6 output: everything needed to generate Dockerfiles, compose and k8s manifests."""

    services: list[ServiceInfra] = Field(min_length=2)
    infra_components: list[InfraComponent] = Field(min_length=1)
    notes: str = Field(description="Deployment order, migrations, scaling and secret handling")


STAGE_CONTRACTS: dict[StageType, type[StageContract]] = {
    StageType.BOUNDARIES: BoundariesOutput,
    StageType.HLD: HLDOutput,
    StageType.LLD: LLDOutput,
    StageType.DB_SCHEMA: DBSchemaOutput,
    StageType.KAFKA_EVENTS: KafkaEventsOutput,
    StageType.INFRA: InfraOutput,
}


def contract_for(stage_type: StageType) -> type[StageContract]:
    contract = STAGE_CONTRACTS.get(stage_type)
    if contract is None:
        raise NotImplementedError(f"Stage '{stage_type.value}' is not implemented yet")
    return contract
