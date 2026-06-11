from __future__ import annotations

from typing import Any, Iterable

from app.modules.llm.base import CallMessage, LlmCallContext

DEFAULT_REALTIME_PROMPT = "Напомни клиенту о договоре и спроси его, помнит ли он о нём. Скажи, что звонишь только напомнить о задолжности, больше не нужно ничего."
DEFAULT_REALTIME_SCENARIO = "realtime_call"
FINAL_MARKER = "FINAL"


def build_call_context(
    prompt: str,
    scenario: str,
    target: dict[str, Any],
    history: Iterable[CallMessage] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> LlmCallContext:
    return LlmCallContext(
        prompt=prompt,
        scenario=scenario,
        target=target,
        history=list(history or []),
        extra_context=extra_context or {},
    )


def build_default_realtime_target(phone_number: str) -> dict[str, Any]:
    return {
        "phone_number": phone_number,
        "client_name": None,
        "call_type": "realtime_call",
    }


def build_openrouter_messages(context: LlmCallContext) -> list[dict[str, str]]:
    system_message = f"""Ты человек, занимающийся обзвоном по сценарию "{context.scenario}".

Описание сценария:
{context.prompt}

Данные клиента:
{context.target}

=== ПРАВИЛА ОТВЕТА (ОБЯЗАТЕЛЬНЫ!) ===

1. Выводи ТОЛЬКО готовый ответ для клиента, ничего больше
2. БЕЗ рассуждений, объяснений, размышлений о стратегии
3. БЕЗ анализа ситуации или описания своих мыслей
4. БЕЗ примечаний, комментариев, пояснений
5. Только текст, который ты будешь говорить клиенту

НЕПРАВИЛЬНО:
"Нужно учесть, что клиент выразил недовольство... Я думаю, лучше ответить так-то... Согласно инструкции... Оптимальный вариант ответа: Привет!"

ПРАВИЛЬНО:
"Привет! Чем я могу вам помочь?"

=== ЗАДАЧА ===
Вести естественный и вежливый диалог, следуя сценарию.
Собирать информацию от клиента кратко (1-2 предложения за раз).
Завершить звонок, когда:
- Получена нужная информация
- Клиент выразил нежелание продолжать
- Достигнута цель звонка

При завершении звонка скажи "До свидания!" или "Спасибо и до встречи!"

Если разговор нужно завершить, допиши в самом конце отдельной строкой слово FINAL.
Перед FINAL обязательно должна быть последняя фраза для клиента.
После слова FINAL не добавляй ничего.

Отвечай максимум 1-2 предложениями."""

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_message},
    ]

    for msg in context.history:
        if msg.role == "bot":
            messages.append({"role": "assistant", "content": msg.content})
        elif msg.role == "client":
            messages.append({"role": "user", "content": msg.content})

    return messages
