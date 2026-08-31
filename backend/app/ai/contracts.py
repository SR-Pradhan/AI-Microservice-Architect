"""Output contracts for each pipeline stage.

Every stage's output shape is a Pydantic model. That one definition does three jobs: it is the
JSON schema Claude is forced to produce, it validates what comes back, and it documents the
stage. Adding a stage means adding a model here and registering it in STAGE_CONTRACTS.
"""

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


# Stages 2-6 land in later versions.
STAGE_CONTRACTS: dict[StageType, type[StageContract]] = {
    StageType.BOUNDARIES: BoundariesOutput,
}


def contract_for(stage_type: StageType) -> type[StageContract]:
    contract = STAGE_CONTRACTS.get(stage_type)
    if contract is None:
        raise NotImplementedError(f"Stage '{stage_type.value}' is not implemented yet")
    return contract
