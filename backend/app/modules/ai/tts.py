# app/modules/ai/tts.py

import wave
import audioop
import threading
import queue
import tempfile
import time

import edge_tts
import asyncio

from pydub import AudioSegment


class TTSService:

    def __init__(
        self,
        rtp_session
    ):

        self.rtp = rtp_session

        self.voice = "ru-RU-DmitryNeural"

        self.tts_queue = queue.Queue()
        self.playback_finished = threading.Event()
        self.playback_finished.set()

        self.running = False
        self.is_speaking = False

    # =====================================================
    # START
    # =====================================================

    def start(self):

        self.running = True

        threading.Thread(
            target=self._worker,
            daemon=True
        ).start()

        print("🔊 TTS STARTED")

    # =====================================================
    # SAY
    # =====================================================

    def say(self, text: str):

        if not text.strip():
            return

        self.playback_finished.clear()
        self.tts_queue.put(text)

    # =====================================================
    # STOP (BARGE-IN)
    # =====================================================

    def stop(self):

        self.is_speaking = False

        with self.rtp.outbound_audio.mutex:
            self.rtp.outbound_audio.queue.clear()

        print("🛑 TTS INTERRUPTED")

    # =====================================================
    # WORKER
    # =====================================================

    def _worker(self):

        while self.running:

            try:

                text = self.tts_queue.get(timeout=0.1)

                self.is_speaking = True

                print(f"🗣 TTS: {text}")

                self._speak(text)

                self.is_speaking = False
                self.playback_finished.set()

            except queue.Empty:
                continue

            except Exception as e:
                print("TTS ERROR:", e)
                self.is_speaking = False
                self.playback_finished.set()

    # =====================================================
    # SPEAK
    # =====================================================

    def _speak(self, text: str):

        wav_path = asyncio.run(
            self._generate_tts(text)
        )

        self._push_wav_to_queue(wav_path)
        self._wait_for_rtp_flush()

    # =====================================================
    # EDGE-TTS -> WAV
    # =====================================================

    async def _generate_tts(self, text: str):

        mp3_fp = tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False
        )

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice
        )

        await communicate.save(mp3_fp.name)

        audio = AudioSegment.from_mp3(
            mp3_fp.name
        )

        # ==========================================
        # TELEPHONY FORMAT
        # ==========================================

        audio = (
            audio
            .set_frame_rate(8000)
            .set_channels(1)
            .set_sample_width(2)
        )

        wav_path = mp3_fp.name.replace(
            ".mp3",
            ".wav"
        )

        audio.export(
            wav_path,
            format="wav"
        )

        return wav_path

    # =====================================================
    # WAV -> RTP QUEUE
    # =====================================================

    def _push_wav_to_queue(self, wav_path):

        with wave.open(wav_path, "rb") as wf:

            while self.is_speaking:

                # 160 samples = 20ms @ 8kHz
                pcm = wf.readframes(160)

                if not pcm:
                    break

                # enforce exact frame size
                if len(pcm) < 320:
                    pcm += b"\x00" * (320 - len(pcm))

                # PCM -> PCMU
                ulaw = audioop.lin2ulaw(
                    pcm,
                    2
                )

                # JUST PUSH TO RTP QUEUE
                self.rtp.outbound_audio.put(
                    ulaw
                )

        print("✅ TTS FINISHED")

    # =====================================================
    # WAIT RTP FLUSH
    # =====================================================

    def _wait_for_rtp_flush(self):

        started = time.time()

        while self.running and time.time() - started < 10:

            if self.rtp.outbound_audio.empty():
                time.sleep(0.3)
                if self.rtp.outbound_audio.empty():
                    return

            time.sleep(0.05)