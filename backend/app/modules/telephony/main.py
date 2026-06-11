from ari_client import AriClient

from app.core.config import config


class AriService:
    def __init__(self):
        self.client = AriClient(
            host=config.ARI_HOST,
            port=config.ARI_PORT,
            ari_user=config.ARI_USER,
            ari_password=config.ARI_PASS,
        )

    async def connect(self):
        await self.client.connect(app=config.ARI_APP, subscribe_to_all=True)

    def get(self):
        return self.client


client = AriService()
