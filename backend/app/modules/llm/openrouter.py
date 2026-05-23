from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.modules.llm.base import LlmCallContext, LlmReply, LlmSummary

logger = logging.getLogger(__name__)

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterLlmGateway:
    """Шлюз для интеграции с OpenRouter API."""

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 60) -> None:
        if not api_key:
            raise ValueError("Требуется API ключ OpenRouter (llm_openrouter_api_key)")
        if not model:
            raise ValueError("Требуется модель OpenRouter (llm_openrouter_model)")
        
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    async def generate_reply(self, context: LlmCallContext) -> LlmReply:
        """Генерирует ответ бота на основе контекста диалога через OpenRouter API."""
        messages = self._build_messages(context)
        
        logger.info(
            "Запрос к OpenRouter для генерации ответа: модель=%s, ходов=%s",
            self.model,
            len(context.history),
        )
        
        try:
            response = await self.client.post(
                f"{OPENROUTER_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 512,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            message = data["choices"][0]["message"]["content"]
            logger.info(
                "Ответ от OpenRouter получен: использовано токенов=%s",
                data.get("usage", {}).get("total_tokens", 0),
            )
            
            # Определяем, нужно ли завершить звонок по содержимому ответа
            finish_keywords = [
                "до свидания",
                "всего хорошего",
                "спасибо и до встречи",
                "до встречи",
                "хорошего дня",
                "спасибо за внимание",
                "разговор закончен",
                "пока",
                "до встреч",
                "хорошего вам дня",
            ]
            finish_call = any(kw in message.lower() for kw in finish_keywords)
            
            logger.info(
                "Ответ LLM: finish_call=%s, длина_ответа=%s, ответ=%s",
                finish_call,
                len(message),
                message[:150],  # Первые 150 символов для отладки
            )
            
            return LlmReply(
                message=message,
                finish_call=finish_call,
                raw_payload={
                    "provider": "openrouter",
                    "model": self.model,
                    "usage": data.get("usage", {}),
                    "finish_reason": data["choices"][0].get("finish_reason"),
                    "detected_ending": finish_call,
                },
            )
        except httpx.ConnectError as exc:
            logger.exception("Не удалось подключиться к OpenRouter: проверьте сеть и DNS")
            raise RuntimeError("Не удалось подключиться к OpenRouter: проверьте сеть и DNS") from exc
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Ошибка API OpenRouter",
                extra={
                    "status_code": exc.response.status_code,
                    "response": exc.response.text,
                },
            )
            raise
        except Exception as exc:
            logger.exception("Ошибка при генерации ответа через OpenRouter")
            raise

    async def summarize(self, context: LlmCallContext, transcript: str) -> LlmSummary:
        """Генерирует резюме звонка на основе транскрипции через OpenRouter API."""
        summary_prompt = f"""Проанализируй следующую транскрипцию диалога и создай краткое резюме:

Сценарий: {context.scenario}
Данные клиента: {json.dumps(context.target, ensure_ascii=False, indent=2)}

Транскрипция:
{transcript}

Создай краткое резюме из 1-2 предложений на русском языке, описывающее суть разговора и итоговый результат."""

        messages = [
            {"role": "system", "content": "Ты помощник, который создаёт краткие резюме деловых телефонных разговоров на русском языке."},
            {"role": "user", "content": summary_prompt},
        ]
        
        logger.info("Запрос к OpenRouter для создания резюме: модель=%s", self.model)
        
        try:
            response = await self.client.post(
                f"{OPENROUTER_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.5,
                    "max_tokens": 256,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            summary_text = data["choices"][0]["message"]["content"]
            logger.info(
                "Резюме получено от OpenRouter: использовано токенов=%s",
                data.get("usage", {}).get("total_tokens", 0),
            )
            
            return LlmSummary(
                text=summary_text,
                raw_payload={
                    "provider": "openrouter",
                    "model": self.model,
                    "scenario": context.scenario,
                    "usage": data.get("usage", {}),
                    "finish_reason": data["choices"][0].get("finish_reason"),
                },
            )
        except httpx.ConnectError as exc:
            logger.exception("Не удалось подключиться к OpenRouter при создании резюме: проверьте сеть и DNS")
            raise RuntimeError(
                "Не удалось подключиться к OpenRouter при создании резюме: проверьте сеть и DNS"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Ошибка API OpenRouter при создании резюме",
                extra={
                    "status_code": exc.response.status_code,
                    "response": exc.response.text,
                },
            )
            raise
        except Exception as exc:
            logger.exception("Ошибка при создании резюме через OpenRouter")
            raise

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        await self.client.aclose()

    @staticmethod
    def _build_messages(context: LlmCallContext) -> list[dict[str, str]]:
        """Строит список сообщений для отправки в OpenRouter API."""
        system_message = f"""Ты человек, занимающийся обзвоном по сценарию "{context.scenario}".

Описание сценария:
{context.prompt}

Данные клиента:
{json.dumps(context.target, ensure_ascii=False, indent=2)}

=== ПРАВИЛА ОТВЕТА (ОБЯЗАТЕЛЬНЫ!) ===

1. Выводи ТОЛЬКО готовый ответ для клиента, ничего больше
2. БЕЗ рассуждений, объяснений, размышлений о стратегии
3. БЕЗ анализа ситуации или описания своих мыслей
4. БЕЗ примечаний, комментариев, пояснений
5. Только текст, который ты будешь говорить клиенту

НЕПРАВИЛЬНО ❌
"Нужно учесть, что клиент выразил недовольство... Я думаю, лучше ответить так-то... Согласно инструкции... Оптимальный вариант ответа: Привет!"

ПРАВИЛЬНО ✅
"Привет! Чем я могу вам помочь?"

=== ЗАДАЧА ===
Вести естественный и вежливый диалог, следуя сценарию.
Собирать информацию от клиента кратко (1-2 предложения за раз).
Завершить звонок, когда:
- Получена нужная информация
- Клиент выразил нежелание продолжать  
- Достигнута цель звонка

При завершении звонка скажи "До свидания!" или "Спасибо и до встречи!"

Отвечай максимум 1-2 предложениями."""

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_message},
        ]
        
        # Добавляем историю диалога
        for msg in context.history:
            if msg.role == "bot":
                messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "client":
                messages.append({"role": "user", "content": msg.content})
        
        return messages
