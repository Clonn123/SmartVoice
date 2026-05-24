from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, AnyUrl, BaseModel, ConfigDict, Field

from app.core.enums import CallAttemptStatus, CallJobStatus, CallResult, CallStatus, DialogSpeaker


class CallTargetInput(BaseModel):
    """Данные клиента для проведения звонка."""
    model_config = ConfigDict(populate_by_name=True)

    phone_number: str = Field(
        ...,
        min_length=3,
        max_length=32,
        validation_alias=AliasChoices("phone_number", "phone"),
        description="Номер телефона клиента (обязательно). Пример: +79990000000 или 89990000000",
    )
    client_name: str | None = Field(
        default=None,
        max_length=255,
        validation_alias=AliasChoices("client_name", "name"),
        description="Имя клиента (опционально). Используется в диалоге для персонализации. Пример: Иван Петров",
    )
    external_id: str | None = Field(
        default=None,
        max_length=255,
        description="Внешний ID клиента из вашей системы (опционально). Пример: CRM-12345",
    )
    contract_id: str | None = Field(
        default=None,
        max_length=255,
        description="Номер договора (опционально, но рекомендуется). Используется в контексте разговора. Пример: CTR-2024-001",
    )
    contract_type: str | None = Field(
        default=None,
        max_length=255,
        description="Тип договора (опционально). Пример: кредит, подписка, страховка",
    )
    contract_status: str | None = Field(
        default=None,
        max_length=255,
        description="Статус договора (опционально). Пример: просрочен, активен, истекает_через_3_дня",
    )
    call_type: str | None = Field(
        default=None,
        max_length=100,
        description="Тип звонка (опционально). Пример: напомнение, опрос. Влияет на контекст для LLM.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные данные клиента в формате JSON (опционально). Будут передано в контекст LLM. Пример: {\"last_purchase\": \"2024-05-10\"}",
    )


class ProcessCallsRequest(BaseModel):
    """Запрос на проведение обзвона клиентов."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prompt": "Напомни клиенту о договоре и спроси, помнит ли он о задолженности. Скажи, что звонишь только напомнить, больше ничего не требуется.",
                    "scenario": "contract_reminder",
                    "clients": [
                        {
                            "phone_number": "+79990000000",
                            "client_name": "Полозников Артем",
                            "contract_id": "CLON-123",
                            "contract_type": "кредит",
                            "contract_status": "просрочен",
                            "external_id": "CRM-12345",
                        }
                    ],
                    "max_attempts": 1,
                    "metadata": {},
                }
            ]
        }
    )
    
    prompt: str = Field(
        ...,
        min_length=1,
        description="Основной промпт/сценарий для ИИ (обязательно). Описывает, что должен сказать бот и какую информацию собрать. Пример: 'Напомни клиенту о договоре и спроси, помнит ли он о задолженности.'",
    )
    clients: list[CallTargetInput] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Список клиентов для обзвона (обязательно). Минимум 1, максимум 500 клиентов за один запрос.",
    )
    scenario: str = Field(
        default="contract_reminder",
        min_length=1,
        max_length=100,
        description="Сценарий звонка (опционально, по умолчанию 'contract_reminder'). Влияет на контекст для LLM. Пример: contract_reminder, survey, followup",
    )
    callback_url: AnyUrl | None = Field(
        default=None,
        description="URL для вебхука, на который система отправит результаты звонков (опционально). Пример: https://example.com/callbacks/calls",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные метаданные для сохранения и отслеживания (опционально). Пример: {\"campaign_id\": \"2024-05-17-promo\", \"source\": \"crm\"}",
    )
    max_attempts: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Максимальное количество попыток дозвона при недозвоне (опционально). От 1 до 3. По умолчанию 1 попытка.",
    )


class DialogTurnResponse(BaseModel):
    speaker: DialogSpeaker
    text: str


class CallAttemptResponse(BaseModel):
    attempt_number: int
    status: CallAttemptStatus
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: int | None
    error_message: str | None


class ProcessedCallResult(BaseModel):
    call_id: str
    external_id: str | None
    contract_id: str | None
    phone: str
    client_name: str | None
    call_status: CallStatus
    result: CallResult
    attempts: list[CallAttemptResponse]
    dialog: list[DialogTurnResponse]
    transcription: str | None
    summary: str | None
    recording_url: str | None
    payload: dict[str, Any]
    result_payload: dict[str, Any]
    error_message: str | None = None


class ProcessCallsResponse(BaseModel):
    job_id: str
    status: CallJobStatus
    scenario: str
    calls_count: int
    processed_at: datetime
    metadata: dict[str, Any]
    results: list[ProcessedCallResult]

