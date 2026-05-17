import ari
import threading
import socket
import time

# ---------------- CONFIG ----------------
ARI_URL = "http://127.0.0.1:8088"
ARI_USER = "python"
ARI_PASS = "supersecret"
APP = "python"

RTP_HOST = "172.22.218.236:6000"  # поменяй если нужно

# ---------------- ARI ----------------
client = ari.connect(ARI_URL, ARI_USER, ARI_PASS)

# ---------------- UDP SOCKET ----------------
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 6000))

# ---------------- STATE ----------------
handled = set()


# =========================================================
# RTP DEBUG LISTENER
# =========================================================
def rtp_loop():
    print("🎧 RTP listener started on 6000...")

    while True:
        data, addr = sock.recvfrom(4096)

        print("\n📦 RTP PACKET RECEIVED")
        print("FROM:", addr)
        print("SIZE:", len(data))
        print("HEAD:", data[:20])


# =========================================================
# CREATE MEDIA + BRIDGE
# =========================================================
def create_media(channel):
    print("🔊 Creating external media...")

    try:
        ext = client.channels.externalMedia(
            app=APP,
            external_host=RTP_HOST,
            format="slin16"
        )

        bridge = client.bridges.create(type="mixing")

        bridge.addChannel(channel=channel)
        bridge.addChannel(channel=ext.id)

        print("✅ Bridge created")
        print("EXT MEDIA ID:", ext.id)

    except Exception as e:
        print("❌ externalMedia ERROR:", e)


# =========================================================
# STASIS HANDLER
# =========================================================
def on_stasis_start(channel_obj, ev):
    channel = channel_obj.get("channel")

    name = channel.json.get("name", "")

    print("\n📞 EVENT:", name)

    # игнор всего кроме SIP и RTP
    if not name.startswith("PJSIP/") and not name.startswith("UnicastRTP"):
        print("⛔ IGNORED:", name)
        return

    if channel.id in handled:
        return

    handled.add(channel.id)

    print("✅ NEW CALL:", channel.id)

    channel.answer()

    create_media(channel.id)


# =========================================================
# OUTBOUND CALL
# =========================================================
def call(number):
    print("\n📲 CALLING:", number)

    client.channels.originate(
        endpoint=f"PJSIP/{number}",
        app=APP,
        callerId="AI <999>"
    )


# =========================================================
# START
# =========================================================
client.on_channel_event("StasisStart", on_stasis_start)

threading.Thread(target=rtp_loop, daemon=True).start()

# тестовый звонок
time.sleep(1)
call("100")

client.run(apps=APP)
