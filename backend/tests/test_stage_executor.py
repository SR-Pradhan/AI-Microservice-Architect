"""Stage Executor tests.

These use a fake LLM, so they run without an API key and cost nothing. They cover the parts that
are easy to get wrong: the approval gate, the retry-with-error-feedback loop, and edit validation.
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.contracts import BoundariesOutput
from app.db.base import Base
from app.models import STAGE_ORDER, Project, Stage, StageStatus, StageType
from app.services import stage_executor
from app.services.stage_executor import StageError

TEST_DB_URL = "postgresql+asyncpg://architect:architect@localhost:5434/architect_test"

VALID_OUTPUT = {
    "services": [
        {
            "name": "OrderService",
            "responsibility": "Owns order lifecycle.",
            "domain": "Orders",
            "key_entities": ["Order"],
        },
        {
            "name": "PaymentService",
            "responsibility": "Owns payments.",
            "domain": "Payments",
            "key_entities": ["Payment"],
        },
    ],
    "boundaries_rationale": "Split by data ownership.",
}


class FakeLLM:
    """Replays a scripted list of results. An Exception in the list is raised instead of returned."""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.calls: list[list[dict[str, Any]]] = []

    async def generate(self, *, system: str, messages: list[dict[str, Any]], output_format: type[BaseModel]):
        self.calls.append(messages)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return output_format.model_validate(result)


def _validation_error() -> ValidationError:
    try:
        BoundariesOutput.model_validate({"services": [], "boundaries_rationale": "x"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = Project(name="Shop", raw_description="An online shop with orders and payments.")
    p.stages = [Stage(stage_type=t, status=StageStatus.PENDING, version=0) for t in STAGE_ORDER]
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest.mark.asyncio
async def test_run_stage_stores_validated_output(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([VALID_OUTPUT])
    stage = await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)

    assert stage.status is StageStatus.GENERATED
    assert stage.version == 1
    assert stage.output_json is not None
    assert [s["name"] for s in stage.output_json["services"]] == ["OrderService", "PaymentService"]
    # The input snapshot is the audit trail of what the model was actually given.
    assert stage.input_snapshot["raw_description"] == project.raw_description
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_retry_feeds_the_validation_error_back(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([_validation_error(), VALID_OUTPUT])
    stage = await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)

    assert stage.status is StageStatus.GENERATED
    assert len(llm.calls) == 2
    # The second attempt must actually contain the error text, not just be a blind re-ask.
    retry_prompt = llm.calls[1][-1]["content"]
    assert "did not satisfy the required schema" in retry_prompt
    assert "services" in retry_prompt


@pytest.mark.asyncio
async def test_gives_up_after_max_retries(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([_validation_error() for _ in range(3)])
    with pytest.raises(StageError, match="after 3 attempts"):
        await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)
    assert len(llm.calls) == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_later_stage_blocked_until_prior_approved(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([VALID_OUTPUT])
    with pytest.raises(StageError, match="must be approved"):
        await stage_executor.run_stage(db, project, StageType.HLD, llm)
    assert llm.calls == []  # no money spent on a call that was never allowed


@pytest.mark.asyncio
async def test_approved_stage_is_locked(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([VALID_OUTPUT, VALID_OUTPUT])
    await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)
    await stage_executor.approve_stage(db, project, StageType.BOUNDARIES)

    with pytest.raises(StageError, match="approved and locked"):
        await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)

    # Un-approving unlocks it again.
    stage = await stage_executor.unapprove_stage(db, project, StageType.BOUNDARIES)
    assert stage.status is StageStatus.GENERATED


@pytest.mark.asyncio
async def test_edit_is_validated_against_the_contract(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([VALID_OUTPUT])
    await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)

    edited = {**VALID_OUTPUT, "boundaries_rationale": "I renamed a service."}
    edited["services"] = [{**edited["services"][0], "name": "OrdersService"}, edited["services"][1]]
    stage = await stage_executor.save_stage_edit(db, project, StageType.BOUNDARIES, edited)
    assert stage.status is StageStatus.EDITED
    assert stage.user_edited_json["services"][0]["name"] == "OrdersService"
    assert stage.output_json["services"][0]["name"] == "OrderService"  # original preserved
    assert stage.effective_json == stage.user_edited_json  # downstream sees the edit

    with pytest.raises(StageError, match="does not satisfy the stage schema"):
        await stage_executor.save_stage_edit(db, project, StageType.BOUNDARIES, {"nonsense": 1})


@pytest.mark.asyncio
async def test_unimplemented_stage_reports_clearly(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([VALID_OUTPUT])
    await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)
    await stage_executor.approve_stage(db, project, StageType.BOUNDARIES)
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        await stage_executor.run_stage(db, project, StageType.HLD, llm)
