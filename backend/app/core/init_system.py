import logging

from app.repository.models.base import Base
from app.modules.telephony.caller import AsteriskCaller
from app.modules.telephony.handlers import register_handlers
from app.modules.telephony.main import AriService
from app.modules.calls.runtime import get_call_runtime_gateway
from app.core.config import get_settings
from app.modules.llm.factory import get_llm_gateway

logger = logging.getLogger(__name__)


async def init_base():
    """Создаёт все таблицы, если их нет."""
    from app.repository.unitofwork import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_telephony(app):
    ari_service = AriService()

    await ari_service.connect()

    settings = get_settings()
    if settings.call_runtime_provider == "vosk":
        get_call_runtime_gateway()
        logger.info(
            "Vosk model preloaded successfully at startup: model_path=%s sample_rate=%s",
            settings.vosk_model_path,
            settings.vosk_sample_rate,
        )

    # Попытка создать LLM-шлюз и выставить флаг готовности
    try:
        llm_gateway = get_llm_gateway()
        app.state.llm = llm_gateway
        app.state.llm_ready = True
        logger.info(
            "LLM gateway initialized at startup: provider=%s", settings.llm_provider
        )
    except Exception as exc:  # pragma: no cover - best-effort initialization
        app.state.llm = None
        app.state.llm_ready = False
        logger.warning("LLM gateway initialization failed: %s", exc)

    ari = ari_service.get()

    from app.modules.telephony.runtime import set_caller

    caller = AsteriskCaller(ari)
    set_caller(caller)

    # IMPORTANT: register events BEFORE system fully runs
    await register_handlers(ari, caller)

    app.state.ari = ari
    app.state.caller = caller
