from __future__ import annotations

import asyncio
import logging

from app.infra.db.gateway import AppDatabaseGateway
from app.observability.event import MetricEvent

logger = logging.getLogger(__name__)


class MetricEventWriter:
    def __init__(self, batch_size: int = 100, flush_interval_sec: float = 0.5) -> None:
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self._db: AppDatabaseGateway | None = None
        self._queue: asyncio.Queue[MetricEvent] | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping = False

    def start(self, db: AppDatabaseGateway) -> None:
        self._db = db
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=50_000)
        self._stopping = False
        self._task = self._loop.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True

        if self._queue:
            await self._queue.join()

        if self._task:
            await self._task

    def enqueue(self, event: MetricEvent) -> None:
        if not self._loop or not self._queue:
            return

        def put() -> None:
            assert self._queue is not None

            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Metric queue is full. Dropped event: %s", event.name)

        self._loop.call_soon_threadsafe(put)

    async def _run(self) -> None:
        assert self._queue is not None

        batch: list[MetricEvent] = []

        while True:
            if self._stopping and self._queue.empty():
                await self._flush(batch)
                return

            try:
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self.flush_interval_sec,
                )
            except asyncio.TimeoutError:
                await self._flush(batch)
                batch.clear()
                continue

            batch.append(event)

            if len(batch) >= self.batch_size:
                await self._flush(batch)
                batch.clear()

    async def _flush(self, batch: list[MetricEvent]) -> None:
        if not batch:
            return

        assert self._db is not None
        assert self._queue is not None

        try:
            await self._db.insert_metric_events(event.to_row() for event in batch)
        except Exception:
            logger.exception("Failed to write metric events batch")
        finally:
            for _ in batch:
                self._queue.task_done()


metric_event_writer = MetricEventWriter()
