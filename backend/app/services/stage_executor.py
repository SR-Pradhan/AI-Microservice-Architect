"""The Stage Executor — the engine of the whole pipeline.

For one stage it: checks the stage is allowed to run, gathers the approved outputs of prior
stages, builds the prompt, asks Claude for structured output, validates it, retries with the
validation error fed back on failure, and stores the result.
"""

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import contract_for
from app.ai.llm import StructuredLLM
from app.ai.prompts import build_stage_prompt
from app.core.config import get_settings
from app.models import STAGE_ORDER, Project, Stage, StageStatus, StageType

logger = logging.getLogger(__name__)


class StageError(Exception):
    """A stage could not be run. Carries an HTTP-ish reason for the route layer to translate."""

    def __init__(self, message: str, *, conflict: bool = False) -> None:
        super().__init__(message)
        self.conflict = conflict


async def get_stage(db: AsyncSession, project_id: Any, stage_type: StageType) -> Stage:
    result = await db.execute(
        select(Stage).where(Stage.project_id == project_id, Stage.stage_type == stage_type)
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise StageError(f"Stage '{stage_type.value}' does not exist on this project")
    return stage


async def collect_prior_outputs(
    db: AsyncSession, project_id: Any, stage_type: StageType
) -> dict[str, Any]:
    """The approved output of every stage before this one, keyed by stage name.

    Raises if an earlier stage is not approved yet — that gate is the entire point of the
    human-checkpointed design: garbage must not propagate downstream.
    """
    prior: dict[str, Any] = {}
    for earlier in STAGE_ORDER[: STAGE_ORDER.index(stage_type)]:
        stage = await get_stage(db, project_id, earlier)
        if stage.status is not StageStatus.APPROVED:
            raise StageError(
                f"Stage '{earlier.value}' must be approved before '{stage_type.value}' can run",
                conflict=True,
            )
        prior[earlier.value] = stage.effective_json
    return prior


async def run_stage(
    db: AsyncSession, project: Project, stage_type: StageType, llm: StructuredLLM
) -> Stage:
    """Generates (or re-generates) one stage and stores the validated output."""
    settings = get_settings()
    stage = await get_stage(db, project.id, stage_type)

    if stage.status is StageStatus.APPROVED:
        raise StageError(
            f"Stage '{stage_type.value}' is approved and locked. Un-approve it to re-generate.",
            conflict=True,
        )

    # Workflow validity is checked before implementation availability: being blocked by an
    # unapproved earlier stage is the more useful thing to tell the user.
    prior_outputs = await collect_prior_outputs(db, project.id, stage_type)
    contract = contract_for(stage_type)
    system, user_prompt = build_stage_prompt(stage_type, project.raw_description, prior_outputs)

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
    last_error: Exception | None = None

    # Attempt 1, then up to llm_max_retries repair attempts with the error fed back to the model.
    for attempt in range(settings.llm_max_retries + 1):
        try:
            parsed = await llm.generate(
                system=system, messages=messages, output_format=contract
            )
            break
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Stage %s attempt %s failed validation: %s", stage_type.value, attempt + 1, exc
            )
            if attempt == settings.llm_max_retries:
                raise StageError(
                    f"Claude failed to produce valid output for '{stage_type.value}' after "
                    f"{attempt + 1} attempts: {last_error}"
                ) from exc
            messages = messages + [
                {"role": "assistant", "content": "I produced output that failed validation."},
                {
                    "role": "user",
                    "content": (
                        "Your previous output did not satisfy the required schema. "
                        f"The validation error was:\n\n{exc}\n\n"
                        "Return corrected output that satisfies the schema exactly."
                    ),
                },
            ]

    stage.input_snapshot = {
        "raw_description": project.raw_description,
        "prior_outputs": prior_outputs,
    }
    stage.output_json = parsed.model_dump(mode="json")
    stage.user_edited_json = None  # a fresh generation supersedes the previous edit
    stage.status = StageStatus.GENERATED
    stage.version += 1
    await db.commit()
    await db.refresh(stage)
    return stage


async def save_stage_edit(
    db: AsyncSession, project: Project, stage_type: StageType, edited: dict[str, Any]
) -> Stage:
    """Stores the user's edited version, after validating it against the same contract."""
    contract = contract_for(stage_type)
    stage = await get_stage(db, project.id, stage_type)

    if stage.status is StageStatus.APPROVED:
        raise StageError(f"Stage '{stage_type.value}' is approved and locked", conflict=True)
    if stage.output_json is None:
        raise StageError(f"Stage '{stage_type.value}' has not been generated yet", conflict=True)

    try:
        validated = contract.model_validate(edited)
    except ValidationError as exc:
        raise StageError(f"Your edit does not satisfy the stage schema: {exc}") from exc

    stage.user_edited_json = validated.model_dump(mode="json")
    stage.status = StageStatus.EDITED
    await db.commit()
    await db.refresh(stage)
    return stage


async def approve_stage(db: AsyncSession, project: Project, stage_type: StageType) -> Stage:
    """Locks a stage. Only then may the next stage run."""
    stage = await get_stage(db, project.id, stage_type)
    if stage.status is StageStatus.PENDING:
        raise StageError(f"Stage '{stage_type.value}' has nothing to approve yet", conflict=True)
    stage.status = StageStatus.APPROVED
    await db.commit()
    await db.refresh(stage)
    return stage


async def unapprove_stage(db: AsyncSession, project: Project, stage_type: StageType) -> Stage:
    """Unlocks an approved stage so it can be re-generated or edited again."""
    stage = await get_stage(db, project.id, stage_type)
    if stage.status is not StageStatus.APPROVED:
        raise StageError(f"Stage '{stage_type.value}' is not approved", conflict=True)
    stage.status = StageStatus.EDITED if stage.user_edited_json else StageStatus.GENERATED
    await db.commit()
    await db.refresh(stage)
    return stage
