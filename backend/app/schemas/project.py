"""Request/response contracts for the project + stage endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import StageStatus, StageType


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    raw_description: str = Field(min_length=10, description="Plain-English description of the system")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    raw_description: str | None = Field(default=None, min_length=10)


class StageUpdate(BaseModel):
    """The user's edited version of a stage output. Validated against that stage's contract."""

    output_json: dict[str, Any]


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage_type: StageType
    status: StageStatus
    version: int
    output_json: dict[str, Any] | None = None
    user_edited_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    raw_description: str
    created_at: datetime
    updated_at: datetime
    # Stage statuses in pipeline order, so a list view can show progress without a second request.
    stage_statuses: list[StageStatus] = []


class ProjectDetail(ProjectRead):
    """Project plus the state of all six stages — what the review UI loads."""

    stages: list[StageRead] = []
