from __future__ import annotations

from fastapi import APIRouter, Query, Request

# from app.modules.calls.schemas import ProcessCallsRequest, ProcessCallsResponse
# from app.modules.calls.service import CallService

router = APIRouter(tags=["calls"])


# @router.post("/calls", response_model=ProcessCallsResponse)
# async def process_calls(payload: ProcessCallsRequest) -> ProcessCallsResponse:
#     service = CallService()
#     return await service.process(payload)


@router.post(
    '/call'
)
async def init_call(
    number: str,
    request: Request
):
    try:
        caller = request.app.state.caller
        await caller.init_call(number)
        return {"status": "calling"}
    except Exception as e:
        print(e)
