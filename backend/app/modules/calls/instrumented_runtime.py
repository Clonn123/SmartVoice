from __future__ import annotations

from typing import Any

from app.modules.calls.runtime import (
    AudioArtifact,
    CallRuntimeGateway,
    CallSession,
    CustomerAudio,
    FinishedCall,
)
from app.observability import metric, metric_span


class InstrumentedCallRuntimeGateway:
    def __init__(self, inner: CallRuntimeGateway, provider: str) -> None:
        self.inner = inner
        self.provider = provider

    async def prepare_audio(self, text: str) -> AudioArtifact:
        async with metric_span(
            "runtime.prepare_audio",
            component="calls.runtime",
            provider=self.provider,
            attrs={"text_chars": len(text or "")},
        ) as span:
            result = await self.inner.prepare_audio(text)

            span.tag(
                audio_uri=result.uri,
                raw_payload=result.raw_payload,
            )

            return result

    async def start_call(
        self,
        phone_number: str,
        opening_audio_uri: str,
        client_payload: dict[str, Any],
    ) -> CallSession:
        async with metric_span(
            "runtime.start_call",
            component="calls.runtime",
            provider=self.provider,
            attrs={
                "phone_present": bool(phone_number),
                "opening_audio_uri": opening_audio_uri,
                "external_id": client_payload.get("external_id"),
                "contract_id": client_payload.get("contract_id"),
            },
        ) as span:
            result = await self.inner.start_call(
                phone_number=phone_number,
                opening_audio_uri=opening_audio_uri,
                client_payload=client_payload,
            )

            span.tag(
                provider_call_id=result.call_id,
                raw_payload=result.raw_payload,
            )

            metric(
                "call.connected",
                component="calls.runtime",
                provider=self.provider,
                status="connected",
                attrs={
                    "provider_call_id": result.call_id,
                },
            )

            return result

    async def wait_for_customer_audio(self, call_id: str) -> CustomerAudio:
        async with metric_span(
            "runtime.wait_for_customer_audio",
            component="calls.runtime",
            provider=self.provider,
            attrs={
                "provider_call_id": call_id,
            },
        ) as span:
            result = await self.inner.wait_for_customer_audio(call_id)

            span.tag(
                audio_uri=result.audio_uri,
                is_final=result.is_final,
                raw_payload=result.raw_payload,
            )

            return result

    async def recognize_speech(self, audio_uri: str) -> str:
        async with metric_span(
            "runtime.recognize_speech",
            component="calls.runtime",
            provider=self.provider,
            attrs={
                "audio_uri": audio_uri,
            },
        ) as span:
            text = await self.inner.recognize_speech(audio_uri)

            span.tag(
                text_chars=len(text or ""),
                empty_transcript=not bool(text),
            )

            metric(
                "stt.batch_result",
                component="calls.runtime",
                provider=self.provider,
                status="ok" if text else "empty",
                attrs={
                    "audio_uri": audio_uri,
                    "text_chars": len(text or ""),
                    "empty_transcript": not bool(text),
                },
            )

            return text

    async def play_audio(self, call_id: str, audio_uri: str) -> None:
        async with metric_span(
            "runtime.play_audio",
            component="calls.runtime",
            provider=self.provider,
            attrs={
                "provider_call_id": call_id,
                "audio_uri": audio_uri,
            },
        ):
            await self.inner.play_audio(call_id, audio_uri)

    async def finish_call(self, call_id: str) -> FinishedCall:
        async with metric_span(
            "runtime.finish_call",
            component="calls.runtime",
            provider=self.provider,
            attrs={
                "provider_call_id": call_id,
            },
        ) as span:
            result = await self.inner.finish_call(call_id)

            span.tag(
                recording_uri=result.recording_uri,
                raw_payload=result.raw_payload,
            )

            return result
