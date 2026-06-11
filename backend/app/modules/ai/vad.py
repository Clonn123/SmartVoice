import audioop
import webrtcvad


class VADDetector:

    def __init__(self, mode=3):

        self.vad = webrtcvad.Vad(mode)

        self.speech_frames = 0
        self.silence_frames = 0

        self.is_speaking = False

        self.speech_threshold = 8
        self.silence_threshold = 20

        self.min_rms = 700

    def process(self, frame: bytes) -> bool:

        rms = audioop.rms(frame, 2)

        if rms < self.min_rms:
            is_speech = False
        else:
            is_speech = self.vad.is_speech(frame, 8000)

        if is_speech:
            self.speech_frames += 1
            self.silence_frames = 0
        else:
            self.silence_frames += 1
            self.speech_frames = 0

        if not self.is_speaking and self.speech_frames >= self.speech_threshold:
            self.is_speaking = True

        if self.is_speaking and self.silence_frames >= self.silence_threshold:
            self.is_speaking = False

        return self.is_speaking
