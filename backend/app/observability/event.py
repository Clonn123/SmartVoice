from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ms_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


@dataclass(slots=True)
class MetricEvent:
    name: str
    component: str

    id: UUID = field(default_factory=uuid4)
    observed_at: datetime = field(default_factory=utc_now)

    trace_id: str | None = None
    job_id: str | None = None
    call_id: str | None = None
    task_id: str | None = None

    attempt_number: int | None = None
    turn_index: int | None = None

    provider: str | None = None
    model_name: str | None = None

    status: str | None = None
    error: str | None = None

    duration_ms: int | None = None
    value_numeric: float | None = None
    numerator: float | None = None
    denominator: float | None = None
    unit: str | None = None

    attrs: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "observed_at": self.observed_at,
            "name": self.name,
            "component": self.component,
            "trace_id": self.trace_id,
            "job_id": self.job_id,
            "call_id": self.call_id,
            "task_id": self.task_id,
            "attempt_number": self.attempt_number,
            "turn_index": self.turn_index,
            "provider": self.provider,
            "model_name": self.model_name,
            "status": self.status,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "value_numeric": self.value_numeric,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "unit": self.unit,
            "attrs": self.attrs,
        }
