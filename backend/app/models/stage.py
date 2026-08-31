"""One row per (project, stage) — holds the LLM output and the user's edit of it."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import StageStatus, StageType

if TYPE_CHECKING:
    from app.models.project import Project


class Stage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "stages"
    __table_args__ = (UniqueConstraint("project_id", "stage_type", name="uq_stage_per_project"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    stage_type: Mapped[StageType] = mapped_column(
        SAEnum(StageType, name="stage_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[StageStatus] = mapped_column(
        SAEnum(StageStatus, name="stage_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=StageStatus.PENDING,
    )
    # What was fed into this stage (approved outputs of prior stages).
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Raw, schema-validated LLM output.
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # The user's edited version, if they changed anything.
    user_edited_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Bumped every time the stage is re-generated.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped["Project"] = relationship(back_populates="stages")

    @property
    def effective_json(self) -> dict[str, Any] | None:
        """The version downstream stages should consume: the user's edit wins."""
        return self.user_edited_json or self.output_json
