# app/modules/ai/pipeline.py

from datetime import datetime
import threading
import time
import wave
import audioop

from app.modules.ai.stt import VoskSTT
from app.modules.ai.vad import VADDetector
from app.core.config import config
from app.modules.ai.tts import TTSService


class RealtimePipeline:

    def __init__(self, rtp_session):

        self.rtp = rtp_session

        self.running = False

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
        self.last_partial = ""

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

        self.wav_file = wave.open(filename, "wb")

        self.wav_file.setnchannels(1)
        self.wav_file.setsampwidth(2)
        self.wav_file.setframerate(8000)

        print(f"🎙 RECORDING: {filename}")

    # =====================================================
    # MAIN LOOP
    # =====================================================

    def loop(self):

        while self.running:

            if self.rtp.inbound_audio.empty():
                time.sleep(0.01)
                continue

            pcm = self.rtp.inbound_audio.get()

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

                if self.tts.is_speaking:

                    self.tts.stop()

                # ======================================
                # START SPEECH
                # ======================================

                if not self.is_speaking:

                    self.is_speaking = True

                    self.silence_ticks = 0

                    self.current_dialog_text = ""
                    self.last_partial = ""

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

                            if text != self.last_partial:

                                self.last_partial = text

                                self.current_dialog_text += " " + text

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

                                if text:
                                    self.current_dialog_text += " " + text

                        # ==================================
                        # FINAL TEXT
                        # ==================================

                        final_text = self.current_dialog_text.strip()

                        if final_text:

                            print("\n🟢 FINAL USER TEXT:")
                            print(final_text)
                            print()

                            # ==================================
                            # SEND TO TTS
                            # ==================================

                            self.tts.say(final_text)

                        # ==================================
                        # RESET
                        # ==================================

                        self.current_dialog_text = ""
                        self.last_partial = ""

                        self.stt.reset()

                        self.silence_ticks = 0

                        print("🤐 USER STOPPED SPEAKING")

    # =====================================================
    # STOP
    # =====================================================

    def stop(self):

        self.running = False

        if self.wav_file:
            self.wav_file.close()

        print("🛑 PIPELINE STOPPED")