from ari_client import AriClient

from app.core.config import config
from app.modules.telephony.caller import AsteriskCaller
from app.modules.telephony.handlers import register_handlers


async def create_worker_caller():
    ari = AriClient(
        host=config.ARI_HOST,
        port=config.ARI_PORT,
        ari_user=config.ARI_USER,
        ari_password=config.ARI_PASS,
    )

    await ari.connect(
        app=config.ARI_APP,
        subscribe_to_all=True,
    )

    caller = AsteriskCaller(ari)

    await register_handlers(ari, caller)

    return caller
