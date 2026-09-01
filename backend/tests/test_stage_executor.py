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
    assert "Your previous output was rejected" in retry_prompt
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


VALID_HLD = {
    "services": [
        {"name": "OrderService", "datastore": "PostgreSQL", "scaling_notes": "-"},
        {"name": "PaymentService", "datastore": "PostgreSQL", "scaling_notes": "-"},
    ],
    "sync_calls": [],
    "async_flows": [
        {
            "event": "order.created",
            "producer": "OrderService",
            "consumers": ["PaymentService"],
            "purpose": "start payment",
        }
    ],
    "external_dependencies": [],
    "design_notes": "-",
}


@pytest.mark.asyncio
async def test_hld_runs_once_boundaries_are_approved(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM([VALID_OUTPUT, VALID_HLD])
    await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)
    await stage_executor.approve_stage(db, project, StageType.BOUNDARIES)

    stage = await stage_executor.run_stage(db, project, StageType.HLD, llm)
    assert stage.status is StageStatus.GENERATED
    # Stage 2 must have been given Stage 1's approved output, not the raw description alone.
    assert stage.input_snapshot["prior_outputs"]["boundaries"]["services"][0]["name"] == "OrderService"


@pytest.mark.asyncio
async def test_inconsistent_hld_is_retried_then_rejected(db: AsyncSession, project: Project) -> None:
    """A schema-valid HLD that invents a service must be caught and fed back, not stored."""
    ghost = {
        **VALID_HLD,
        "services": VALID_HLD["services"] + [
            {"name": "GhostService", "datastore": "none", "scaling_notes": "-"}
        ],
    }
    llm = FakeLLM([VALID_OUTPUT, ghost, VALID_HLD])
    await stage_executor.run_stage(db, project, StageType.BOUNDARIES, llm)
    await stage_executor.approve_stage(db, project, StageType.BOUNDARIES)

    stage = await stage_executor.run_stage(db, project, StageType.HLD, llm)
    assert stage.status is StageStatus.GENERATED
    assert [s["name"] for s in stage.output_json["services"]] == ["OrderService", "PaymentService"]
    # The repair prompt must name the actual offending service.
    assert "GhostService" in llm.calls[-1][-1]["content"]


def _service_lld(name: str, published: list[str], consumed: list[str], called_by: list[str]) -> dict:
    return {
        "name": name,
        "tech_stack": "Python / FastAPI",
        "entities": [
            {
                "name": name.replace("Service", ""),
                "description": "-",
                "fields": [{"name": "id", "type": "uuid", "required": True, "description": "-"}],
            }
        ],
        "endpoints": [
            {
                "method": "GET",
                "path": f"/{name.lower()}",
                "summary": "-",
                "request_fields": [],
                "response_fields": [],
                "called_by": called_by,
            }
        ],
        "published_events": published,
        "consumed_events": consumed,
        "internal_logic_notes": "-",
    }


VALID_LLD = {
    "services": [
        _service_lld("OrderService", ["order.created"], [], ["public"]),
        _service_lld("PaymentService", [], ["order.created"], ["public"]),
    ]
}


@pytest.mark.asyncio
async def test_full_three_stage_run(db: AsyncSession, project: Project) -> None:
    """Boundaries -> HLD -> LLD, each gated on the previous being approved."""
    llm = FakeLLM([VALID_OUTPUT, VALID_HLD, VALID_LLD])
    for stage_type in (StageType.BOUNDARIES, StageType.HLD, StageType.LLD):
        stage = await stage_executor.run_stage(db, project, stage_type, llm)
        assert stage.status is StageStatus.GENERATED
        await stage_executor.approve_stage(db, project, stage_type)

    # Stage 3 must have received BOTH prior stages, not just the one immediately before it.
    lld = await stage_executor.get_stage(db, project.id, StageType.LLD)
    assert set(lld.input_snapshot["prior_outputs"]) == {"boundaries", "hld"}


def _schema(service: str, entity: str, table: str) -> dict:
    return {
        "name": service,
        "engine": "PostgreSQL",
        "tables": [
            {
                "name": table,
                "entity": entity,
                "columns": [
                    {"name": "id", "type": "UUID", "nullable": False,
                     "primary_key": True, "description": "-"}
                ],
                "indexes": [],
                "foreign_keys": [],
            }
        ],
        "notes": "-",
    }


VALID_DB_SCHEMA = {
    "services": [
        _schema("OrderService", "Order", "orders"),
        _schema("PaymentService", "Payment", "payments"),
    ]
}

VALID_KAFKA = {
    "topics": [
        {
            "name": "order.created",
            "producer": "OrderService",
            "consumers": [
                {"service": "PaymentService", "consumer_group": "payment-group", "purpose": "-"}
            ],
            "partition_key": "orderId",
            "partitions": 6,
            "retention": "7 days",
            "payload_fields": [
                {"name": "orderId", "type": "uuid", "required": True, "description": "-"}
            ],
            "ordering_notes": "-",
        }
    ],
    "dead_letter_strategy": "-",
    "schema_evolution_notes": "-",
}

def _infra_service(name: str, port: int) -> dict:
    return {
        "name": name, "base_image": "python:3.12-slim", "build_steps": ["COPY . ."],
        "start_command": "python main.py", "port": port, "health_check_path": "/health",
        "env_vars": [], "replicas": 1, "cpu_request": "100m", "cpu_limit": "500m",
        "memory_request": "256Mi", "memory_limit": "512Mi",
        "depends_on": ["postgres", "kafka"],
    }


VALID_INFRA = {
    "services": [_infra_service("OrderService", 8081), _infra_service("PaymentService", 8082)],
    "infra_components": [
        {"name": "postgres", "image": "postgres:16-alpine", "port": 5432,
         "used_by": ["OrderService", "PaymentService"]},
        {"name": "kafka", "image": "bitnami/kafka:3.7", "port": 9092,
         "used_by": ["OrderService", "PaymentService"]},
    ],
    "notes": "-",
}

IMPLEMENTED = STAGE_ORDER
SCRIPT = [VALID_OUTPUT, VALID_HLD, VALID_LLD, VALID_DB_SCHEMA, VALID_KAFKA, VALID_INFRA]


@pytest.mark.asyncio
async def test_all_implemented_stages_run_in_order(db: AsyncSession, project: Project) -> None:
    llm = FakeLLM(list(SCRIPT))
    for stage_type in IMPLEMENTED:
        stage = await stage_executor.run_stage(db, project, stage_type, llm)
        assert stage.status is StageStatus.GENERATED
        await stage_executor.approve_stage(db, project, stage_type)

    # The last stage must receive every earlier stage, not just the one before it.
    infra = await stage_executor.get_stage(db, project.id, StageType.INFRA)
    assert set(infra.input_snapshot["prior_outputs"]) == {
        "boundaries", "hld", "lld", "db_schema", "kafka_events"
    }


@pytest.mark.asyncio
async def test_every_stage_is_implemented(db: AsyncSession, project: Project) -> None:
    """All six stages now have a contract and a prompt — nothing returns 501 any more."""
    from app.ai.contracts import STAGE_CONTRACTS
    from app.ai.prompts import STAGE_INSTRUCTIONS

    assert set(STAGE_CONTRACTS) == set(STAGE_ORDER)
    assert set(STAGE_INSTRUCTIONS) == set(STAGE_ORDER)
