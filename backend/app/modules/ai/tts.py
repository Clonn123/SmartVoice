import asyncio
import audioop
import queue
import tempfile
import threading
import time
import wave
from datetime import datetime
from typing import Any

import edge_tts
from pydub import AudioSegment

from app.observability import metric, metric_span, ms_between, utc_now


class TTSService:
    def __init__(self, rtp_session):
        self.rtp = rtp_session
        self.voice = "ru-RU-DmitryNeural"
        self.tts_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.playback_finished = threading.Event()
        self.playback_finished.set()
        self.running = False
        self.is_speaking = False

    def start(self):
        self.running = True

        threading.Thread(
            target=self._worker,
            daemon=True,
        ).start()

        metric(
            "tts.service_started",
            component="ai.tts",
            provider="edge_tts",
            status="started",
        )

        print(" TTS STARTED")

    def say(self, text: str, context: dict | None = None):
        if not text.strip():
            return

        context = context or {}

        self.playback_finished.clear()

        self.tts_queue.put(
            {
                "text": text,
                "context": context,
                "enqueued_at": utc_now(),
            }
        )

        metric(
            "tts.enqueued",
            component="ai.tts",
            call_id=context.get("call_id"),
            turn_index=context.get("turn_index"),
            provider="edge_tts",
            status="queued",
            attrs={
                "text_chars": len(text),
                "queue_size": self.tts_queue.qsize(),
            },
        )

    def stop(self, context: dict | None = None):
        context = context or {}

        self.is_speaking = False

        with self.rtp.outbound_audio.mutex:
            dropped_frames = len(self.rtp.outbound_audio.queue)
            self.rtp.outbound_audio.queue.clear()

        metric(
            "tts.interrupted",
            component="ai.tts",
            call_id=context.get("call_id"),
            turn_index=context.get("turn_index"),
            provider="edge_tts",
            status="interrupted",
            attrs={
                "reason": "barge_in",
                "dropped_frames": dropped_frames,
            },
        )

        print(" TTS INTERRUPTED")

    def _worker(self):
        while self.running:
            try:
                job = self.tts_queue.get(timeout=0.1)

                text = job["text"]
                context = job["context"]
                enqueued_at = job["enqueued_at"]

                self.is_speaking = True

                print(f" TTS: {text}")

                with metric_span(
                    "tts.speak",
                    component="ai.tts",
                    call_id=context.get("call_id"),
                    turn_index=context.get("turn_index"),
                    provider="edge_tts",
                    attrs={
                        "text_chars": len(text),
                    },
                ):
                    self._speak(
                        text,
                        context=context,
                        enqueued_at=enqueued_at,
                    )

                self.is_speaking = False
                self.playback_finished.set()

            except queue.Empty:
                continue

            except Exception as e:
                metric(
                    "tts.error",
                    component="ai.tts",
                    provider="edge_tts",
                    status="error",
                    error=str(e),
                )

                print("TTS ERROR:", e)

                self.is_speaking = False
                self.playback_finished.set()

    def _speak(self, text: str, context: dict, enqueued_at: datetime):
        wav_path = asyncio.run(self._generate_tts(text, context=context))

        self._push_wav_to_queue(
            wav_path,
            context=context,
            enqueued_at=enqueued_at,
        )

        self._wait_for_rtp_flush()

    async def _generate_tts(self, text: str, context: dict | None = None):
        context = context or {}

        async with metric_span(
            "tts.generate_audio",
            component="ai.tts",
            call_id=context.get("call_id"),
            turn_index=context.get("turn_index"),
            provider="edge_tts",
            model_name=self.voice,
            attrs={
                "text_chars": len(text),
            },
        ) as span:
            mp3_fp = tempfile.NamedTemporaryFile(
                suffix=".mp3",
                delete=False,
            )

            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
            )

            await communicate.save(mp3_fp.name)

            audio = AudioSegment.from_mp3(
                mp3_fp.name,
            )

            audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)

            wav_path = mp3_fp.name.replace(
                ".mp3",
                ".wav",
            )

            audio.export(
                wav_path,
                format="wav",
            )

            span.tag(
                wav_path=wav_path,
                audio_duration_ms=len(audio),
            )

            return wav_path

    def _push_wav_to_queue(self, wav_path, context: dict, enqueued_at: datetime):
        first_audio_sent = False
        frames_pushed = 0

        with wave.open(wav_path, "rb") as wf:
            while self.is_speaking:
                pcm = wf.readframes(160)

                if not pcm:
                    break

                if len(pcm) < 320:
                    pcm += b"\x00" * (320 - len(pcm))

                ulaw = audioop.lin2ulaw(
                    pcm,
                    2,
                )

                self.rtp.outbound_audio.put(
                    ulaw,
                )

                frames_pushed += 1

                if not first_audio_sent:
                    first_audio_sent = True

                    first_audio_at = utc_now()
                    ttfa_ms = ms_between(enqueued_at, first_audio_at)

                    e2e_latency_ms = None
                    speech_ended_at_raw = context.get("speech_ended_at")

                    if speech_ended_at_raw:
                        try:
                            speech_ended_at = datetime.fromisoformat(
                                speech_ended_at_raw
                            )
                            e2e_latency_ms = ms_between(speech_ended_at, first_audio_at)
                        except Exception:
                            e2e_latency_ms = None

                    metric(
                        "tts.first_audio",
                        component="ai.tts",
                        call_id=context.get("call_id"),
                        turn_index=context.get("turn_index"),
                        provider="edge_tts",
                        status="ok",
                        duration_ms=ttfa_ms,
                        value_numeric=ttfa_ms,
                        unit="ms",
                        attrs={
                            "ttfa_ms": ttfa_ms,
                            "e2e_latency_ms": e2e_latency_ms,
                        },
                    )

        metric(
            "tts.audio_pushed",
            component="ai.tts",
            call_id=context.get("call_id"),
            turn_index=context.get("turn_index"),
            provider="edge_tts",
            status="ok",
            attrs={
                "frames_pushed": frames_pushed,
                "wav_path": wav_path,
            },
        )

        print("✅ TTS FINISHED")

    def _wait_for_rtp_flush(self):
        started = time.time()

        while self.running and time.time() - started < 10:
            if self.rtp.outbound_audio.empty():
                time.sleep(0.3)

                if self.rtp.outbound_audio.empty():
                    return

            time.sleep(0.05)
