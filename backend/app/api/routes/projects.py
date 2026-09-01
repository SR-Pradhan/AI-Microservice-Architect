"""CRUD for architecture projects. No AI here yet — that lands in v0.2.0."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import STAGE_ORDER, Project, Stage, StageStatus
from app.services import export
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> Project:
    """Creates the project and seeds all six stages as 'pending'."""
    project = Project(name=payload.name, raw_description=payload.raw_description)
    project.stages = [
        Stage(stage_type=stage_type, status=StageStatus.PENDING, version=0)
        for stage_type in STAGE_ORDER
    ]
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Project:
    return await _get_project_or_404(db, project_id)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)
) -> Project:
    project = await _get_project_or_404(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}/export")
async def export_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    """Downloads the whole scaffold as a zip: Dockerfiles, compose, k8s manifests, docs, diagrams.

    Exports what each stage *effectively* holds — the user's edit if there is one — and refuses if
    nothing has been generated at all.
    """
    project = await _get_project_or_404(db, project_id)
    stages = {
        stage.stage_type.value: stage.effective_json
        for stage in project.stages
        if stage.effective_json is not None
    }
    if not stages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nothing to export — no stage has been generated yet",
        )

    archive = export.build_export(project.name, project.raw_description, stages)
    filename = f"{export.kebab(project.name)}-scaffold.zip"
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    project = await _get_project_or_404(db, project_id)
    await db.delete(project)
    await db.commit()
