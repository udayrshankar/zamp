from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }


@router.get("/", tags=["Root"])
def root():
    return {
        "message": f"{settings.APP_NAME} is running",
        "health": "/health",
        "docs": "/docs",
    }
