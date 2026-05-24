from app.repository.models.base import Base
from app.modules.telephony.caller import AsteriskCaller
from app.modules.telephony.handlers import register_handlers
from app.modules.telephony.main import AriService


async def init_base():
    """Создаёт все таблицы, если их нет."""
    from app.repository.unitofwork import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_telephony(app):
    ari_service = AriService()

    await ari_service.connect()

    ari = ari_service.get()

    caller = AsteriskCaller(ari)

    # IMPORTANT: register events BEFORE system fully runs
    await register_handlers(ari, caller)

    app.state.ari = ari
    app.state.caller = caller
