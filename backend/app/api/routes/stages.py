"""Stage endpoints: run a stage, save edits, approve / un-approve."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import MissingAPIKeyError, StructuredLLM, get_llm
from app.db.session import get_db
from app.models import Project, StageType
from app.schemas.project import StageRead, StageUpdate
from app.services import diagram, stage_executor
from app.services.stage_executor import StageError

router = APIRouter(prefix="/projects/{project_id}/stages", tags=["stages"])



async def _get_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _translate(exc: StageError) -> HTTPException:
    """A blocked-by-workflow error is a 409; a bad payload or failed generation is a 400."""
    code = status.HTTP_409_CONFLICT if exc.conflict else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc))


@router.post("/{stage_type}/run", response_model=StageRead)
async def run_stage(
    project_id: uuid.UUID,
    stage_type: StageType,
    db: AsyncSession = Depends(get_db),
    llm: StructuredLLM = Depends(get_llm),
) -> object:
    project = await _get_project(db, project_id)
    try:
        return await stage_executor.run_stage(db, project, stage_type, llm)
    except MissingAPIKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except StageError as exc:
        raise _translate(exc) from exc


@router.get("/{stage_type}/diagram")
async def stage_diagram(
    project_id: uuid.UUID, stage_type: StageType, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """Mermaid source for this stage's output, rendered by the frontend."""
    await _get_project(db, project_id)
    try:
        stage = await stage_executor.get_stage(db, project_id, stage_type)
    except StageError as exc:
        raise _translate(exc) from exc
    if stage.effective_json is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stage '{stage_type.value}' has not been generated yet",
        )
    try:
        return {"mermaid": diagram.render_stage(stage_type, stage.effective_json)}
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.put("/{stage_type}", response_model=StageRead)
async def save_stage_edit(
    project_id: uuid.UUID,
    stage_type: StageType,
    payload: StageUpdate,
    db: AsyncSession = Depends(get_db),
) -> object:
    project = await _get_project(db, project_id)
    try:
        return await stage_executor.save_stage_edit(db, project, stage_type, payload.output_json)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except StageError as exc:
        raise _translate(exc) from exc


@router.post("/{stage_type}/approve", response_model=StageRead)
async def approve_stage(
    project_id: uuid.UUID, stage_type: StageType, db: AsyncSession = Depends(get_db)
) -> object:
    project = await _get_project(db, project_id)
    try:
        return await stage_executor.approve_stage(db, project, stage_type)
    except StageError as exc:
        raise _translate(exc) from exc


@router.post("/{stage_type}/unapprove", response_model=StageRead)
async def unapprove_stage(
    project_id: uuid.UUID, stage_type: StageType, db: AsyncSession = Depends(get_db)
) -> object:
    project = await _get_project(db, project_id)
    try:
        return await stage_executor.unapprove_stage(db, project, stage_type)
    except StageError as exc:
        raise _translate(exc) from exc
