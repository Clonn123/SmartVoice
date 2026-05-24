from __future__ import annotations

from urllib.parse import quote
from uuid import uuid4

from app.modules.calls.runtime import AudioArtifact, CallSession, CustomerAudio, FinishedCall


class MockCallRuntimeGateway:
    async def prepare_audio(self, text: str) -> AudioArtifact:
        return AudioArtifact(
            uri=f"mock://audio/{quote(text[:80])}",
            raw_payload={"provider": "mock"},
        )

    async def start_call(
        self,
        phone_number: str,
        opening_audio_uri: str,
        client_payload: dict,
    ) -> CallSession:
        return CallSession(
            call_id=str(uuid4()),
            raw_payload={
                "provider": "mock",
                "phone_number": phone_number,
                "opening_audio_uri": opening_audio_uri,
                "client_payload": client_payload,
            },
        )

    async def wait_for_customer_audio(self, call_id: str) -> CustomerAudio:
        return CustomerAudio(
            audio_uri=f"mock://customer-audio/{call_id}",
            raw_payload={"provider": "mock"},
        )

    async def recognize_speech(self, audio_uri: str) -> str:
        return "yes"

    async def play_audio(self, call_id: str, audio_uri: str) -> None:
        return None

    async def finish_call(self, call_id: str) -> FinishedCall:
        return FinishedCall(
            recording_uri=f"mock://recordings/{call_id}.wav",
            raw_payload={"provider": "mock", "call_id": call_id},
        )


