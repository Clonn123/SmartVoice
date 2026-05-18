from __future__ import annotations

from app.modules.llm.base import LlmCallContext, LlmReply, LlmSummary


class MockLlmGateway:
    async def generate_reply(self, context: LlmCallContext) -> LlmReply:
        name = context.target.get("client_name") or "клиент"
        contract_id = context.target.get("contract_id")

        if not context.history:
            contract_phrase = f" по договору {contract_id}" if contract_id else ""
            return LlmReply(
                message=(
                    f"Здравствуйте, {name}. Звоню{contract_phrase}. "
                    "Подскажите, пожалуйста, вам удобно сейчас ответить на короткий вопрос?"
                ),
                raw_payload={
                    "provider": "mock",
                    "stage": "opening",
                    "scenario": context.scenario,
                    "prompt_used": context.prompt,
                },
            )

        last_client_message = next(
            (message.content for message in reversed(context.history) if message.role == "client"),
            "",
        ).lower()
        finish_call = any(word in last_client_message for word in ("да", "хорошо", "ок", "yes"))
        message = (
            "Спасибо, я зафиксировал ваш ответ. Хорошего дня."
            if finish_call
            else "Понял вас. Уточните, пожалуйста, какой итог по вашему обращению мне зафиксировать?"
        )
        return LlmReply(
            message=message,
            finish_call=finish_call,
            raw_payload={"provider": "mock", "stage": "dialogue"},
        )

    async def summarize(self, context: LlmCallContext, transcript: str) -> LlmSummary:
        result = "client_confirmed" if transcript else "unknown"
        return LlmSummary(
            text=(
                "Клиент подтвердил информацию по звонку."
                if transcript
                else "Диалог не состоялся."
            ),
            raw_payload={
                "provider": "mock",
                "scenario": context.scenario,
                "turns": len(context.history),
                "result": result,
                "target": context.target,
            },
        )

