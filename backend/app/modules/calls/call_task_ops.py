from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.repository.models.models import (
    CallAttempt,
    CallAttemptResult,
    CallTask,
    CallTaskStatus,
)
from app.repository.unitofwork import SqlAlchemyUnitOfWork

SUCCESS_RESULTS = {
    CallAttemptResult.SUCCESS,
    CallAttemptResult.BOT_FINISHED,
    CallAttemptResult.ANSWERED,
}

RETRYABLE_RESULTS = {
    CallAttemptResult.NO_ANSWER,
    CallAttemptResult.BUSY,
    CallAttemptResult.REJECTED,
    CallAttemptResult.FAILED,
    CallAttemptResult.ERROR,
}


def is_success_result(result: str | CallAttemptResult | None) -> bool:
    if result is None:
        return False

    if isinstance(result, CallAttemptResult):
        return result in SUCCESS_RESULTS

    return result in {item.value for item in SUCCESS_RESULTS}


async def create_call_task(
    phone: str,
    prompt: str | None = None,
    scenario: str | None = None,
    target_payload: dict | None = None,
    metadata: dict | None = None,
    max_attempts: int = 3,
) -> CallTask:
    task = CallTask(
        phone=phone,
        prompt=prompt,
        scenario=scenario,
        target_payload=target_payload,
        metadata_json=metadata or {},
        max_attempts=max_attempts,
        attempts=0,
        status=CallTaskStatus.PENDING,
        next_attempt_at=datetime.utcnow(),
        completed=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    async with SqlAlchemyUnitOfWork() as uow:
        await uow.call_tasks.add(task)

    return task


async def create_attempt(
    call_task: CallTask,
    celery_task_id: str | None = None,
) -> CallAttempt:
    attempt_number = call_task.attempts + 1

    attempt = CallAttempt(
        call_task_id=call_task.id,
        attempt_number=attempt_number,
        celery_task_id=celery_task_id,
        status="RUNNING",
        started_at=datetime.utcnow(),
    )

    call_task.attempts = attempt_number
    call_task.status = CallTaskStatus.RUNNING
    call_task.updated_at = datetime.utcnow()

    async with SqlAlchemyUnitOfWork() as uow:
        await uow.call_attempts.add(attempt)

    return attempt


async def finish_attempt(
    attempt: CallAttempt,
    result: CallAttemptResult,
    *,
    answered: bool = False,
    bot_finished: bool = False,
    channel_id: str | None = None,
    hangup_cause: int | None = None,
    hangup_text: str | None = None,
    error: str | None = None,
    dialog: list[dict[str, str]] | None = None,
    recording_path: str | None = None,
) -> CallAttempt:
    attempt.status = "FINISHED"
    attempt.result = result.value
    attempt.answered = answered
    attempt.bot_finished = bot_finished
    attempt.channel_id = channel_id
    attempt.hangup_cause = hangup_cause
    attempt.hangup_text = hangup_text
    attempt.error = error
    attempt.dialog_json = dialog or []
    attempt.recording_path = recording_path
    attempt.finished_at = datetime.utcnow()

    return attempt


async def update_call_task_after_attempt(
    call_task: CallTask,
    attempt: CallAttempt,
    retry_delay_seconds: int = 900,
) -> CallTask:
    result = CallAttemptResult(attempt.result)

    call_task.last_result = attempt.result
    call_task.updated_at = datetime.utcnow()

    if result in SUCCESS_RESULTS:
        call_task.status = CallTaskStatus.COMPLETED
        call_task.completed = True
        call_task.next_attempt_at = None

    elif call_task.attempts >= call_task.max_attempts:
        call_task.status = CallTaskStatus.FAILED
        call_task.completed = True
        call_task.next_attempt_at = None

    elif result in RETRYABLE_RESULTS:
        call_task.status = CallTaskStatus.RETRY_WAIT
        call_task.completed = False
        call_task.next_attempt_at = datetime.utcnow() + timedelta(
            seconds=retry_delay_seconds
        )

    else:
        call_task.status = CallTaskStatus.FAILED
        call_task.completed = True
        call_task.next_attempt_at = None

    return call_task


def resolve_result_from_hangup(
    *,
    answered: bool,
    bot_finished: bool,
    hangup_cause: int | None,
) -> CallAttemptResult:
    if bot_finished:
        return CallAttemptResult.BOT_FINISHED

    if answered:
        return CallAttemptResult.ANSWERED

    if hangup_cause == 17:
        return CallAttemptResult.BUSY

    if hangup_cause in {18, 19}:
        return CallAttemptResult.NO_ANSWER

    if hangup_cause == 21:
        return CallAttemptResult.REJECTED

    return CallAttemptResult.FAILED


def serialize_dialog(dialog: list[dict[str, Any]] | list[Any] | None) -> list[dict[str, str]]:
    if not dialog:
        return []

    serialized: list[dict[str, str]] = []

    for item in dialog:
        if isinstance(item, dict):
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
        else:
            role = str(getattr(item, "role", "")).strip()
            content = str(getattr(item, "content", "")).strip()

        if role and content:
            serialized.append({"role": role, "content": content})

    return serialized


def build_recording_url(recording_path: str | None) -> str | None:
    if not recording_path:
        return None

    filename = recording_path.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename:
        return None

    if filename.lower().endswith(".wav"):
        filename = filename[:-4]

    return filename


def resolve_task_outcome(task: CallTask) -> str:
    if not task.completed:
        return "in_progress"

    if is_success_result(task.last_result):
        return "success"

    return "failed"
