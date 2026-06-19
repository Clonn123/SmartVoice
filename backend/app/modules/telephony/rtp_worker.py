import socket
import audioop
import queue
import threading
import struct
import time

from app.core.config import config
from app.modules.llm.context import DEFAULT_REALTIME_PROMPT, DEFAULT_REALTIME_SCENARIO


class CallContext:
    def __init__(self):
        self.channel_id = None
        self.external_media_channel_id = None
        self.bridge = None
        self.rtp_session = None
        self.remote_addr = None
        self.active = False

        self.answered = False
        self.bot_finished = False
        self.hangup_cause = None
        self.hangup_text = None

        self.call_task_id = None
        self.call_attempt_id = None

        self.llm_prompt = DEFAULT_REALTIME_PROMPT
        self.llm_scenario = DEFAULT_REALTIME_SCENARIO
        self.llm_target = None
        self.llm_metadata = {}
        self.llm_opening_reply = None


class RTPSession:
    def __init__(self):
        self.inbound_audio = queue.Queue()
        self.outbound_audio = queue.Queue()

        self.lock = threading.Lock()
        self.running = False
        self.seq = 0
        self.timestamp = 0
        self.remote_addr = None

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", config.RTP_PORT))
        self.sock.settimeout(0.5)

    def build_rtp(self, payload):
        header = struct.pack(
            "!BBHII",
            0x80,
            0x00,
            self.seq,
            self.timestamp,
            123456,
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
        while self.running:
            try:
                pkt, _ = self.sock.recvfrom(2048)

                payload = self.strip_rtp(pkt)
                pcm = self.pcmu_to_pcm(payload)

                self.inbound_audio.put(pcm)

            except socket.timeout:
                continue

            except OSError:
                break

            except Exception as e:
                if self.running:
                    print("RTP IN ERROR:", e)

    def send_wav_file(self, wav_path):
        import wave

        wf = wave.open(wav_path, "rb")

        frame_size = 160
        next_send = time.time()

        while self.running:
            pcm = wf.readframes(frame_size)

            if not pcm:
                break

            if len(pcm) < 320:
                pcm += b"\x00" * (320 - len(pcm))

            ulaw = audioop.lin2ulaw(pcm, 2)
            packet = self.build_rtp(ulaw)

            if self.remote_addr:
                self.sock.sendto(packet, self.remote_addr)

            next_send += 0.02
            sleep_time = next_send - time.time()

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_send = time.time()

        wf.close()

    def outbound_loop(self):
        while self.running:
            try:
                pcm = self.outbound_audio.get(timeout=0.2)

                if not self.remote_addr:
                    continue

                packet = self.build_rtp(pcm)

                self.sock.sendto(packet, self.remote_addr)

                time.sleep(0.02)

            except queue.Empty:
                continue

            except OSError:
                break

            except Exception as e:
                if self.running:
                    print("RTP OUT ERROR:", e)

    def start(self):
        if self.running:
            return

        self.running = True

        threading.Thread(
            target=self.rtp_listener,
            daemon=True,
        ).start()

        threading.Thread(
            target=self.outbound_loop,
            daemon=True,
        ).start()

    def stop(self):
        if not self.running:
            return

        self.running = False

        try:
            self.sock.close()
        except Exception:
            pass
