import socket
import audioop
import queue
import threading
import struct
import time

from app.core.config import config


class CallContext:
    def __init__(self):
        self.channel_id = None
        self.bridge = None
        self.rtp_session = None
        self.remote_addr = None  
        self.active = False


class RTPSession:
    def __init__(self):
        # inbound PCM from caller
        self.inbound_audio = queue.Queue()

        # outbound PCM to caller
        self.outbound_audio = queue.Queue()

        self.lock = threading.Lock()
        self.running = False
        self.seq = 0
        self.timestamp = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", config.RTP_PORT))

    def build_rtp(self, payload):
        header = struct.pack(
            "!BBHII",
            0x80,
            0x00,
            self.seq,
            self.timestamp,
            123456
        )

        self.seq = (self.seq + 1) % 65535
        self.timestamp += 160

        return header + payload

    def strip_rtp(self, pkt):
        return pkt[12:]

    def pcmu_to_pcm(self, data):
        return audioop.ulaw2lin(data, 2)

    def pcm_to_pcmu(self, pcm: bytes):
        return audioop.lin2ulaw(pcm, 2)

    def rtp_listener(self):

        while True:
            try:
                pkt, _ = self.sock.recvfrom(2048)

                payload = self.strip_rtp(pkt)
                pcm = self.pcmu_to_pcm(payload)
                self.inbound_audio.put(pcm)
            except Exception as e:
                print(e)

    def send_wav_file(self, wav_path):

        import wave
        import audioop
        import time

        wf = wave.open(wav_path, "rb")

        frame_size = 160  # 20ms @ 8kHz

        next_send = time.time()

        while self.running:

            pcm = wf.readframes(frame_size)

            if not pcm:
                break

            # enforce size
            if len(pcm) < 320:
                pcm += b"\x00" * (320 - len(pcm))

            ulaw = audioop.lin2ulaw(pcm, 2)
            packet = self.build_rtp(ulaw)

            if self.remote_addr:
                self.sock.sendto(packet, self.remote_addr)

            # stable pacing
            next_send += 0.02
            sleep_time = next_send - time.time()

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_send = time.time()

    def outbound_loop(self):

        while self.running:

            try:

                pcm = self.outbound_audio.get()

                packet = self.build_rtp(pcm)

                self.sock.sendto(
                    packet,
                    self.remote_addr
                )

                # RTP pacing
                time.sleep(0.02)

            except Exception as e:
                print("RTP OUT ERROR:", e)

    def start(self):
        self.running = True

        threading.Thread(target=self.rtp_listener, daemon=True).start()
        threading.Thread(
            target=self.outbound_loop,
            daemon=True
        ).start()

    def stop(self):
        self.running = False
        self.sock.close()
