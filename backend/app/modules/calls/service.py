from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.core.enums import (
    CallAttemptStatus,
    CallJobStatus,
    CallResult,
    CallStatus,
    DialogSpeaker,
)
from app.modules.calls.runtime import RetryableCallError, get_call_runtime_gateway
from app.modules.calls.schemas import (
    CallAttemptResponse,
    CallTargetInput,
    DialogTurnResponse,
    ProcessCallsRequest,
    ProcessCallsResponse,
    ProcessedCallResult,
)
from app.modules.llm.base import CallMessage, LlmCallContext
from app.modules.llm.context import build_call_context
from app.modules.llm.factory import get_llm_gateway
from app.observability import bind_metrics, metric, metric_span
from app.repository.file_repository import FileCallResultRepository

from app.repository.unitofwork import SqlAlchemyUnitOfWork

from app.repository.models.models import (
    CallTask,
    CallAttempt,
    CallTaskStatus,
    CallAttemptResult,
)

RETRYABLE_RESULTS = {
    CallAttemptResult.NO_ANSWER,
    CallAttemptResult.BUSY,
    CallAttemptResult.REJECTED,
    CallAttemptResult.FAILED,
    CallAttemptResult.ERROR,
}

logger = logging.getLogger(__name__)


class CallService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm_gateway()
        self.call_runtime = get_call_runtime_gateway()
        self.storage = FileCallResultRepository()

    async def process(self, payload: ProcessCallsRequest) -> ProcessCallsResponse:
        job_id = str(uuid4())
        trace_id = str(uuid4())

        metadata = {
            **payload.metadata,
            "max_attempts": payload.max_attempts,
        }

        results: list[ProcessedCallResult] = []

        with bind_metrics(
            trace_id=trace_id,
            job_id=job_id,
            scenario=payload.scenario,
            clients_count=len(payload.clients),
            max_attempts=payload.max_attempts,
        ):
            metric(
                "call_job.started",
                component="calls.service",
                status="started",
                attrs={
                    "scenario": payload.scenario,
                    "clients_count": len(payload.clients),
                    "max_attempts": payload.max_attempts,
                },
            )

            logger.info(
                "Call job started: job_id=%s scenario=%s clients=%s max_attempts=%s",
                job_id,
                payload.scenario,
                len(payload.clients),
                payload.max_attempts,
            )

            with metric_span(
                "call_job.process",
                component="calls.service",
                attrs={
                    "clients_count": len(payload.clients),
                },
            ):
                for target in payload.clients:
                    result = await self._process_target(
                        job_id=job_id,
                        scenario=payload.scenario,
                        prompt=payload.prompt,
                        metadata=metadata,
                        target=target,
                        max_attempts=payload.max_attempts,
                    )

                    results.append(result)

                    logger.info(
                        "Call target finished: job_id=%s call_id=%s phone=%s status=%s result=%s",
                        job_id,
                        result.call_id,
                        result.phone,
                        result.call_status,
                        result.result,
                    )

            response = ProcessCallsResponse(
                job_id=job_id,
                status=CallJobStatus.completed,
                scenario=payload.scenario,
                calls_count=len(payload.clients),
                processed_at=datetime.now(timezone.utc),
                metadata=metadata,
                results=results,
            )

            result_path = await self.storage.save(response)

            metric(
                "call_job.completed",
                component="calls.service",
                status="completed",
                value_numeric=len(results),
                unit="calls",
                attrs={
                    "calls_count": len(payload.clients),
                    "results_file": str(result_path),
                },
            )

            logger.info(
                "Call job completed: job_id=%s results_file=%s", job_id, result_path
            )

            return response

    async def _process_target(
        self,
        job_id: str,
        scenario: str,
        prompt: str,
        metadata: dict[str, Any],
        target: CallTargetInput,
        max_attempts: int,
    ) -> ProcessedCallResult:
        call_id = str(uuid4())
        task_id = target.external_id or target.contract_id or call_id

        attempts: list[CallAttemptResponse] = []

        with bind_metrics(
            job_id=job_id,
            call_id=call_id,
            task_id=task_id,
            phone_present=bool(target.phone_number),
            external_id=target.external_id,
            contract_id=target.contract_id,
            client_name_present=bool(target.client_name),
            contract_type=target.contract_type,
            contract_status=target.contract_status,
            call_type=target.call_type,
        ):
            metric(
                "call_target.started",
                component="calls.service",
                status="started",
            )

            logger.info(
                "Call target started: job_id=%s call_id=%s phone=%s contract_id=%s",
                job_id,
                call_id,
                target.phone_number,
                target.contract_id,
            )

            last_error: str | None = None
            last_retry_status: CallAttemptStatus | None = None

            for attempt_number in range(1, max_attempts + 1):
                started_at = datetime.now(timezone.utc)

                with bind_metrics(attempt_number=attempt_number):
                    metric(
                        "call_attempt.started",
                        component="calls.service",
                        status="started",
                        attrs={
                            "attempt_number": attempt_number,
                            "max_attempts": max_attempts,
                        },
                    )

                    logger.info(
                        "Call attempt started: job_id=%s call_id=%s attempt=%s phone=%s",
                        job_id,
                        call_id,
                        attempt_number,
                        target.phone_number,
                    )

                    try:
                        with metric_span(
                            "call_attempt.process",
                            component="calls.service",
                            attrs={
                                "attempt_number": attempt_number,
                            },
                        ):
                            result = await self._process_answered_attempt(
                                call_id=call_id,
                                job_id=job_id,
                                scenario=scenario,
                                prompt=prompt,
                                metadata=metadata,
                                target=target,
                                attempt_number=attempt_number,
                                started_at=started_at,
                                previous_attempts=attempts,
                            )

                        metric(
                            "call_attempt.answered",
                            component="calls.service",
                            status="answered",
                            attrs={
                                "call_status": str(result.call_status),
                                "result": str(result.result),
                                "dialog_turns": len(result.dialog),
                                "has_recording": bool(result.recording_url),
                            },
                        )

                        metric(
                            "task.completed",
                            component="calls.service",
                            status=str(result.result),
                            attrs={
                                "result": str(result.result),
                                "contract_id": target.contract_id,
                                "external_id": target.external_id,
                            },
                        )

                        return result

                    except RetryableCallError as exc:
                        last_error = str(exc)
                        last_retry_status = exc.attempt_status

                        metric(
                            "call_attempt.retryable",
                            component="calls.service",
                            status=str(exc.attempt_status),
                            error=last_error,
                            attrs={
                                "retryable": True,
                                "raw_payload": exc.raw_payload,
                            },
                        )

                        logger.info(
                            "Call attempt retryable result: job_id=%s call_id=%s attempt=%s status=%s error=%s",
                            job_id,
                            call_id,
                            attempt_number,
                            exc.attempt_status,
                            last_error,
                        )

                        attempts.append(
                            self._attempt_response(
                                attempt_number=attempt_number,
                                status=exc.attempt_status,
                                started_at=started_at,
                                error_message=last_error,
                            )
                        )

                    except Exception as exc:
                        last_error = str(exc)

                        metric(
                            "call_attempt.failed",
                            component="calls.service",
                            status="failed",
                            error=last_error,
                            attrs={
                                "retryable": False,
                            },
                        )

                        logger.exception(
                            "Call attempt failed",
                            extra={
                                "job_id": job_id,
                                "call_id": call_id,
                                "attempt": attempt_number,
                            },
                        )

                        attempts.append(
                            self._attempt_response(
                                attempt_number=attempt_number,
                                status=CallAttemptStatus.failed,
                                started_at=started_at,
                                error_message=last_error,
                            )
                        )

            if last_retry_status in {
                CallAttemptStatus.no_answer,
                CallAttemptStatus.busy,
                CallAttemptStatus.unavailable,
            }:
                metric(
                    "task.failed",
                    component="calls.service",
                    status="no_answer",
                    error=last_error,
                )

                return self._empty_result(
                    call_id=call_id,
                    target=target,
                    call_status=CallStatus.no_answer,
                    result=CallResult.no_answer,
                    attempts=attempts,
                    error_message=last_error or "Client did not answer",
                )

            metric(
                "task.failed",
                component="calls.service",
                status="failed",
                error=last_error,
            )

            return self._empty_result(
                call_id=call_id,
                target=target,
                call_status=CallStatus.failed,
                result=CallResult.failed,
                attempts=attempts,
                error_message=last_error or "All call attempts failed",
            )

    async def _process_answered_attempt(
        self,
        call_id: str,
        job_id: str,
        scenario: str,
        prompt: str,
        metadata: dict[str, Any],
        target: CallTargetInput,
        attempt_number: int,
        started_at: datetime,
        previous_attempts: list[CallAttemptResponse],
    ) -> ProcessedCallResult:
        history: list[CallMessage] = []
        dialog: list[DialogTurnResponse] = []
        target_payload = self._target_payload(call_id, target)

        context = self._build_context(
            prompt, scenario, target_payload, history, metadata
        )

        logger.info("LLM opening request: job_id=%s call_id=%s", job_id, call_id)

        opening_reply = await self.llm.generate_reply(context)

        logger.info(
            "LLM opening response: job_id=%s call_id=%s finish=%s",
            job_id,
            call_id,
            opening_reply.finish_call,
        )

        opening_audio = await self.call_runtime.prepare_audio(opening_reply.message)

        dialog.append(
            DialogTurnResponse(speaker=DialogSpeaker.bot, text=opening_reply.message)
        )
        history.append(CallMessage(role="bot", content=opening_reply.message))

        logger.info(
            "Runtime start call: job_id=%s call_id=%s phone=%s",
            job_id,
            call_id,
            target.phone_number,
        )

        call_session = await self.call_runtime.start_call(
            phone_number=target.phone_number,
            opening_audio_uri=opening_audio.uri,
            client_payload=target_payload,
        )

        for _ in range(self.settings.max_dialogue_turns):
            client_audio = await self.call_runtime.wait_for_customer_audio(
                call_session.call_id
            )

            if client_audio.is_final:
                break

            client_text = await self.call_runtime.recognize_speech(
                client_audio.audio_uri
            )

            logger.info(
                "STT result: job_id=%s call_id=%s text=%s", job_id, call_id, client_text
            )

            dialog.append(
                DialogTurnResponse(speaker=DialogSpeaker.client, text=client_text)
            )
            history.append(CallMessage(role="client", content=client_text))

            context = self._build_context(
                prompt, scenario, target_payload, history, metadata
            )

            logger.info(
                "LLM dialogue request: job_id=%s call_id=%s turns=%s",
                job_id,
                call_id,
                len(history),
            )

            reply = await self.llm.generate_reply(context)

            logger.info(
                "LLM dialogue response: job_id=%s call_id=%s finish=%s",
                job_id,
                call_id,
                reply.finish_call,
            )

            reply_audio = await self.call_runtime.prepare_audio(reply.message)
            await self.call_runtime.play_audio(call_session.call_id, reply_audio.uri)

            dialog.append(
                DialogTurnResponse(speaker=DialogSpeaker.bot, text=reply.message)
            )
            history.append(CallMessage(role="bot", content=reply.message))

            if reply.finish_call:
                break

        logger.info(
            "Runtime finish call: job_id=%s call_id=%s session_id=%s",
            job_id,
            call_id,
            call_session.call_id,
        )

        finished_call = await self.call_runtime.finish_call(call_session.call_id)

        transcription = self._render_transcription(history)

        logger.info("LLM summary request: job_id=%s call_id=%s", job_id, call_id)

        summary = await self.llm.summarize(
            self._build_context(prompt, scenario, target_payload, history, metadata),
            transcription,
        )

        result = self._parse_result(summary.raw_payload.get("result"))

        current_attempt = self._attempt_response(
            attempt_number=attempt_number,
            status=CallAttemptStatus.answered,
            started_at=started_at,
        )

        return ProcessedCallResult(
            call_id=call_id,
            external_id=target.external_id,
            contract_id=target.contract_id,
            phone=target.phone_number,
            client_name=target.client_name,
            call_status=CallStatus.completed,
            result=result,
            attempts=[*previous_attempts, current_attempt],
            dialog=dialog,
            transcription=transcription,
            summary=summary.text,
            recording_url=finished_call.recording_uri,
            payload=target.payload,
            result_payload={
                "llm_summary": summary.raw_payload,
                "runtime": {
                    "call_session": call_session.raw_payload,
                    "finished_call": finished_call.raw_payload,
                },
            },
            error_message=None,
        )

    @staticmethod
    def _build_context(
        prompt: str,
        scenario: str,
        target_payload: dict[str, Any],
        history: list[CallMessage],
        metadata: dict[str, Any],
    ) -> LlmCallContext:
        return build_call_context(
            prompt=prompt,
            scenario=scenario,
            target=target_payload,
            history=history,
            extra_context=metadata,
        )

    @staticmethod
    def _target_payload(call_id: str, target: CallTargetInput) -> dict[str, Any]:
        payload = dict(target.payload)

        payload.update(
            {
                "call_id": call_id,
                "external_id": target.external_id,
                "phone_number": target.phone_number,
                "client_name": target.client_name,
                "contract_id": target.contract_id,
                "contract_type": target.contract_type,
                "contract_status": target.contract_status,
                "call_type": target.call_type,
            }
        )

        return payload

    @staticmethod
    def _attempt_response(
        attempt_number: int,
        status: CallAttemptStatus,
        started_at: datetime,
        error_message: str | None = None,
    ) -> CallAttemptResponse:
        finished_at = datetime.now(timezone.utc)

        return CallAttemptResponse(
            attempt_number=attempt_number,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=int((finished_at - started_at).total_seconds()),
            error_message=error_message,
        )

    @staticmethod
    def _empty_result(
        call_id: str,
        target: CallTargetInput,
        call_status: CallStatus,
        result: CallResult,
        attempts: list[CallAttemptResponse],
        error_message: str,
    ) -> ProcessedCallResult:
        return ProcessedCallResult(
            call_id=call_id,
            external_id=target.external_id,
            contract_id=target.contract_id,
            phone=target.phone_number,
            client_name=target.client_name,
            call_status=call_status,
            result=result,
            attempts=attempts,
            dialog=[],
            transcription=None,
            summary=None,
            recording_url=None,
            payload=target.payload,
            result_payload={},
            error_message=error_message,
        )

    @staticmethod
    def _render_transcription(history: list[CallMessage]) -> str:
        return "\n".join(f"{message.role}: {message.content}" for message in history)

    @staticmethod
    def _parse_result(value: object) -> CallResult:
        if isinstance(value, str):
            try:
                return CallResult(value)
            except ValueError:
                return CallResult.unknown

        return CallResult.unknown


async def create_call_task(
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
        metadata_json=metadata or {},
        max_attempts=max_attempts,
        attempts=0,
        status=CallTaskStatus.PENDING,
        next_attempt_at=datetime.utcnow(),
        completed=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    async with SqlAlchemyUnitOfWork() as uow:
        await uow.call_tasks.add(task)

    return task


async def create_attempt(
    call_task: CallTask,
    celery_task_id: str | None = None,
):
    attempt_number = call_task.attempts + 1

    attempt = CallAttempt(
        call_task_id=call_task.id,
        attempt_number=attempt_number,
        celery_task_id=celery_task_id,
        status="RUNNING",
        started_at=datetime.utcnow(),
    )

    call_task.attempts = attempt_number
    call_task.status = CallTaskStatus.RUNNING
    call_task.updated_at = datetime.utcnow()

    async with SqlAlchemyUnitOfWork() as uow:
        await uow.call_attempts.add(attempt)

    return attempt


async def finish_attempt(
    attempt: CallAttempt,
    result: CallAttemptResult,
    answered: bool = False,
    bot_finished: bool = False,
    channel_id: str | None = None,
    hangup_cause: int | None = None,
    hangup_text: str | None = None,
    error: str | None = None,
):
    attempt.status = "FINISHED"
    attempt.result = result
    attempt.answered = answered
    attempt.bot_finished = bot_finished
    attempt.channel_id = channel_id
    attempt.hangup_cause = hangup_cause
    attempt.hangup_text = hangup_text
    attempt.error = error
    attempt.finished_at = datetime.utcnow()

    return attempt


async def update_call_task_after_attempt(
    call_task: CallTask,
    attempt: CallAttempt,
    retry_delay_seconds: int = 900,
):
    result = CallAttemptResult(attempt.result)

    call_task.last_result = result
    call_task.updated_at = datetime.utcnow()

    if result in {
        CallAttemptResult.SUCCESS,
        CallAttemptResult.BOT_FINISHED,
        CallAttemptResult.ANSWERED,
    }:
        call_task.status = CallTaskStatus.COMPLETED
        call_task.completed = True
        call_task.next_attempt_at = None

    elif call_task.attempts >= call_task.max_attempts:
        call_task.status = CallTaskStatus.FAILED
        call_task.completed = True
        call_task.next_attempt_at = None

    elif result in RETRYABLE_RESULTS:
        call_task.status = CallTaskStatus.RETRY_WAIT
        call_task.completed = False
        call_task.next_attempt_at = datetime.utcnow() + timedelta(
            seconds=retry_delay_seconds
        )

    else:
        call_task.status = CallTaskStatus.FAILED
        call_task.completed = True
        call_task.next_attempt_at = None

    return call_task


def resolve_result_from_hangup(
    *,
    answered: bool,
    bot_finished: bool,
    hangup_cause: int | None,
):
    """
    Asterisk hangup causes:
    16 NORMAL_CLEARING
    17 USER_BUSY
    18 NO_USER_RESPONSE
    19 NO_ANSWER
    21 CALL_REJECTED
    """

    if bot_finished:
        return CallAttemptResult.BOT_FINISHED

    # Если человек поднял трубку, считаем попытку успешной,
    # даже если потом он сам положил трубку.
    if answered:
        return CallAttemptResult.ANSWERED

    if hangup_cause == 17:
        return CallAttemptResult.BUSY

    if hangup_cause in {18, 19}:
        return CallAttemptResult.NO_ANSWER

    if hangup_cause == 21:
        return CallAttemptResult.REJECTED

    return CallAttemptResult.FAILED
