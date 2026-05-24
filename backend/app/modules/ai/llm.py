import time


class LLMService:

    def stream(
        self,
        text: str
    ):

        print(f"[USER]: {text}")

        response = (
            "Здравствуйте чем могу помочь вам сегодня"
        )

        words = response.split()

        for word in words:

            yield word + " "

            time.sleep(0.15)