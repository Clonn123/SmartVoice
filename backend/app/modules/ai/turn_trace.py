from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.observability import ms_between


@dataclass(slots=True)
class TurnTrace:
    call_id: str | None
    turn_index: int

    speech_started_at: datetime | None = None
    speech_ended_at: datetime | None = None

    stt_first_partial_at: datetime | None = None
    stt_final_at: datetime | None = None

    llm_started_at: datetime | None = None
    llm_finished_at: datetime | None = None

    tts_enqueued_at: datetime | None = None
    tts_first_audio_at: datetime | None = None

    user_text: str | None = None
    agent_text: str | None = None

    barge_in_detected_at: datetime | None = None

    def speech_duration_ms(self) -> int | None:
        if self.speech_started_at and self.speech_ended_at:
            return ms_between(self.speech_started_at, self.speech_ended_at)

        return None

    def ttfs_ms(self) -> int | None:
        if self.speech_ended_at and self.stt_final_at:
            return ms_between(self.speech_ended_at, self.stt_final_at)

        return None

    def llm_latency_ms(self) -> int | None:
        if self.llm_started_at and self.llm_finished_at:
            return ms_between(self.llm_started_at, self.llm_finished_at)

        return None

    def ttfa_ms(self) -> int | None:
        if self.tts_enqueued_at and self.tts_first_audio_at:
            return ms_between(self.tts_enqueued_at, self.tts_first_audio_at)

        return None

    def e2e_latency_ms(self) -> int | None:
        if self.speech_ended_at and self.tts_first_audio_at:
            return ms_between(self.speech_ended_at, self.tts_first_audio_at)

        return None
