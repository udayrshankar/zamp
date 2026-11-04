from fastapi import APIRouter, Request

from app.api.dependencies import get_model_health, get_model_prober
from app.core.config import settings

router = APIRouter()


@router.get("/health", tags=["Health"])
def health_check(request: Request):
    health = get_model_health(request)
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "models": [status.model_dump() for status in health.status()] if health else [],
        "panel_size": settings.LLM_PANEL_SIZE,
    }


@router.post("/health/models/check", tags=["Health"])
async def check_models(request: Request):
    """Sends a tiny request to every model and reports which ones answered."""
    prober = get_model_prober(request)
    statuses = await prober.check() if prober else []
    return {
        "models": [status.model_dump() for status in statuses],
        "panel_size": settings.LLM_PANEL_SIZE,
    }


@router.get("/", tags=["Root"])
def root():
    return {
        "message": f"{settings.APP_NAME} is running",
        "health": "/health",
        "docs": "/docs",
    }
