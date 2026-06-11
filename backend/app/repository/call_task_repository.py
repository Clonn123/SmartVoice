from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.models.models import CallTask


class CallTaskRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, task_id: int):

        result = await self.session.execute(
            select(CallTask).where(CallTask.id == task_id)
        )

        return result.scalars().first()

    async def add(self, task: CallTask):

        self.session.add(task)

        await self.session.flush()

        return task
