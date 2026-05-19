from __future__ import annotations

from fastapi import APIRouter

from app.modules.calls.schemas import ProcessCallsRequest, ProcessCallsResponse
from app.modules.calls.service import CallService

router = APIRouter(tags=["calls"])


@router.post("/calls", response_model=ProcessCallsResponse)
async def process_calls(payload: ProcessCallsRequest) -> ProcessCallsResponse:
    service = CallService()
    return await service.process(payload)
