"""
Сценарий быстрого тестирования провайдера OpenRouter.
Использование: python test_openrouter.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.modules.llm.base import CallMessage, LlmCallContext
from app.modules.llm.factory import get_llm_gateway


async def test_openrouter() -> None:
    settings = get_settings()
    
    print(f"LLM Provider: {settings.llm_provider}")
    print(f"LLM Model: {settings.llm_model or settings.llm_openrouter_model}")
    print(f"Timeout: {settings.llm_timeout_seconds}s")
    print()
    
    if settings.llm_provider != "openrouter":
        print("LLM_PROVIDER не установлен в 'openrouter'")
        print("   Обновите файл .env:")
        print("   LLM_PROVIDER=openrouter")
        print("   LLM_OPENROUTER_API_KEY=sk-or-...")
        print("   LLM_OPENROUTER_MODEL=meta-llama/llama-2-70b-chat")
        return
    
    if not settings.llm_openrouter_api_key:
        print("LLM_OPENROUTER_API_KEY не установлен")
        print("   1. Получите API ключ на https://openrouter.ai/keys")
        print("   2. Добавьте в .env:")
        print("   LLM_OPENROUTER_API_KEY=sk-or-...")
        return
    
    print("✓ Конфигурация выглядит корректной")
    print()
    
    # Создаём тестовый контекст
    context = LlmCallContext(
        prompt="Напомни клиенту о договоре и спроси его, помнит ли он о нём. Скажи, что звонишь только напомнить о задолжности, больше не нужно ничего.",
        scenario="contract_reminder",
        target={
            "call_id": "test-123",
            "phone_number": "+79990000000",
            "client_name": "Артем Полозников",
            "contract_id": "CLON-123",
            "contract_type": "loan",
            "contract_status": "overdue",
        },
        history=[],
    )
    
    print("Тестирование generate_reply (открывающее сообщение)...")
    print("-" * 50)
    
    try:
        llm = get_llm_gateway()
        reply = await llm.generate_reply(context)
        
        print(f"✓ Ответ: {reply.message}")
        print(f"  Завершить звонок: {reply.finish_call}")
        print(f"  Провайдер: {reply.raw_payload.get('provider')}")
        print(f"  Модель: {reply.raw_payload.get('model')}")
        usage = reply.raw_payload.get('usage', {})
        print(f"  Использовано токенов: {usage.get('total_tokens', '?')}")
        print()
        
        # Проверяем ответ с историей диалога
        print("Тестирование generate_reply (с ответом клиента)...")
        print("-" * 50)
        context = LlmCallContext(
            prompt=context.prompt,
            scenario=context.scenario,
            target=context.target,
            history=[
                CallMessage(role="bot", content=reply.message),
                CallMessage(role="client", content="Да, помню про договор"),
            ],
        )
        
        reply2 = await llm.generate_reply(context)
        print(f"✓ Ответ: {reply2.message}")
        print(f"  Использовано токенов: {reply2.raw_payload.get('usage', {}).get('total_tokens', '?')}")
        print()
        
        # Проверяем создание резюме
        print("Тестирование создания резюме...")
        print("-" * 50)
        
        transcript = "bot: Здравствуйте, Иван. Я звоню по договору CTR-001.\nclient: Да, помню про договор"
        summary = await llm.summarize(context, transcript)
        
        print(f"✓ Резюме: {summary.text}")
        print(f"  Провайдер: {summary.raw_payload.get('provider')}")
        print(f"  Использовано токенов: {summary.raw_payload.get('usage', {}).get('total_tokens', '?')}")
        print()
        
        print("Все тесты пройдены успешно!")
        
    except ValueError as exc:
        print(f"Ошибка конфигурации: {exc}")
    except Exception as exc:
        print(f"Ошибка: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_openrouter())
