from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import process

api_router = APIRouter()
# api_router.include_router(health.router)
api_router.include_router(process.router, prefix="/api/v1")
# api_router.include_router(dialog.router, prefix="/api/v1")
