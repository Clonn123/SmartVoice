import json
from vosk import Model, KaldiRecognizer


class VoskSTT:

    def __init__(self, model_path: str, sample_rate=8000):

        self.model = Model(model_path)

        self.rec = KaldiRecognizer(self.model, sample_rate)

        self.rec.SetWords(True)

        self.last_partial = ""

    # -----------------------------
    # STREAM AUDIO (REALTIME)
    # -----------------------------
    
    def accept(self, pcm: bytes):

        if self.rec.AcceptWaveform(pcm):

            result = json.loads(self.rec.Result())

            text = result.get("text", "")

            return {
                "type": "final",
                "text": text
            }

        else:

            partial = json.loads(self.rec.PartialResult())

            text = partial.get("partial", "")

            # dedup
            if text == self.last_partial:
                return None

            self.last_partial = text

            return {
                "type": "partial",
                "text": text
            }

    def reset(self):
        self.rec.Reset()
        self.last_partial = ""