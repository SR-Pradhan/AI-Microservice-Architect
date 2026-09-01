"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, projects, stages
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI Microservice Architect",
    description="Staged, human-checkpointed pipeline that turns a plain-English system "
    "description into a full microservice architecture.",
    version="0.8.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(stages.router)
