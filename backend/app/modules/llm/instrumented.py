from __future__ import annotations

from app.modules.llm.base import LlmCallContext, LlmGateway, LlmReply, LlmSummary
from app.observability import metric_span


class InstrumentedLlmGateway:
    def __init__(
        self,
        inner: LlmGateway,
        provider: str,
        model_name: str | None = None,
    ) -> None:
        self.inner = inner
        self.provider = provider
        self.model_name = model_name

    async def generate_reply(self, context: LlmCallContext) -> LlmReply:
        async with metric_span(
            "llm.generate_reply",
            component="llm.gateway",
            provider=self.provider,
            model_name=self.model_name,
            attrs={
                "scenario": context.scenario,
                "prompt_chars": len(context.prompt or ""),
                "history_turns": len(context.history),
                "target_keys": list(context.target.keys()),
                "extra_context_keys": list(context.extra_context.keys()),
            },
        ) as span:
            reply = await self.inner.generate_reply(context)

            span.tag(
                reply_chars=len(reply.message or ""),
                finish_call=reply.finish_call,
                raw_payload=reply.raw_payload,
            )

            return reply

    async def summarize(self, context: LlmCallContext, transcript: str) -> LlmSummary:
        async with metric_span(
            "llm.summarize",
            component="llm.gateway",
            provider=self.provider,
            model_name=self.model_name,
            attrs={
                "scenario": context.scenario,
                "history_turns": len(context.history),
                "transcript_chars": len(transcript or ""),
            },
        ) as span:
            summary = await self.inner.summarize(context, transcript)

            span.tag(
                summary_chars=len(summary.text or ""),
                raw_payload=summary.raw_payload,
            )

            return summary
