"""Liveness + DB connectivity probe."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Liveness, DB connectivity, and which LLM is configured. Never returns the key itself."""
    await db.execute(text("SELECT 1"))
    settings = get_settings()
    provider = settings.llm_provider
    key_set = bool(
        settings.gemini_api_key if provider == "gemini" else settings.anthropic_api_key
    )
    return {
        "status": "ok",
        "database": "ok",
        "llm_provider": provider,
        "llm_model": settings.gemini_model if provider == "gemini" else settings.anthropic_model,
        "llm_key": "set" if key_set else "missing",
    }
