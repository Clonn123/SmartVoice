"""Роуты для тестирования диалога с LLM."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.modules.calls.schemas import CallTargetInput
from app.modules.calls.service import CallService
from app.modules.llm.base import CallMessage, LlmCallContext

router = APIRouter(tags=["dialog"])


class DialogMessage(BaseModel):
    """Одно сообщение в диалоге."""
    role: str = Field(..., description="Роль: 'bot' или 'client'")
    content: str = Field(..., description="Текст сообщения")


class DialogRequest(BaseModel):
    """Запрос для диалога с LLM."""
    prompt: str = Field(
        ...,
        description="Основной промпт/сценарий для ИИ",
    )
    scenario: str = Field(
        default="contract_reminder",
        description="Сценарий звонка",
    )
    client_message: str | None = Field(
        default=None,
        description="Сообщение от клиента (если None, генерируется первое сообщение бота)",
    )
    history: list[DialogMessage] = Field(
        default_factory=list,
        description="История диалога (сообщения bot и client)",
    )
    target: CallTargetInput = Field(
        ...,
        description="Данные клиента",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные метаданные",
    )


class DialogResponse(BaseModel):
    """Ответ с сообщением бота."""
    bot_message: str = Field(..., description="Ответ бота")
    finish_call: bool = Field(..., description="Должен ли завершиться звонок")
    history: list[DialogMessage] = Field(
        ...,
        description="Обновленная история диалога",
    )


@router.post("/dialog", response_model=DialogResponse)
async def dialog(request: DialogRequest) -> DialogResponse:
    """
    Диалог с LLM для тестирования.
    
    Если `client_message` не передан или None → генерируется первое сообщение бота.
    Если `client_message` передан → добавляется в историю и генерируется ответ бота.
    
    Пример 1 (первое сообщение):
    ```json
    {
        "prompt": "Напомни клиенту о договоре",
        "scenario": "contract_reminder",
        "target": {
            "phone_number": "+79990000000",
            "client_name": "Иван Петров",
            "contract_id": "CTR-2024-001",
            "contract_type": "кредит",
            "contract_status": "просрочен"
        }
    }
    ```
    
    Пример 2 (продолжение):
    ```json
    {
        "prompt": "Напомни клиенту о договоре",
        "scenario": "contract_reminder",
        "client_message": "Здравствуйте, я помню о договоре",
        "history": [
            {"role": "bot", "content": "Здравствуйте, это звонок из банка..."}
        ],
        "target": {
            "phone_number": "+79990000000",
            "client_name": "Иван Петров",
            "contract_id": "CTR-2024-001",
            "contract_type": "кредит",
            "contract_status": "просрочен"
        }
    }
    ```
    """
    service = CallService()
    
    # Собираем историю сообщений из переданного массива
    call_history: list[CallMessage] = [
        CallMessage(role=msg.role, content=msg.content)
        for msg in request.history
    ]
    
    # Если передано сообщение клиента, добавляем его в историю
    if request.client_message:
        call_history.append(CallMessage(role="client", content=request.client_message))
    
    # Подготавливаем данные клиента
    target_payload = {
        "phone_number": request.target.phone_number,
        "client_name": request.target.client_name or "Клиент",
        "contract_id": request.target.contract_id,
        "contract_type": request.target.contract_type,
        "contract_status": request.target.contract_status,
        "external_id": request.target.external_id,
        **(request.target.payload or {}),  # Добавляем дополнительные данные
    }
    
    # Строим контекст для LLM
    context = LlmCallContext(
        prompt=request.prompt,
        scenario=request.scenario,
        target=target_payload,
        history=call_history,
        extra_context=request.metadata,
    )
    
    # Генерируем ответ от LLM
    reply = await service.llm.generate_reply(context)
    
    # Добавляем ответ бота в историю
    updated_history = [DialogMessage(role=msg.role, content=msg.content) for msg in call_history]
    updated_history.append(DialogMessage(role="bot", content=reply.message))
    
    return DialogResponse(
        bot_message=reply.message,
        finish_call=reply.finish_call,
        history=updated_history,
    )
