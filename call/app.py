import time
import socket
import threading
import .ari_client

# =========================================================
# CONFIG
# =========================================================

ARI_URL = "http://asterisk:8088"
ARI_USER = "python"
ARI_PASS = "supersecret"

APP = "main-app"

SIP_ENDPOINT = "PJSIP/100"

RTP_IP = "0.0.0.0"
RTP_PORT = 6000

# =========================================================
# GLOBAL STATE
# =========================================================

client = None
bridge = None
call_channel = None
media_channel = None
call_started = False

# =========================================================
# RTP LISTENER (PURE DEBUG)
# =========================================================

def rtp_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((RTP_IP, RTP_PORT))

    print(f"[RTP] listening on {RTP_IP}:{RTP_PORT}")

    while True:
        data, addr = sock.recvfrom(4096)

        print(f"[RTP] packet {len(data)} bytes from {addr}")

# =========================================================
# STASIS HANDLER
# =========================================================

def on_stasis_start(channel, event):

    global bridge, call_channel, media_channel, call_started

    name = channel.json.get("name", "")

    print(f"\n📞 STASIS START: {name}")

    # ignore media channel
    if "UnicastRTP" in name:
        print("⛔ ignoring RTP channel")
        return

    if call_started:
        print("⛔ call already running")
        return

    call_started = True
    call_channel = channel

    # =====================================================
    # ANSWER CALL
    # =====================================================

    print("📲 answering call")
    channel.answer()

    # =====================================================
    # CREATE BRIDGE
    # =====================================================

    print("🌉 creating bridge")
    bridge = client.bridges.create(type="mixing")

    bridge.addChannel(channel=channel.id)

    print("➕ SIP added to bridge")

    # =====================================================
    # EXTERNAL MEDIA
    # =====================================================

    print("🎧 creating external media")

    media_channel = client.channels.externalMedia(
        app=APP,
        external_host=f"python-ai:{RTP_PORT}",
        format="ulaw"
    )

    bridge.addChannel(channel=media_channel.id)

    print("➕ media added")

    print("\n🚀 AUDIO PIPELINE READY\n")

# =========================================================
# ORIGINATE CALL
# =========================================================

def originate_call():

    print("📡 originating call...")

    try:
        client.channels.originate(
            endpoint=SIP_ENDPOINT,
            app=APP,
            callerId="AI Bot <1000>"
        )

        print("✅ originate sent")

    except Exception as e:
        print("❌ originate error:", e)

# =========================================================
# MAIN
# =========================================================

def main():

    global client

    print("🔌 connecting to ARI...")

    client = ari_client.connect(
        ARI_URL,
        ARI_USER,
        ARI_PASS
    )

    print("✅ connected")

    # register event
    client.on_event("StasisStart", on_stasis_start)

    # start RTP thread
    threading.Thread(target=rtp_loop, daemon=True).start()

    # small delay
    time.sleep(2)

    # start call
    originate_call()

    print("🚀 running event loop")

    client.run(apps=APP)


# =========================================================

if __name__ == "__main__":
    main()