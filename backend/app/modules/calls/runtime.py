from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.enums import CallAttemptStatus


class CallRuntimeError(Exception):
    pass


class RetryableCallError(CallRuntimeError):
    def __init__(
        self,
        message: str,
        attempt_status: CallAttemptStatus = CallAttemptStatus.no_answer,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.attempt_status = attempt_status
        self.raw_payload = raw_payload or {}


@dataclass(frozen=True)
class AudioArtifact:
    uri: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallSession:
    call_id: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerAudio:
    audio_uri: str
    is_final: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinishedCall:
    recording_uri: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class CallRuntimeGateway(Protocol):
    async def prepare_audio(self, text: str) -> AudioArtifact:
        raise NotImplementedError

    async def start_call(
        self,
        phone_number: str,
        opening_audio_uri: str,
        client_payload: dict[str, Any],
    ) -> CallSession:
        raise NotImplementedError

    async def wait_for_customer_audio(self, call_id: str) -> CustomerAudio:
        raise NotImplementedError

    async def recognize_speech(self, audio_uri: str) -> str:
        raise NotImplementedError

    async def play_audio(self, call_id: str, audio_uri: str) -> None:
        raise NotImplementedError

    async def finish_call(self, call_id: str) -> FinishedCall:
        raise NotImplementedError


def get_call_runtime_gateway() -> CallRuntimeGateway:
    settings = get_settings()
    if settings.call_runtime_provider == "mock":
        from app.modules.calls.mock_runtime import MockCallRuntimeGateway

        return MockCallRuntimeGateway()
    if settings.call_runtime_provider == "vosk":
        from app.modules.calls.vosk_runtime import VoskCallRuntimeGateway

        return VoskCallRuntimeGateway(
            model_path=settings.vosk_model_path,
            sample_rate=settings.vosk_sample_rate,
            fallback_text=settings.vosk_fallback_text,
            test_audio_path=settings.vosk_test_audio_path,
        )
    raise ValueError(f"Unsupported call runtime provider: {settings.call_runtime_provider}")

