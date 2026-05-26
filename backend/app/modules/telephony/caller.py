from ari_client import AriClient

from app.core.config import config
from app.modules.telephony.rtp_worker import CallContext
from app.modules.ai.pipeline import RealtimePipeline
from app.modules.llm.base import CallMessage, LlmCallContext
from app.modules.llm.factory import get_llm_gateway
from app.modules.llm.context import DEFAULT_REALTIME_PROMPT, DEFAULT_REALTIME_SCENARIO, build_default_realtime_target


class AsteriskCaller:
    def __init__(self, ari):
        self.ari: AriClient = ari
        self.ctx = CallContext()
        self.pipeline = None
        self.llm = get_llm_gateway()

    async def init_call(self, number: str, *, prompt: str | None = None, scenario: str | None = None, target_payload: dict | None = None, metadata: dict | None = None):
        if self.ctx.active:
            raise RuntimeError("Call already running")

        if not number.isdigit():
            raise ValueError("Invalid number")

        # RTP session (ONLY ONE)
        from app.modules.telephony.rtp_worker import RTPSession

        self.ctx.rtp_session = RTPSession()
        self.ctx.rtp_session.start()

        self.ctx.llm_prompt = prompt or DEFAULT_REALTIME_PROMPT
        self.ctx.llm_scenario = scenario or DEFAULT_REALTIME_SCENARIO
        self.ctx.llm_target = target_payload or build_default_realtime_target(number)
        self.ctx.llm_metadata = metadata or {}

        opening_context = LlmCallContext(
            prompt=self.ctx.llm_prompt,
            scenario=self.ctx.llm_scenario,
            target=self.ctx.llm_target,
            history=[],
            extra_context=self.ctx.llm_metadata,
        )

        try:
            opening_reply = await self.llm.generate_reply(opening_context)
            self.ctx.llm_opening_reply = opening_reply.message.strip() or "Здравствуйте! Подскажите, пожалуйста, удобно ли вам сейчас говорить?"
        except Exception:
            self.ctx.llm_opening_reply = "Здравствуйте! Подскажите, пожалуйста, удобно ли вам сейчас говорить?"

        self.pipeline = RealtimePipeline(
            self.ctx.rtp_session,
            call_context=self.ctx,
        )
        self.pipeline.start()

        await self.ari.ari.originate(
            endpoint=f"PJSIP/{number}",
            app_args=config.ARI_APP,
            caller_id="AI Bot <1000>",
        )
