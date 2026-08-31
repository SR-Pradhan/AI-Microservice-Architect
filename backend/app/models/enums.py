"""Enums shared by the ORM models and the Pydantic schemas."""

from enum import Enum


class StageType(str, Enum):
    """The six pipeline stages, in execution order."""

    BOUNDARIES = "boundaries"
    HLD = "hld"
    LLD = "lld"
    DB_SCHEMA = "db_schema"
    KAFKA_EVENTS = "kafka_events"
    INFRA = "infra"


class StageStatus(str, Enum):
    """Lifecycle of a single stage: nothing yet -> LLM output -> human edit -> locked."""

    PENDING = "pending"
    GENERATED = "generated"
    EDITED = "edited"
    APPROVED = "approved"


STAGE_ORDER: list[StageType] = [
    StageType.BOUNDARIES,
    StageType.HLD,
    StageType.LLD,
    StageType.DB_SCHEMA,
    StageType.KAFKA_EVENTS,
    StageType.INFRA,
]
