"""Initial schema: projects + stages.

Revision ID: 0001
Revises:
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

stage_type_enum = postgresql.ENUM(
    "boundaries", "hld", "lld", "db_schema", "kafka_events", "infra",
    name="stage_type",
    create_type=False,
)
stage_status_enum = postgresql.ENUM(
    "pending", "generated", "edited", "approved", name="stage_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    stage_type_enum.create(bind, checkfirst=True)
    stage_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_type", stage_type_enum, nullable=False),
        sa.Column("status", stage_status_enum, nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("output_json", postgresql.JSONB(), nullable=True),
        sa.Column("user_edited_json", postgresql.JSONB(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "stage_type", name="uq_stage_per_project"),
    )
    op.create_index("ix_stages_project_id", "stages", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_stages_project_id", table_name="stages")
    op.drop_table("stages")
    op.drop_table("projects")
    bind = op.get_bind()
    stage_status_enum.drop(bind, checkfirst=True)
    stage_type_enum.drop(bind, checkfirst=True)
