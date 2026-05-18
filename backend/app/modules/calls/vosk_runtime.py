from __future__ import annotations

import json
import logging
import wave
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from app.modules.calls.runtime import AudioArtifact, CallSession, CustomerAudio, FinishedCall

logger = logging.getLogger(__name__)


class VoskCallRuntimeGateway:
    """Локальный runtime c STT на Vosk и mock-поведением для звонка/TTS."""

    def __init__(
        self,
        model_path: str | None,
        sample_rate: int = 16000,
        fallback_text: str = "да",
        test_audio_path: str | None = None,
    ) -> None:
        if not model_path:
            raise ValueError("Требуется VOSK_MODEL_PATH, если CALL_RUNTIME_PROVIDER=vosk")

        self.sample_rate = sample_rate
        self.fallback_text = fallback_text
        self.test_audio_path = test_audio_path

        try:
            from vosk import Model
        except ImportError as exc:
            raise RuntimeError(
                "Пакет vosk не установлен. Установите зависимости проекта заново."
            ) from exc

        model_dir = Path(model_path)
        if not model_dir.exists() or not model_dir.is_dir():
            raise ValueError(f"Каталог модели Vosk не найден: {model_path}")

        self._model = Model(str(model_dir))

    async def prepare_audio(self, text: str) -> AudioArtifact:
        return AudioArtifact(
            uri=f"mock://audio/{quote(text[:80])}",
            raw_payload={"provider": "vosk-runtime"},
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
                "provider": "vosk-runtime",
                "phone_number": phone_number,
                "opening_audio_uri": opening_audio_uri,
                "client_payload": client_payload,
            },
        )

    async def wait_for_customer_audio(self, call_id: str) -> CustomerAudio:
        # Для локального прогона можно один раз подать WAV через VOSK_TEST_AUDIO_PATH.
        if self.test_audio_path:
            return CustomerAudio(
                audio_uri=self.test_audio_path,
                raw_payload={"provider": "vosk-runtime", "source": "test_audio_path"},
            )

        return CustomerAudio(
            audio_uri=f"mock://customer-audio/{call_id}",
            raw_payload={"provider": "vosk-runtime", "source": "mock"},
        )

    async def recognize_speech(self, audio_uri: str) -> str:
        audio_path = self._resolve_audio_path(audio_uri)
        if audio_path is None:
            logger.warning(
                "Vosk recognize_speech: путь к аудио не найден, возвращаю fallback text"
            )
            return self.fallback_text

        try:
            from vosk import KaldiRecognizer

            with wave.open(str(audio_path), "rb") as wf:
                recognizer = KaldiRecognizer(self._model, wf.getframerate())

                while True:
                    data = wf.readframes(4000)
                    if len(data) == 0:
                        break
                    recognizer.AcceptWaveform(data)

                final_result = json.loads(recognizer.FinalResult())
                text = (final_result.get("text") or "").strip()
                if text:
                    return text

                return self.fallback_text
        except Exception:
            logger.exception("Vosk recognize_speech failed for audio_uri=%s", audio_uri)
            return self.fallback_text

    async def play_audio(self, call_id: str, audio_uri: str) -> None:
        return None

    async def finish_call(self, call_id: str) -> FinishedCall:
        return FinishedCall(
            recording_uri=f"mock://recordings/{call_id}.wav",
            raw_payload={"provider": "vosk-runtime", "call_id": call_id},
        )

    @staticmethod
    def _resolve_audio_path(audio_uri: str) -> Path | None:
        if audio_uri.startswith("file://"):
            path = Path(audio_uri.replace("file://", "", 1))
            return path if path.exists() else None

        candidate = Path(audio_uri)
        if candidate.exists() and candidate.is_file():
            return candidate

        return None
