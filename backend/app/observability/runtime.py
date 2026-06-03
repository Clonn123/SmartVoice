from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future

from app.infra.db.gateway import db
from app.observability.handler import configure_metric_logging
from app.observability.writer import metric_event_writer

logger = logging.getLogger(__name__)


class ObservabilityRuntime:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._start_lock = threading.Lock()
        self._is_started = False

    def start(self) -> None:
        with self._start_lock:
            if self._is_started:
                return

            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="observability-runtime",
            )
            self._thread.start()

            self._started.wait(timeout=10)

            if not self._started.is_set():
                raise RuntimeError("Observability runtime failed to start")

            self._is_started = True

    def stop(self) -> None:
        with self._start_lock:
            if not self._is_started or not self._loop:
                return

            future = asyncio.run_coroutine_threadsafe(
                self._async_stop(),
                self._loop,
            )

            future.result(timeout=15)

            self._loop.call_soon_threadsafe(self._loop.stop)

            if self._thread:
                self._thread.join(timeout=10)

            self._loop = None
            self._thread = None
            self._started.clear()
            self._is_started = False

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self._loop = loop

        try:
            loop.run_until_complete(self._async_start())
            self._started.set()
            loop.run_forever()
        except Exception:
            logger.exception("Observability runtime crashed")
            self._started.set()
        finally:
            pending = asyncio.all_tasks(loop)

            for task in pending:
                task.cancel()

            if pending:
                loop.run_until_complete(
                    asyncio.gather(
                        *pending,
                        return_exceptions=True,
                    )
                )

            loop.close()

    async def _async_start(self) -> None:
        await db.start()
        await db.init_schema()

        metric_event_writer.start(db)
        configure_metric_logging(metric_event_writer)

    async def _async_stop(self) -> None:
        await metric_event_writer.stop()
        await db.stop()


observability_runtime = ObservabilityRuntime()
