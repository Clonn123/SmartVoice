from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.repository.unitofwork import get_db, SqlAlchemyUnitOfWork
from app.repository.models.models import CallTask
from app.modules.calls.service import create_call_task
from app.modules.calls.tasks import run_call_task

router = APIRouter()


class CreateCallTaskRequest(BaseModel):
    phone: str
    prompt: str | None = None
    scenario: str | None = None
    target_payload: dict | None = None
    metadata: dict | None = None
    max_attempts: int = 3


@router.post("/call-tasks")
async def create_call_task_endpoint(
    payload: CreateCallTaskRequest,
    uow: SqlAlchemyUnitOfWork = Depends(get_db),
) -> dict[str, Any]:
    """
    Создаёт новую задачу на звонок и запускает её выполнение через Celery.

    Параметры:
        payload (CreateCallTaskRequest): Данные для создания задачи (телефон, сценарий и др.).
        uow (SqlAlchemyUnitOfWork): Unit of Work для работы с БД (внедряется через Depends).

    Возвращает:
        dict[str, Any]: Словарь с полями созданной задачи, включая id, phone, status,
                        attempts, max_attempts и celery_task_id.

    Исключения:
        Может пробросить исключения, возникшие при создании задачи или запуске Celery-задачи.
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

    return {
        "id": task.id,
        "phone": task.phone,
        "status": task.status,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "celery_task_id": task.celery_task_id,
    }


@router.get("/call-tasks/{task_id}")
async def get_call_task_endpoint(
    task_id: int,
) -> dict[str, Any]:
    """
    Возвращает детальную информацию о задаче на звонок по её ID.

    Параметры:
        task_id (int): Идентификатор задачи CallTask.

    Возвращает:
        dict[str, Any]: Словарь с полным описанием задачи: id, phone, status,
                        attempts, max_attempts, last_result, completed,
                        next_attempt_at, celery_task_id.

    Исключения:
        HTTPException: 404, если задача с указанным task_id не найдена.
    """
    async with SqlAlchemyUnitOfWork() as uow:
        task = await uow.call_tasks.get(task_id)

    if not task:
        raise HTTPException(
            status_code=404,
            detail="CallTask not found",
        )

    return {
        "id": task.id,
        "phone": task.phone,
        "status": task.status,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "last_result": task.last_result,
        "completed": task.completed,
        "next_attempt_at": task.next_attempt_at,
        "celery_task_id": task.celery_task_id,
    }


@router.get("/call-tasks/{task_id}/attempts")
async def get_call_task_attempts_endpoint(
    task_id: int,
) -> dict[str, Any]:
    """
    Возвращает список попыток звонка для указанной задачи.

    Параметры:
        task_id (int): Идентификатор задачи CallTask.

    Возвращает:
        dict[str, Any]: Словарь с ключами:
            - call_task_id: идентификатор родительской задачи;
            - attempts: список словарей с деталями каждой попытки (attempt_number, status,
              result, answered, bot_finished, hangup_cause, hangup_text, started_at,
              finished_at, error).

    Исключения:
        HTTPException: 404, если задача с указанным task_id не найдена.
    """
    async with SqlAlchemyUnitOfWork() as uow:
        task = await uow.call_tasks.get(task_id)

        if not task:
            raise HTTPException(
                status_code=404,
                detail="CallTask not found",
            )

        attempts = await uow.call_attempts.list_by_call_task_id(task_id)

    return {
        "call_task_id": task.id,
        "attempts": [
            {
                "id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "status": attempt.status,
                "result": attempt.result,
                "answered": attempt.answered,
                "bot_finished": attempt.bot_finished,
                "hangup_cause": attempt.hangup_cause,
                "hangup_text": attempt.hangup_text,
                "started_at": attempt.started_at,
                "finished_at": attempt.finished_at,
                "error": attempt.error,
            }
            for attempt in attempts
        ],
    }