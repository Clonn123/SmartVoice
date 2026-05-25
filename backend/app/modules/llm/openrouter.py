from __future__ import annotations

import json
import logging

import httpx

from app.modules.llm.base import LlmCallContext, LlmReply, LlmSummary
from app.modules.llm.context import FINAL_MARKER, build_openrouter_messages

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

    async def _post(self, *, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{OPENROUTER_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            return response.json()

    async def generate_reply(self, context: LlmCallContext) -> LlmReply:
        """Генерирует ответ бота на основе контекста диалога через OpenRouter API."""
        messages = self._build_messages(context)
        
        logger.info(
            "Запрос к OpenRouter для генерации ответа: модель=%s, ходов=%s",
            self.model,
            len(context.history),
        )
        
        try:
            data = await self._post(messages=messages, temperature=0.7, max_tokens=512)
            
            message = data["choices"][0]["message"]["content"]
            finish_call, message = self._extract_finish_call(message)
            logger.info(
                "Ответ от OpenRouter получен: использовано токенов=%s",
                data.get("usage", {}).get("total_tokens", 0),
            )
            
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
            data = await self._post(messages=messages, temperature=0.5, max_tokens=256)
            
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
        """Совместимый no-op: клиент создаётся на каждый запрос."""
        return None

    @staticmethod
    def _build_messages(context: LlmCallContext) -> list[dict[str, str]]:
        """Строит список сообщений для отправки в OpenRouter API."""
        return build_openrouter_messages(context)

    @staticmethod
    def _extract_finish_call(message: str) -> tuple[bool, str]:
        cleaned_message = message.strip()

        if FINAL_MARKER in cleaned_message:
            message_without_marker = cleaned_message.split(FINAL_MARKER, 1)[0].rstrip("\n ")
            return True, message_without_marker.strip()

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
        finish_call = any(kw in cleaned_message.lower() for kw in finish_keywords)
        return finish_call, cleaned_message
