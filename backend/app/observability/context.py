from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any

_metric_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "metric_context",
    default={},
)


def get_metric_context() -> dict[str, Any]:
    return dict(_metric_context.get())


@contextmanager
def bind_metrics(**values: Any):
    current = dict(_metric_context.get())

    for key, value in values.items():
        if value is not None:
            current[key] = value

    token = _metric_context.set(current)

    try:
        yield
    finally:
        _metric_context.reset(token)
