from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import threading
import time
import wave
import audioop

import requests

from app.core.config import config
from app.modules.ai.stt import VoskSTT
from app.modules.ai.tts import TTSService
from app.modules.ai.vad import VADDetector
from app.modules.llm.base import CallMessage, LlmCallContext
from app.modules.llm.base import LlmReply
from app.modules.llm.factory import get_llm_gateway
from app.modules.llm.context import FINAL_MARKER, build_call_context


class RealtimePipeline:

    def __init__(self, rtp_session, call_context=None):

        self.rtp = rtp_session
        self.call_context = call_context

        self.running = False

        self.llm = get_llm_gateway()

        # ==========================================
        # STT
        # ==========================================

        self.stt = VoskSTT(
            config.VOSK_MODEL_PATH,
            config.VOSK_SAMPLE_RATE
        )

        # ==========================================
        # VAD
        # ==========================================

        self.vad = VADDetector()

        # ==========================================
        # TTS
        # ==========================================

        self.tts = TTSService(
            rtp_session=rtp_session
        )

        # ==========================================
        # AUDIO BUFFER
        # ==========================================

        self.audio_buffer = bytearray()

        self.target_buffer_size = 8000 * 2 * 2

        # ==========================================
        # STATES
        # ==========================================

        self.is_speaking = False
        self.silence_ticks = 0

        self.silence_threshold = 15

        # ==========================================
        # TEXT
        # ==========================================

        self.current_dialog_text = ""
        self.current_dialog_segments: list[str] = []
        self.last_partial = ""
        self.last_partial_committed = ""
        self.dialog_history: list[CallMessage] = []
        self.greeting_sent = False
        self.opening_greeting_active = False
        self.finish_call_pending = False
        self.closing_message_active = False

        # ==========================================
        # WAV DEBUG
        # ==========================================

        self.wav_file = None

    # =====================================================
    # START
    # =====================================================

    def start(self):

        self.running = True

        self.tts.start()

        self._open_wav()

        threading.Thread(
            target=self.loop,
            daemon=True
        ).start()

        print("🧠 REALTIME PIPELINE STARTED")

    # =====================================================
    # WAV DEBUG
    # =====================================================

    def _open_wav(self):

        filename = f"record_{datetime.now().strftime('%H_%M_%S')}.wav"
        recordings_dir = Path(config.recordings_dir)
        recordings_dir.mkdir(parents=True, exist_ok=True)
        recording_path = recordings_dir / filename

        self.wav_file = wave.open(str(recording_path), "wb")

        self.wav_file.setnchannels(1)
        self.wav_file.setsampwidth(2)
        self.wav_file.setframerate(8000)

        print(f"🎙 RECORDING: {recording_path}")

    # =====================================================
    # MAIN LOOP
    # =====================================================

    def loop(self):

        while self.running:

            if self.rtp.inbound_audio.empty():
                time.sleep(0.01)
                continue

            pcm = self.rtp.inbound_audio.get()

            if self.opening_greeting_active:
                time.sleep(0.01)
                continue

            if self.finish_call_pending and self.closing_message_active:
                time.sleep(0.01)
                continue

            # ==========================================
            # BOOST
            # ==========================================

            pcm = audioop.mul(pcm, 2, 3.0)

            # ==========================================
            # SAVE DEBUG WAV
            # ==========================================

            self.wav_file.writeframes(pcm)

            # ==========================================
            # VAD
            # ==========================================

            is_speech = self.vad.process(pcm)

            # ==========================================
            # USER STARTED TALKING
            # ==========================================

            if is_speech:

                # ======================================
                # BARGE-IN
                # ======================================

                if self.tts.is_speaking and not self.finish_call_pending:

                    self.tts.stop()

                # ======================================
                # START SPEECH
                # ======================================

                if not self.is_speaking:

                    self.is_speaking = True

                    self.silence_ticks = 0

                    self.current_dialog_text = ""
                    self.current_dialog_segments = []
                    self.last_partial = ""
                    self.last_partial_committed = ""

                    self.stt.reset()

                    print("🎤 USER STARTED SPEAKING")

                self.silence_ticks = 0

                # ======================================
                # BUFFER AUDIO
                # ======================================

                self.audio_buffer.extend(pcm)

                # ======================================
                # 2 SECOND CHUNK
                # ======================================

                if len(self.audio_buffer) >= self.target_buffer_size:

                    pcm16k, _ = audioop.ratecv(
                        bytes(self.audio_buffer),
                        2,
                        1,
                        8000,
                        16000,
                        None
                    )

                    result = self.stt.accept(
                        pcm16k
                    )

                    self.audio_buffer.clear()

                    if result:

                        text = result.get(
                            "text",
                            ""
                        ).strip()

                        if text:

                            result_type = result.get("type")

                            if result_type == "final":

                                if not self.current_dialog_segments or self.current_dialog_segments[-1] != text:

                                    self.current_dialog_segments.append(text)

                                    self.current_dialog_text = " ".join(self.current_dialog_segments).strip()

                                    print("🟢", text)

                            elif text != self.last_partial:

                                self.last_partial = text

                                self.last_partial_committed = text

                                print("🟡", text)

            # ==========================================
            # SILENCE
            # ==========================================

            else:

                if self.is_speaking:

                    self.silence_ticks += 1

                    # ==================================
                    # END OF SPEECH
                    # ==================================

                    if self.silence_ticks >= self.silence_threshold:

                        self.is_speaking = False

                        # flush remaining buffer
                        if self.audio_buffer:

                            pcm16k, _ = audioop.ratecv(
                                bytes(self.audio_buffer),
                                2,
                                1,
                                8000,
                                16000,
                                None
                            )

                            result = self.stt.accept(
                                pcm16k
                            )

                            self.audio_buffer.clear()

                            if result:

                                text = result.get(
                                    "text",
                                    ""
                                ).strip()

                                if text and result.get("type") == "final":

                                    if not self.current_dialog_segments or self.current_dialog_segments[-1] != text:

                                        self.current_dialog_segments.append(text)

                                        self.current_dialog_text = " ".join(self.current_dialog_segments).strip()

                                elif text and not self.current_dialog_text:

                                    self.current_dialog_text = text

                        # ==================================
                        # FINAL TEXT
                        # ==================================

                        final_text = self.current_dialog_text.strip() or self.last_partial_committed.strip()

                        final_text = self._normalize_transcript(final_text)

                        if final_text:

                            print("\n🟢 FINAL USER TEXT:")
                            print(final_text)
                            print()

                            # ==================================
                            # SEND TO LLM
                            # ==================================

                            llm_reply = self._get_llm_reply(final_text)

                            if llm_reply:

                                reply_text = self._sanitize_farewell(llm_reply.message) if llm_reply.finish_call else llm_reply.message

                                print("🤖 LLM REPLY:")
                                print(reply_text)
                                print()

                                self.dialog_history.append(
                                    CallMessage(role="client", content=final_text)
                                )
                                self.dialog_history.append(
                                    CallMessage(role="bot", content=reply_text)
                                )

                            # ==================================
                            # SEND TO TTS
                            # ==================================

                            if llm_reply:

                                if llm_reply.finish_call:
                                    self.closing_message_active = True

                                self.tts.say(reply_text)

                                if llm_reply.finish_call:

                                    self.finish_call_pending = True
                                    threading.Thread(
                                        target=self._hangup_after_tts,
                                        daemon=True,
                                    ).start()

                            else:

                                self.tts.say(final_text)

                        # ==================================
                        # RESET
                        # ==================================

                        self.current_dialog_text = ""
                        self.current_dialog_segments = []
                        self.last_partial = ""
                        self.last_partial_committed = ""

                        self.stt.reset()

                        self.silence_ticks = 0

                        print("🤐 USER STOPPED SPEAKING")

    # =====================================================
    # STOP
    # =====================================================

    def stop(self):

        self.running = False
        self.finish_call_pending = False
        self.closing_message_active = False

        if self.wav_file:
            self.wav_file.close()

        print("🛑 PIPELINE STOPPED")

    # =====================================================
    # LLM
    # =====================================================

    def _get_llm_reply(self, user_text: str) -> LlmReply | None:

        prompt = getattr(self.call_context, "llm_prompt", None) or "Напомни клиенту о договоре и спроси его, помнит ли он о нём. Скажи, что звонишь только напомнить о задолжности, больше не нужно ничего."
        scenario = getattr(self.call_context, "llm_scenario", None) or "realtime_call"
        target = getattr(self.call_context, "llm_target", None) or {"user_text": user_text}
        metadata = getattr(self.call_context, "llm_metadata", None) or {}

        context = build_call_context(
            prompt=prompt,
            scenario=scenario,
            target=target,
            history=[*self.dialog_history, CallMessage(role="client", content=user_text)],
            extra_context=metadata,
        )

        try:

            reply = asyncio.run(self.llm.generate_reply(context))

            return reply

        except Exception as exc:

            print("LLM ERROR:", exc)

            return None

    def _queue_opening_greeting(self) -> None:

        if self.greeting_sent:
            return

        self.greeting_sent = True
        self.opening_greeting_active = True

        greeting = getattr(self.call_context, "llm_opening_reply", None) or "Здравствуйте! Подскажите, пожалуйста, удобно ли вам сейчас говорить?"

        self.dialog_history.append(CallMessage(role="bot", content=greeting))
        self.tts.say(greeting)

        threading.Thread(
            target=self._wait_opening_greeting_done,
            daemon=True,
        ).start()

    def _wait_opening_greeting_done(self) -> None:

        started = time.time()
        while self.running and time.time() - started < 30:
            if not self.tts.is_speaking and self.tts.tts_queue.empty():
                break
            time.sleep(0.05)

        self.opening_greeting_active = False

    def _hangup_after_tts(self) -> None:

        if not self.tts.playback_finished.wait(timeout=30):
            print("HANGUP WAIT TIMEOUT: TTS playback was not confirmed finished")

        self._hangup_call()

    def _hangup_call(self) -> None:

        channel_id = getattr(self.call_context, "channel_id", None)

        if not channel_id:
            self.stop()
            return

        url = f"http://{config.ARI_HOST}:{config.ARI_PORT}/ari/channels/{channel_id}"

        try:
            response = requests.delete(
                url,
                auth=(config.ARI_USER, config.ARI_PASS),
                timeout=5,
            )
            response.raise_for_status()
            print(f"🛑 CALL HUNG UP: {channel_id}")
        except Exception as exc:
            print("HANGUP ERROR:", exc)
        finally:
            self.stop()

    @staticmethod
    def _sanitize_farewell(text: str) -> str:

        cleaned = text.strip()

        if FINAL_MARKER in cleaned:
            cleaned = cleaned.split(FINAL_MARKER, 1)[0].rstrip("\n ").strip()

        return cleaned or text.strip()

    @staticmethod
    def _normalize_transcript(text: str) -> str:

        words = text.split()

        if len(words) < 4:
            return text.strip()

        changed = True

        while changed:

            changed = False

            max_window = min(8, len(words) // 2)

            for window in range(max_window, 1, -1):

                cursor = 0

                while cursor + 2 * window <= len(words):

                    left = words[cursor:cursor + window]
                    right = words[cursor + window:cursor + 2 * window]

                    if left == right:

                        del words[cursor + window:cursor + 2 * window]
                        changed = True

                        break

                    cursor += 1

                if changed:

                    break

        return " ".join(words).strip()