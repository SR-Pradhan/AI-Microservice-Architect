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


# Stages 3-6 land in later versions.
STAGE_CONTRACTS: dict[StageType, type[StageContract]] = {
    StageType.BOUNDARIES: BoundariesOutput,
    StageType.HLD: HLDOutput,
}


def contract_for(stage_type: StageType) -> type[StageContract]:
    contract = STAGE_CONTRACTS.get(stage_type)
    if contract is None:
        raise NotImplementedError(f"Stage '{stage_type.value}' is not implemented yet")
    return contract
