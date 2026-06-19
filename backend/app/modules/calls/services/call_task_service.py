from datetime import datetime

from app.repository.models.models import (
    CallTask,
)


class CallTaskService:

    @staticmethod
    async def create_call_task(
        uow,
        *,
        phone: str,
        prompt: str | None = None,
        scenario: str | None = None,
        target_payload: dict | None = None,
        metadata: dict | None = None,
        max_attempts: int = 3,
    ):

        task = CallTask(
            phone=phone,
            prompt=prompt,
            scenario=scenario,
            target_payload=target_payload,
            metadata_json=metadata,
            max_attempts=max_attempts,
            attempts=0,
            completed=False,
            created_at=datetime.utcnow(),
        )

        await uow.call_tasks.add(task)

        return task
