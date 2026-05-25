from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "smartvoice"}


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    app = request.app
    vosk_ready = getattr(app.state, "vosk_ready", None)
    llm_ready = getattr(app.state, "llm_ready", None)
    return {"status": "ok", "vosk_ready": vosk_ready, "llm_ready": llm_ready}
