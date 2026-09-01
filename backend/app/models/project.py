"""A project is one system description the user wants an architecture for."""

from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import STAGE_ORDER, StageStatus

if TYPE_CHECKING:
    from app.models.stage import Stage


class Project(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)

    stages: Mapped[list["Stage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def stage_statuses(self) -> list[StageStatus]:
        """Statuses in pipeline order. Stages are eager-loaded, so this costs no extra query."""
        by_type = {stage.stage_type: stage.status for stage in self.stages}
        return [by_type.get(stage_type, StageStatus.PENDING) for stage_type in STAGE_ORDER]
