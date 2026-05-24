from ari_client import AriClient

from app.core.config import config
from app.modules.telephony.rtp_worker import CallContext
from app.modules.ai.pipeline import RealtimePipeline


class AsteriskCaller:
    def __init__(self, ari):
        self.ari: AriClient = ari
        self.ctx = CallContext()
        self.pipeline = None

    async def init_call(self, number: str):
        if self.ctx.active:
            raise RuntimeError("Call already running")

        if not number.isdigit():
            raise ValueError("Invalid number")

        # RTP session (ONLY ONE)
        from app.modules.telephony.rtp_worker import RTPSession

        self.ctx.rtp_session = RTPSession()
        self.ctx.rtp_session.start()

        self.pipeline = RealtimePipeline(
            self.ctx.rtp_session
        )
        self.pipeline.start()

        await self.ari.ari.originate(
            endpoint=f"PJSIP/{number}",
            app_args=config.ARI_APP,
            caller_id="AI Bot <1000>",
        )
