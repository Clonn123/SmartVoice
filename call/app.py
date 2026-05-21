import asyncio
import socket
import logging
from ari_client import AriClient, StasisStartEvent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

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
# RTP DEBUG SOCKET
# =========================================================

def start_rtp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", RTP_PORT))

    log.info(f"RTP listening on {RTP_PORT}")

    while True:
        data, addr = sock.recvfrom(4096)
        log.info(f"RTP {len(data)} bytes from {addr}")

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

    log.info(f"StasisStart: {event.channel.id}")

    channel = event.channel

    await channel.answer()

    # =====================================================
    # BRIDGE
    # =====================================================

    bridge = await client.ari.create_bridge(type="mixing")
    await bridge.add_channel(channel.id)

    log.info("Bridge created + channel added")

    # =====================================================
    # EXTERNAL MEDIA
    # =====================================================

    media = await client.ari.create_external_media(
        external_host=f"{RTP_HOST}:{RTP_PORT}",
        format="ulaw"
    )

    await bridge.add_channel(media.id)

    log.info(f"External media: {media.id}")

# =========================================================
# ORIGINATE
# =========================================================

async def originate():
    log.info("Originating call...")

    await client.ari.originate(
        endpoint=SIP_ENDPOINT,
        app_args=APP,
        caller_id="AI <1000>"
    )

# =========================================================
# MAIN
# =========================================================

async def main():

    # RTP thread
    import threading
    threading.Thread(target=start_rtp_listener, daemon=True).start()

    # connect ARI (ВАЖНО: это await)
    await client.connect(app=APP, subscribe_to_all=True)

    log.info("ARI connected")

    # originate call
    await originate()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping...")
        await client.disconnect()

# =========================================================

if __name__ == "__main__":
    asyncio.run(main())