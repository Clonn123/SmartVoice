from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.modules.calls.call_task_ops import (
    build_recording_url,
    create_call_task,
    is_success_result,
    resolve_task_outcome,
    serialize_dialog,
)
from app.modules.calls.call_task_schemas import (
    CallAttemptResponse,
    CallTaskAttemptsResponse,
    CallTaskResponse,
    DialogMessageResponse,
)
from app.modules.calls.tasks import run_call_task
from app.repository.models.models import CallAttempt
from app.repository.unitofwork import SqlAlchemyUnitOfWork, get_db

router = APIRouter()


class CreateCallTaskRequest(BaseModel):
    phone: str
    prompt: str | None = None
    scenario: str | None = None
    target_payload: dict | None = None
    metadata: dict | None = None
    max_attempts: int = 3


class CreateCallTaskResponse(BaseModel):
    id: int
    phone: str
    status: str
    attempts: int
    max_attempts: int
    celery_task_id: str | None = None


def _build_attempt_response(attempt: CallAttempt) -> CallAttemptResponse:
    include_details = is_success_result(attempt.result)

    return CallAttemptResponse(
        id=attempt.id,
        attempt_number=attempt.attempt_number,
        status=attempt.status,
        result=attempt.result,
        answered=attempt.answered,
        bot_finished=attempt.bot_finished,
        hangup_cause=attempt.hangup_cause,
        hangup_text=attempt.hangup_text,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        error=attempt.error,
        dialog=(
            [
                DialogMessageResponse(**message)
                for message in serialize_dialog(attempt.dialog_json)
            ]
            if include_details
            else None
        ),
        recording_url=(
            build_recording_url(attempt.recording_path) if include_details else None
        ),
    )


def _find_success_attempt(attempts: list[CallAttempt]) -> CallAttempt | None:
    for attempt in reversed(attempts):
        if is_success_result(attempt.result):
            return attempt

    return None


@router.post("/call-tasks", response_model=CreateCallTaskResponse)
async def create_call_task_endpoint(
    payload: CreateCallTaskRequest,
    uow: SqlAlchemyUnitOfWork = Depends(get_db),
    
) -> CreateCallTaskResponse:
    """
    Создаёт новую задачу на звонок и запускает её выполнение через Celery
    """
    task = await create_call_task(
        phone=payload.phone,
        prompt=payload.prompt,
        scenario=payload.scenario,
        target_payload=payload.target_payload,
        metadata=payload.metadata,
        max_attempts=payload.max_attempts,
    )

    celery_result = run_call_task.delay(task.id)
    task.celery_task_id = celery_result.id

    return CreateCallTaskResponse(
        id=task.id,
        phone=task.phone,
        status=task.status,
        attempts=task.attempts,
        max_attempts=task.max_attempts,
        celery_task_id=task.celery_task_id,
    )


@router.get("/call-tasks/{task_id}", response_model=CallTaskResponse)
async def get_call_task_endpoint(task_id: int) -> CallTaskResponse:
    """
    Возвращает детальную информацию о задаче на звонок по её ID
    """
    async with SqlAlchemyUnitOfWork() as uow:
        task = await uow.call_tasks.get(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="CallTask not found")

        attempts = await uow.call_attempts.list_by_call_task_id(task_id)

    outcome = resolve_task_outcome(task)
    success_attempt = _find_success_attempt(attempts)

    dialog = None
    recording_url = None

    if outcome == "success" and success_attempt:
        dialog = [
            DialogMessageResponse(**message)
            for message in serialize_dialog(success_attempt.dialog_json)
        ]
        recording_url = build_recording_url(success_attempt.recording_path)

    return CallTaskResponse(
        id=task.id,
        phone=task.phone,
        status=task.status,
        outcome=outcome,
        attempts=task.attempts,
        max_attempts=task.max_attempts,
        last_result=task.last_result,
        completed=task.completed,
        next_attempt_at=task.next_attempt_at,
        celery_task_id=task.celery_task_id,
        prompt=task.prompt,
        scenario=task.scenario,
        dialog=dialog,
        recording_url=recording_url,
    )


@router.get("/call-tasks/{task_id}/attempts", response_model=CallTaskAttemptsResponse)
async def get_call_task_attempts_endpoint(task_id: int) -> CallTaskAttemptsResponse:
    """
    Возвращает список попыток звонка для указанной задачи
    """
    async with SqlAlchemyUnitOfWork() as uow:
        task = await uow.call_tasks.get(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="CallTask not found")

        attempts = await uow.call_attempts.list_by_call_task_id(task_id)

    return CallTaskAttemptsResponse(
        call_task_id=task.id,
        attempts=[_build_attempt_response(attempt) for attempt in attempts],
    )


@router.get("/recordings/{filename}")
async def download_recording(filename: str) -> FileResponse:
    """
    Позволяет скачать запись разговора по названию файла
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid recording filename")

    if not filename.lower().endswith(".wav"):
        filename = f"{filename}.wav"

    settings = get_settings()
    recording_path = (settings.recordings_dir / filename).resolve()
    recordings_root = settings.recordings_dir.resolve()

    if not recording_path.is_file() or recordings_root not in recording_path.parents:
        raise HTTPException(status_code=404, detail="Recording not found")

    return FileResponse(
        path=recording_path,
        media_type="audio/wav",
        filename=filename,
    )
