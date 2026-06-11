from __future__ import annotations

import logging

from app.observability.event import MetricEvent
from app.observability.writer import MetricEventWriter


class MetricLoggingHandler(logging.Handler):
    def __init__(self, writer: MetricEventWriter) -> None:
        super().__init__(level=logging.INFO)
        self.writer = writer

    def emit(self, record: logging.LogRecord) -> None:
        event = getattr(record, "metric_event", None)

        if not isinstance(event, MetricEvent):
            return

        self.writer.enqueue(event)


def configure_metric_logging(writer: MetricEventWriter) -> None:
    logger = logging.getLogger("smartvoice.metrics")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    already_configured = any(
        isinstance(handler, MetricLoggingHandler) for handler in logger.handlers
    )

    if not already_configured:
        logger.addHandler(MetricLoggingHandler(writer))
