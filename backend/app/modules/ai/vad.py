import webrtcvad
import collections
import time


class VADDetector:

    def __init__(self, mode=0):

        self.vad = webrtcvad.Vad(mode)

        self.speech_frames = 0
        self.silence_frames = 0

        self.is_speaking = False

        self.speech_threshold = 5   # frames
        self.silence_threshold = 15  # frames (~300ms if 30ms frames)

    def process(self, frame: bytes) -> bool:

        is_speech = self.vad.is_speech(frame, 16000)

        if is_speech:
            self.speech_frames += 1
            self.silence_frames = 0
        else:
            self.silence_frames += 1
            self.speech_frames = 0

        # start speech
        if not self.is_speaking and self.speech_frames >= self.speech_threshold:
            self.is_speaking = True

        # end speech
        if self.is_speaking and self.silence_frames >= self.silence_threshold:
            self.is_speaking = False

        return self.is_speaking