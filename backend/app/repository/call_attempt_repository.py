from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.models.models import CallAttempt


class CallAttemptRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, attempt_id: int):

        result = await self.session.execute(
            select(CallAttempt).where(CallAttempt.id == attempt_id)
        )

        return result.scalars().first()

    async def add(self, attempt):

        self.session.add(attempt)

        await self.session.flush()

        return attempt
