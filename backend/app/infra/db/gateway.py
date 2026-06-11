from __future__ import annotations

import json
from typing import Any, Iterable

import asyncpg

from app.core.config import get_settings


class AppDatabaseGateway:
    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        settings = get_settings()

        dsn = (
            f"postgresql://{settings.PG_USER}:{settings.PG_PASS}"
            f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}"
        )

        self._pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=10,
            command_timeout=10,
        )

    async def stop(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def init_schema(self) -> None:
        pool = self._require_pool()

        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS metric_events (
                    id UUID PRIMARY KEY,
                    observed_at TIMESTAMPTZ NOT NULL,

                    name TEXT NOT NULL,
                    component TEXT NOT NULL,

                    trace_id TEXT NULL,
                    job_id TEXT NULL,
                    call_id TEXT NULL,
                    task_id TEXT NULL,

                    attempt_number INTEGER NULL,
                    turn_index INTEGER NULL,

                    provider TEXT NULL,
                    model_name TEXT NULL,

                    status TEXT NULL,
                    error TEXT NULL,

                    duration_ms INTEGER NULL,
                    value_numeric DOUBLE PRECISION NULL,
                    numerator DOUBLE PRECISION NULL,
                    denominator DOUBLE PRECISION NULL,
                    unit TEXT NULL,

                    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_metric_events_observed_at
                ON metric_events (observed_at);
                """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_metric_events_name_observed_at
                ON metric_events (name, observed_at);
                """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_metric_events_call_id
                ON metric_events (call_id);
                """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_metric_events_job_id
                ON metric_events (job_id);
                """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_metric_events_component_observed_at
                ON metric_events (component, observed_at);
                """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_metric_events_attrs_gin
                ON metric_events USING GIN (attrs);
                """)

    async def insert_metric_events(self, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)

        if not rows:
            return

        pool = self._require_pool()

        values = [
            (
                row["id"],
                row["observed_at"],
                row["name"],
                row["component"],
                row.get("trace_id"),
                row.get("job_id"),
                row.get("call_id"),
                row.get("task_id"),
                row.get("attempt_number"),
                row.get("turn_index"),
                row.get("provider"),
                row.get("model_name"),
                row.get("status"),
                row.get("error"),
                row.get("duration_ms"),
                row.get("value_numeric"),
                row.get("numerator"),
                row.get("denominator"),
                row.get("unit"),
                json.dumps(row.get("attrs") or {}, ensure_ascii=False),
            )
            for row in rows
        ]

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO metric_events (
                    id,
                    observed_at,
                    name,
                    component,
                    trace_id,
                    job_id,
                    call_id,
                    task_id,
                    attempt_number,
                    turn_index,
                    provider,
                    model_name,
                    status,
                    error,
                    duration_ms,
                    value_numeric,
                    numerator,
                    denominator,
                    unit,
                    attrs
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20::jsonb
                );
                """,
                values,
            )

    def _require_pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("Database gateway is not started")

        return self._pool


db = AppDatabaseGateway()
