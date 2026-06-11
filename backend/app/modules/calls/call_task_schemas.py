from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DialogMessageResponse(BaseModel):
    role: str
    content: str


class CallAttemptResponse(BaseModel):
    id: int
    attempt_number: int
    status: str
    result: str | None = None
    answered: bool
    bot_finished: bool
    hangup_cause: int | None = None
    hangup_text: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    dialog: list[DialogMessageResponse] | None = Field(
        default=None,
        description="История диалога, если попытка успешна",
    )
    recording_url: str | None = Field(
        default=None,
        description="Ссылка на WAV-запись, если попытка успешна",
    )


class CallTaskResponse(BaseModel):
    id: int
    phone: str
    status: str
    outcome: str = Field(
        description="Итог задачи: success | failed | in_progress",
    )
    attempts: int
    max_attempts: int
    last_result: str | None = None
    completed: bool
    next_attempt_at: datetime | None = None
    celery_task_id: str | None = None
    prompt: str | None = None
    scenario: str | None = None
    dialog: list[DialogMessageResponse] | None = Field(
        default=None,
        description="История диалога последней успешной попытки",
    )
    recording_url: str | None = Field(
        default=None,
        description="Ссылка на запись последней успешной попытки",
    )


class CallTaskAttemptsResponse(BaseModel):
    call_task_id: int
    attempts: list[CallAttemptResponse]
