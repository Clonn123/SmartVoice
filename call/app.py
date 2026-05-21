import asyncio
import logging
import socket
import traceback

from ari_client import AriClient, StasisStartEvent

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

# =========================================================
# RTP LISTENER
# =========================================================

def rtp_listener():

    global packet_counter

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sock.bind(("0.0.0.0", RTP_PORT))

    log.info(f"🎧 RTP LISTENING ON {RTP_PORT}")

    while True:

        try:

            data, addr = sock.recvfrom(4096)

            packet_counter += 1

            # не спамим Docker логами
            if packet_counter % 100 == 0:
                log.info(
                    f"📦 RTP packets: {packet_counter}"
                )

        except Exception as e:

            log.error(f"RTP ERROR: {e}")

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

        traceback.print_exc()

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

        traceback.print_exc()

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

        traceback.print_exc()