"""A project is one system description the user wants an architecture for."""

from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.stage import Stage


class Project(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)

    stages: Mapped[list["Stage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
