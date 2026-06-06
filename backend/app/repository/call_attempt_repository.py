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

    async def list_by_call_task_id(self, call_task_id: int) -> list[CallAttempt]:
        result = await self.session.execute(
            select(CallAttempt)
            .where(CallAttempt.call_task_id == call_task_id)
            .order_by(CallAttempt.attempt_number.asc())
        )

        return list(result.scalars().all())
