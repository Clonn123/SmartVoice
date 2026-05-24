from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "smartvoice"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
