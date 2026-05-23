import asyncio
import logging
import socket
import time
import traceback
import audioop
import wave
from ari_client import AriClient, StasisStartEvent
import numpy as np
import queue
import threading
from faster_whisper import WhisperModel
# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# убираем websocket spam
logging.getLogger("ari_client").setLevel(logging.CRITICAL)
logging.getLogger("websockets").setLevel(logging.CRITICAL)

log = logging.getLogger("app")

# =========================================================
# CONFIG
# =========================================================

ARI_HOST = "asterisk"
ARI_PORT = 8088

ARI_USER = "python"
ARI_PASS = "supersecret"

APP = "main-app"

SIP_ENDPOINT = "PJSIP/100"

RTP_HOST = "python-ai"
RTP_PORT = 6000

# =========================================================
# GLOBALS
# =========================================================

call_started = False
packet_counter = 0


model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)

audio_queue = queue.Queue()

stream_buffer = bytearray()
lock = threading.Lock()

sample_rate = 8000
channels = 1
sampwidth = 2
OUTPUT_FILE = "call.wav"

wav_file = wave.open(OUTPUT_FILE, "wb")
wav_file.setnchannels(channels)
wav_file.setsampwidth(sampwidth)
wav_file.setframerate(sample_rate)
# =====================
# RTP PARSER
# =====================

def strip_rtp(pkt):
    return pkt[12:]  # RTP header remove


def pcmu_to_pcm(data):
    return audioop.ulaw2lin(data, 2)
# =========================================================
# RTP LISTENER
# =========================================================

def rtp_listener():

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sock.bind(("0.0.0.0", RTP_PORT))

    log.info(f"🎧 RTP LISTENING ON {RTP_PORT}")

    while True:

        try:

            pkt, _ = sock.recvfrom(2048)

            payload = strip_rtp(pkt)
            pcm = pcmu_to_pcm(payload)
            wav_file.writeframes(pcm)

        except Exception as e:

            log.error(f"RTP ERROR: {e}")

def buffer_worker():
    global stream_buffer

    while True:
        pcm = audio_queue.get()

        with lock:
            stream_buffer.extend(pcm)

            # keep last ~5 seconds only (8000 Hz, 16-bit mono)
            max_bytes = 8000 * 2 * 5
            if len(stream_buffer) > max_bytes:
                stream_buffer = stream_buffer[-max_bytes:]

# =====================
# THREAD 3 - STREAMING STT
# =====================

def stt_worker():
    global stream_buffer

    last_offset = 0

    log.info("🧠 STT streaming started")

    while True:
        time.sleep(0.4)  # realtime chunk window (~400ms)

        with lock:
            if len(stream_buffer) < 8000 * 2:  # <1 sec audio
                continue

            audio_copy = bytes(stream_buffer)

        audio_np = np.frombuffer(audio_copy, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = model.transcribe(
            audio_np,
            language="ru",
            beam_size=1,
            vad_filter=False,  # IMPORTANT: we do streaming ourselves
            condition_on_previous_text=True
        )

        text = "".join([s.text for s in segments]).strip()

        if text:
            log.info(f"🧠 LIVE: {text}")

# =========================================================
# ARI CLIENT
# =========================================================

client = AriClient(
    host=ARI_HOST,
    port=ARI_PORT,
    ari_user=ARI_USER,
    ari_password=ARI_PASS,
    tls_enabled=False
)

# =========================================================
# STASIS START
# =========================================================

@client.on_stasis_start
async def on_stasis_start(event: StasisStartEvent):

    global call_started

    try:

        channel = event.channel

        log.info(
            f"📞 STASIS START: {channel.name}"
        )

        # =================================================
        # IGNORE RTP CHANNEL
        # =================================================

        if "UnicastRTP" in channel.name:

            log.info("⛔ IGNORE RTP CHANNEL")

            return

        # =================================================
        # ONLY ONE CALL
        # =================================================

        if call_started:

            log.info("⛔ CALL ALREADY EXISTS")

            return

        call_started = True

        # =================================================
        # ANSWER
        # =================================================

        await channel.answer()

        log.info("✅ ANSWERED")

        # =================================================
        # CREATE BRIDGE
        # =================================================

        bridge = await client.ari.create_bridge(
            type="mixing"
        )

        log.info(f"🌉 BRIDGE: {bridge.id}")

        await bridge.add_channel(channel.id)

        log.info("➕ SIP CHANNEL ADDED")

        # =================================================
        # EXTERNAL MEDIA
        # =================================================

        media = await client.ari.create_external_media(
            external_host=f"{RTP_HOST}:{RTP_PORT}",
            format="ulaw",
        )

        log.info(f"🎧 MEDIA CHANNEL: {media.id}")

        await bridge.add_channel(media.id)

        log.info("➕ MEDIA CHANNEL ADDED")

        # =================================================
        # TEST PLAYBACK
        # =================================================

        # это заставит Asterisk
        # гарантированно отправлять RTP

        log.info("🔊 PLAYBACK STARTED")

        log.info("🚀 AUDIO PIPELINE READY")

    except Exception as e:

        log.error(f"❌ STASIS ERROR: {e}")

        traceback.log.info_exc()

# =========================================================
# ORIGINATE
# =========================================================

async def originate():

    try:

        log.info("📡 ORIGINATING CALL")

        await client.ari.originate(
            endpoint=SIP_ENDPOINT,
            app_args=APP,
            caller_id="AI Bot <1000>"
        )

        log.info("✅ ORIGINATE SENT")

    except Exception as e:

        log.error(f"❌ ORIGINATE ERROR: {e}")

        traceback.log.info_exc()

# =========================================================
# MAIN
# =========================================================

async def main():

    # =====================================================
    # RTP THREAD
    # =====================================================

    import threading

    threading.Thread(
        target=rtp_listener,
        daemon=True
    ).start()
    # threading.Thread(target=buffer_worker, daemon=True).start()
    # threading.Thread(target=stt_worker, daemon=True).start()
    # =====================================================
    # CONNECT ARI
    # =====================================================

    log.info("🔌 CONNECTING TO ARI")

    await client.connect(
        app=APP,
        subscribe_to_all=True
    )

    log.info("✅ ARI CONNECTED")

    # =====================================================
    # SMALL DELAY
    # =====================================================

    await asyncio.sleep(2)

    # =====================================================
    # ORIGINATE
    # =====================================================

    await originate()

    # =====================================================
    # KEEP ALIVE
    # =====================================================

    while True:
        await asyncio.sleep(1)

# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        log.info("⏹️ STOPPED")

    except Exception as e:

        log.error(f"💀 FATAL ERROR: {e}")

        traceback.log.info_exc()