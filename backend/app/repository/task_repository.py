from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4

from app.repository.models.queue_call import TaskQueue


class TaskQueueRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get(self, task_id: str) -> Optional[TaskQueue]:
        result = await self.session.execute(
            select(TaskQueue).
            where(TaskQueue.id == task_id)
        )
        return result.scalars().first()

    async def create_task(self, phone: str) -> Optional[TaskQueue]:
        new_task = TaskQueue(id=str(uuid4()), phone=phone)

        self.session.add(new_task)
        return new_task

    async def update_task_status(self, task_id: str, task_status: str) -> bool:
        task: TaskQueue = await self._get(task_id=task_id)

        if not task:
            raise Exception("Нет такой таски")

        task.status = task_status

        return True

    async def update_task_error(self, task_id: str, task_error: str) -> bool:
        task: TaskQueue = await self._get(task_id=task_id)

        if not task:
            raise Exception("Нет такой таски")

        task.status = "FAIL"
        task.error = task_error

        return True
