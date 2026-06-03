import json
from typing import Any

from vosk import KaldiRecognizer, Model

from app.observability import metric, metric_span


class VoskSTT:
    def __init__(self, model_path: str, sample_rate=8000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.model = Model(model_path)
        self.rec = KaldiRecognizer(self.model, sample_rate)
        self.rec.SetWords(True)
        self.last_partial = ""

    def accept(
        self,
        pcm: bytes,
        *,
        call_id: str | None = None,
        turn_index: int | None = None,
        audio_duration_ms: int | None = None,
    ) -> dict[str, Any] | None:
        with metric_span(
            "stt.accept_chunk",
            component="ai.stt",
            call_id=call_id,
            turn_index=turn_index,
            provider="vosk",
            model_name=self.model_path,
            attrs={
                "pcm_bytes": len(pcm),
                "audio_duration_ms": audio_duration_ms,
                "sample_rate": self.sample_rate,
            },
        ) as span:
            if self.rec.AcceptWaveform(pcm):
                result = json.loads(self.rec.Result())
                text = result.get("text", "").strip()
                words = result.get("result", [])

                span.tag(
                    result_type="final",
                    text_chars=len(text),
                    words_count=len(words),
                    empty_transcript=not bool(text),
                )

                metric(
                    "stt.final",
                    component="ai.stt",
                    call_id=call_id,
                    turn_index=turn_index,
                    provider="vosk",
                    model_name=self.model_path,
                    status="ok" if text else "empty",
                    attrs={
                        "text_chars": len(text),
                        "words_count": len(words),
                        "empty_transcript": not bool(text),
                    },
                )

                return {
                    "type": "final",
                    "text": text,
                    "raw": result,
                    "words": words,
                }

            partial = json.loads(self.rec.PartialResult())
            text = partial.get("partial", "").strip()

            if text == self.last_partial:
                return None

            self.last_partial = text

            if text:
                metric(
                    "stt.partial",
                    component="ai.stt",
                    call_id=call_id,
                    turn_index=turn_index,
                    provider="vosk",
                    model_name=self.model_path,
                    status="ok",
                    attrs={
                        "text_chars": len(text),
                    },
                )

            return {
                "type": "partial",
                "text": text,
                "raw": partial,
            }

    def reset(self):
        self.rec.Reset()
        self.last_partial = ""

        metric(
            "stt.reset",
            component="ai.stt",
            provider="vosk",
            model_name=self.model_path,
            status="ok",
        )
