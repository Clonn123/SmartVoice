import asyncio
import logging
import time
from datetime import datetime

from celery.signals import worker_process_init, worker_process_shutdown

from app.core.celery import celery
from app.modules.calls.call_task_ops import (
    create_attempt,
    finish_attempt,
    resolve_result_from_hangup,
    update_call_task_after_attempt,
)
from app.modules.telephony.factory import create_worker_caller
from app.observability import (
    bind_metrics,
    metric,
    metric_span,
    ms_between,
    observability_runtime,
    utc_now,
)
from app.repository.models.models import CallAttemptResult
from app.repository.unitofwork import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)

CALL_START_TIMEOUT_SECONDS = 40
CALL_TIMEOUT_SECONDS = 15 * 60
RETRY_DELAY_SECONDS = 15 * 60


@worker_process_init.connect
def start_observability_for_worker(**kwargs):
    observability_runtime.start()


@worker_process_shutdown.connect
def stop_observability_for_worker(**kwargs):
    observability_runtime.stop()


@celery.task(
    bind=True,
    name="app.modules.calls.tasks.run_call_task",
)
def run_call_task(self, call_task_id: int):
    observability_runtime.start()

    with bind_metrics(
        trace_id=self.request.id,
        task_id=str(call_task_id),
        celery_task_id=self.request.id,
    ):
        metric(
            "call_task.celery_received",
            component="calls.tasks",
            status="received",
            attrs={
                "call_task_id": call_task_id,
                "celery_task_id": self.request.id,
            },
        )

        return asyncio.run(
            _run_call_task_async(
                celery_task=self,
                call_task_id=call_task_id,
            )
        )


async def _run_call_task_async(celery_task, call_task_id: int):
    with bind_metrics(
        trace_id=celery_task.request.id,
        task_id=str(call_task_id),
        celery_task_id=celery_task.request.id,
    ):
        metric(
            "call_task.started",
            component="calls.tasks",
            status="started",
            attrs={
                "call_task_id": call_task_id,
            },
        )

        async with metric_span(
            "call_task.load",
            component="calls.tasks",
            attrs={
                "call_task_id": call_task_id,
            },
        ):
            async with SqlAlchemyUnitOfWork() as uow:
                call_task = await uow.call_tasks.get(call_task_id)

                if not call_task:
                    metric(
                        "call_task.not_found",
                        component="calls.tasks",
                        status="not_found",
                        attrs={
                            "call_task_id": call_task_id,
                        },
                    )

                    return {"error": "CallTask not found"}

                if call_task.completed:
                    metric(
                        "call_task.already_completed",
                        component="calls.tasks",
                        status="already_completed",
                        attrs={
                            "call_task_id": call_task_id,
                            "status": call_task.status,
                            "attempts": call_task.attempts,
                        },
                    )

                    return {"status": "already_completed"}

                if (
                    call_task.next_attempt_at
                    and call_task.next_attempt_at > datetime.utcnow()
                ):
                    countdown = int(
                        (call_task.next_attempt_at - datetime.utcnow()).total_seconds()
                    )

                    metric(
                        "call_task.retry_delayed",
                        component="calls.tasks",
                        status="retry_delayed",
                        value_numeric=countdown,
                        unit="seconds",
                        attrs={
                            "call_task_id": call_task_id,
                            "next_attempt_at": call_task.next_attempt_at.isoformat(),
                            "countdown": countdown,
                        },
                    )

                    raise celery_task.retry(countdown=max(countdown, 1))

                attempt = await create_attempt(
                    call_task=call_task,
                    celery_task_id=celery_task.request.id,
                )

                attempt_id = attempt.id

                attempt_number = getattr(attempt, "attempt_number", None) or getattr(
                    call_task, "attempts", None
                )

                metric(
                    "call_attempt.created",
                    component="calls.tasks",
                    status="created",
                    attempt_number=attempt_number,
                    attrs={
                        "call_task_id": call_task.id,
                        "attempt_id": attempt_id,
                        "celery_task_id": celery_task.request.id,
                    },
                )

                call_data = {
                    "id": call_task.id,
                    "phone": call_task.phone,
                    "prompt": call_task.prompt,
                    "scenario": call_task.scenario,
                    "target_payload": call_task.target_payload,
                    "metadata_json": call_task.metadata_json,
                }

    with bind_metrics(
        trace_id=celery_task.request.id,
        task_id=str(call_task_id),
        attempt_id=attempt_id,
        attempt_number=attempt_number,
        scenario=call_data.get("scenario"),
        phone_present=bool(call_data.get("phone")),
    ):
        try:
            async with metric_span(
                "call_attempt.run_single_call",
                component="calls.tasks",
                attempt_number=attempt_number,
                attrs={
                    "call_task_id": call_task_id,
                    "attempt_id": attempt_id,
                    "scenario": call_data.get("scenario"),
                },
            ):
                result_payload = await _run_single_call(
                    call_data=call_data,
                    attempt_id=attempt_id,
                )

            result = resolve_result_from_hangup(
                answered=result_payload["answered"],
                bot_finished=result_payload["bot_finished"],
                hangup_cause=result_payload["hangup_cause"],
            )

            error_text = None

            metric(
                "call_attempt.result_resolved",
                component="calls.tasks",
                status=str(result),
                attrs={
                    "call_task_id": call_task_id,
                    "attempt_id": attempt_id,
                    "answered": result_payload["answered"],
                    "bot_finished": result_payload["bot_finished"],
                    "channel_id": result_payload["channel_id"],
                    "hangup_cause": result_payload["hangup_cause"],
                    "hangup_text": result_payload["hangup_text"],
                },
            )

        except Exception as exc:
            logger.exception(
                "Call task %s failed on attempt %s",
                call_task_id,
                attempt_id,
            )

            metric(
                "call_attempt.exception",
                component="calls.tasks",
                status="error",
                error=str(exc),
                attrs={
                    "call_task_id": call_task_id,
                    "attempt_id": attempt_id,
                },
            )

            result_payload = {
                "answered": False,
                "bot_finished": False,
                "channel_id": None,
                "hangup_cause": None,
                "hangup_text": None,
            }

            result = CallAttemptResult.ERROR
            error_text = str(exc)

        async with metric_span(
            "call_attempt.persist_result",
            component="calls.tasks",
            attempt_number=attempt_number,
            attrs={
                "call_task_id": call_task_id,
                "attempt_id": attempt_id,
            },
        ):
            async with SqlAlchemyUnitOfWork() as uow:
                call_task = await uow.call_tasks.get(call_task_id)
                attempt = await uow.call_attempts.get(attempt_id)

                await finish_attempt(
                    attempt=attempt,
                    result=result,
                    answered=result_payload["answered"],
                    bot_finished=result_payload["bot_finished"],
                    channel_id=result_payload["channel_id"],
                    hangup_cause=result_payload["hangup_cause"],
                    hangup_text=result_payload["hangup_text"],
                    error=error_text,
                    dialog=result_payload.get("dialog"),
                    recording_path=result_payload.get("recording_path"),
                )

                await update_call_task_after_attempt(
                    call_task=call_task,
                    attempt=attempt,
                    retry_delay_seconds=RETRY_DELAY_SECONDS,
                )

                response = {
                    "call_task_id": call_task.id,
                    "attempt_id": attempt.id,
                    "result": attempt.result,
                    "status": call_task.status,
                    "attempts": call_task.attempts,
                    "completed": call_task.completed,
                    "next_attempt_at": call_task.next_attempt_at,
                }

                should_retry = bool(
                    not call_task.completed and call_task.next_attempt_at
                )

                if should_retry:
                    countdown = int(
                        (call_task.next_attempt_at - datetime.utcnow()).total_seconds()
                    )
                    retry_task_id = call_task.id
                else:
                    countdown = None
                    retry_task_id = None

        metric(
            "call_task.after_attempt_updated",
            component="calls.tasks",
            status=str(response["status"]),
            attrs={
                "call_task_id": response["call_task_id"],
                "attempt_id": response["attempt_id"],
                "result": str(response["result"]),
                "status": str(response["status"]),
                "attempts": response["attempts"],
                "completed": response["completed"],
                "next_attempt_at": (
                    response["next_attempt_at"].isoformat()
                    if response["next_attempt_at"]
                    else None
                ),
            },
        )

        if retry_task_id:
            metric(
                "call_task.retry_scheduled",
                component="calls.tasks",
                status="retry_scheduled",
                value_numeric=countdown,
                unit="seconds",
                attrs={
                    "call_task_id": retry_task_id,
                    "attempt_id": attempt_id,
                    "countdown": countdown,
                },
            )

            run_call_task.apply_async(
                args=[retry_task_id],
                countdown=max(countdown, 1),
            )

        else:
            metric(
                "call_task.finished",
                component="calls.tasks",
                status=str(response["status"]),
                attrs={
                    "call_task_id": response["call_task_id"],
                    "attempt_id": response["attempt_id"],
                    "result": str(response["result"]),
                    "completed": response["completed"],
                },
            )

        return response


async def _run_single_call(
    *,
    call_data: dict,
    attempt_id: int,
):
    caller = None
    result: dict | None = None

    with bind_metrics(
        task_id=str(call_data["id"]),
        attempt_id=attempt_id,
        scenario=call_data.get("scenario"),
        phone_present=bool(call_data.get("phone")),
    ):
        async with metric_span(
            "caller.create",
            component="calls.tasks",
            attrs={
                "call_task_id": call_data["id"],
                "attempt_id": attempt_id,
            },
        ):
            caller = await create_worker_caller()

        try:
            async with metric_span(
                "caller.init_call",
                component="calls.tasks",
                attrs={
                    "call_task_id": call_data["id"],
                    "attempt_id": attempt_id,
                    "scenario": call_data["scenario"],
                    "phone_present": bool(call_data["phone"]),
                },
            ):
                await caller.init_call(
                    call_data["phone"],
                    prompt=call_data["prompt"],
                    scenario=call_data["scenario"],
                    target_payload=call_data["target_payload"],
                    metadata=call_data["metadata_json"],
                    call_task_id=call_data["id"],
                    call_attempt_id=attempt_id,
                )

            metric(
                "call.start_requested",
                component="calls.tasks",
                status="requested",
                attrs={
                    "call_task_id": call_data["id"],
                    "attempt_id": attempt_id,
                },
            )

            start_wait_started_at = utc_now()
            start_wait = time.time()

            async with metric_span(
                "call.wait_start",
                component="calls.tasks",
                attrs={
                    "call_task_id": call_data["id"],
                    "attempt_id": attempt_id,
                    "timeout_seconds": CALL_START_TIMEOUT_SECONDS,
                },
            ):
                while time.time() - start_wait < CALL_START_TIMEOUT_SECONDS:
                    ctx = caller.ctx

                    if (
                        getattr(ctx, "started", False)
                        or getattr(ctx, "answered", False)
                        or getattr(ctx, "channel_id", None)
                    ):
                        break

                    await asyncio.sleep(0.2)

            ctx = caller.ctx

            if (
                not getattr(ctx, "started", False)
                and not getattr(ctx, "answered", False)
                and not getattr(ctx, "channel_id", None)
            ):
                finished_at = utc_now()

                metric(
                    "call.start_timeout",
                    component="calls.tasks",
                    status="timeout",
                    duration_ms=ms_between(start_wait_started_at, finished_at),
                    attrs={
                        "call_task_id": call_data["id"],
                        "attempt_id": attempt_id,
                        "timeout_seconds": CALL_START_TIMEOUT_SECONDS,
                    },
                )

                result = {
                    "answered": False,
                    "bot_finished": False,
                    "channel_id": None,
                    "hangup_cause": None,
                    "hangup_text": "CALL_START_TIMEOUT",
                }
                return result

            channel_id = getattr(ctx, "channel_id", None)

            metric(
                "call.started",
                component="calls.tasks",
                call_id=str(channel_id) if channel_id else None,
                status="started",
                attrs={
                    "call_task_id": call_data["id"],
                    "attempt_id": attempt_id,
                    "channel_id": channel_id,
                    "answered": bool(getattr(ctx, "answered", False)),
                },
            )

            call_wait_started_at = utc_now()
            started = time.time()

            async with metric_span(
                "call.wait_finish",
                component="calls.tasks",
                call_id=str(channel_id) if channel_id else None,
                attrs={
                    "call_task_id": call_data["id"],
                    "attempt_id": attempt_id,
                    "channel_id": channel_id,
                    "timeout_seconds": CALL_TIMEOUT_SECONDS,
                },
            ):
                while time.time() - started < CALL_TIMEOUT_SECONDS:
                    ctx = caller.ctx

                    if getattr(ctx, "finished", False):
                        break

                    await asyncio.sleep(0.5)

            ctx = caller.ctx

            result = {
                "answered": bool(getattr(ctx, "answered", False)),
                "bot_finished": bool(getattr(ctx, "bot_finished", False)),
                "channel_id": getattr(ctx, "channel_id", None),
                "hangup_cause": getattr(ctx, "hangup_cause", None),
                "hangup_text": getattr(ctx, "hangup_text", None),
            }

            if not getattr(ctx, "finished", False):
                result["hangup_text"] = "CALL_TIMEOUT"

                metric(
                    "call.timeout",
                    component="calls.tasks",
                    call_id=str(result["channel_id"]) if result["channel_id"] else None,
                    status="timeout",
                    duration_ms=ms_between(call_wait_started_at, utc_now()),
                    attrs={
                        "call_task_id": call_data["id"],
                        "attempt_id": attempt_id,
                        "channel_id": result["channel_id"],
                        "timeout_seconds": CALL_TIMEOUT_SECONDS,
                    },
                )

            if result["answered"]:
                metric(
                    "call.connected",
                    component="calls.tasks",
                    call_id=str(result["channel_id"]) if result["channel_id"] else None,
                    status="connected",
                    attrs={
                        "call_task_id": call_data["id"],
                        "attempt_id": attempt_id,
                        "channel_id": result["channel_id"],
                    },
                )

            metric(
                "call.finished",
                component="calls.tasks",
                call_id=str(result["channel_id"]) if result["channel_id"] else None,
                status="finished" if getattr(ctx, "finished", False) else "timeout",
                attrs={
                    "call_task_id": call_data["id"],
                    "attempt_id": attempt_id,
                    "answered": result["answered"],
                    "bot_finished": result["bot_finished"],
                    "channel_id": result["channel_id"],
                    "hangup_cause": result["hangup_cause"],
                    "hangup_text": result["hangup_text"],
                },
            )

            return result

        finally:
            if caller:
                if result is not None:
                    artifacts = caller.collect_call_artifacts()
                    result["dialog"] = artifacts["dialog"]
                    result["recording_path"] = artifacts["recording_path"]

                try:
                    with metric_span(
                        "caller.cleanup",
                        component="calls.tasks",
                        attrs={
                            "call_task_id": call_data["id"],
                            "attempt_id": attempt_id,
                        },
                    ):
                        caller.cleanup_call()

                except Exception as exc:
                    metric(
                        "caller.cleanup",
                        component="calls.tasks",
                        status="error",
                        error=str(exc),
                        attrs={
                            "call_task_id": call_data["id"],
                            "attempt_id": attempt_id,
                        },
                    )

                    print("CALLER CLEANUP ERROR:", exc)

                await _close_ari_safely(caller)


async def _close_ari_safely(caller):
    ari = getattr(caller, "ari", None)

    if not ari:
        return

    async with metric_span(
        "ari.close",
        component="calls.tasks",
    ):
        for method_name in ("disconnect", "close", "aclose"):
            method = getattr(ari, method_name, None)

            if not method:
                continue

            try:
                result = method()

                if asyncio.iscoroutine(result):
                    await result

                metric(
                    "ari.closed",
                    component="calls.tasks",
                    status="closed",
                    attrs={
                        "method": method_name,
                    },
                )

                return

            except Exception as exc:
                metric(
                    "ari.close_method_error",
                    component="calls.tasks",
                    status="error",
                    error=str(exc),
                    attrs={
                        "method": method_name,
                    },
                )

                print(f"ARI {method_name.upper()} ERROR:", exc)

        client = getattr(ari, "client", None)

        if client:
            try:
                await client.aclose()

                metric(
                    "ari.closed",
                    component="calls.tasks",
                    status="closed",
                    attrs={
                        "method": "client.aclose",
                    },
                )

            except Exception as exc:
                metric(
                    "ari.close_client_error",
                    component="calls.tasks",
                    status="error",
                    error=str(exc),
                    attrs={
                        "method": "client.aclose",
                    },
                )
