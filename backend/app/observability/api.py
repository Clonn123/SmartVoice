from __future__ import annotations

import logging
from datetime import datetime
from types import TracebackType
from typing import Any

from app.observability.context import get_metric_context
from app.observability.event import MetricEvent, ms_between, utc_now

_metric_logger = logging.getLogger("smartvoice.metrics")

_ID_FIELDS = {
    "trace_id",
    "job_id",
    "call_id",
    "task_id",
    "attempt_number",
    "turn_index",
}


def metric(
    name: str,
    *,
    component: str,
    status: str | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
    value_numeric: float | None = None,
    numerator: float | None = None,
    denominator: float | None = None,
    unit: str | None = None,
    provider: str | None = None,
    model_name: str | None = None,
    attrs: dict[str, Any] | None = None,
    **ids: Any,
) -> None:
    ctx = get_metric_context()

    event = MetricEvent(
        name=name,
        component=component,
        trace_id=ids.get("trace_id") or ctx.get("trace_id"),
        job_id=ids.get("job_id") or ctx.get("job_id"),
        call_id=ids.get("call_id") or ctx.get("call_id"),
        task_id=ids.get("task_id") or ctx.get("task_id"),
        attempt_number=ids.get("attempt_number") or ctx.get("attempt_number"),
        turn_index=ids.get("turn_index") or ctx.get("turn_index"),
        provider=provider,
        model_name=model_name,
        status=status,
        error=error,
        duration_ms=duration_ms,
        value_numeric=value_numeric,
        numerator=numerator,
        denominator=denominator,
        unit=unit,
        attrs={
            **{key: value for key, value in ctx.items() if key not in _ID_FIELDS},
            **(attrs or {}),
        },
    )

    _metric_logger.info(
        name,
        extra={"metric_event": event},
    )


class MetricSpan:
    def __init__(
        self,
        name: str,
        *,
        component: str,
        status: str = "ok",
        provider: str | None = None,
        model_name: str | None = None,
        attrs: dict[str, Any] | None = None,
        **ids: Any,
    ) -> None:
        self.name = name
        self.component = component
        self.status = status
        self.provider = provider
        self.model_name = model_name
        self.attrs = attrs or {}
        self.ids = ids
        self.started_at: datetime | None = None

    def tag(self, **attrs: Any) -> None:
        self.attrs.update(attrs)

    def __enter__(self) -> "MetricSpan":
        self.started_at = utc_now()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._finish(exc)

    async def __aenter__(self) -> "MetricSpan":
        self.started_at = utc_now()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._finish(exc)

    def _finish(self, exc: BaseException | None) -> None:
        ended_at = utc_now()
        started_at = self.started_at or ended_at

        metric(
            self.name,
            component=self.component,
            provider=self.provider,
            model_name=self.model_name,
            status="error" if exc else self.status,
            error=str(exc) if exc else None,
            duration_ms=ms_between(started_at, ended_at),
            attrs={
                **self.attrs,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
            },
            **self.ids,
        )


def metric_span(
    name: str,
    *,
    component: str,
    provider: str | None = None,
    model_name: str | None = None,
    attrs: dict[str, Any] | None = None,
    **ids: Any,
) -> MetricSpan:
    return MetricSpan(
        name,
        component=component,
        provider=provider,
        model_name=model_name,
        attrs=attrs,
        **ids,
    )
