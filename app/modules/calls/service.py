from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.core.enums import CallAttemptStatus, CallJobStatus, CallResult, CallStatus, DialogSpeaker
from app.modules.calls.runtime import RetryableCallError, get_call_runtime_gateway
from app.modules.calls.schemas import (
    CallAttemptResponse,
    CallTargetInput,
    DialogTurnResponse,
    ProcessCallsRequest,
    ProcessCallsResponse,
    ProcessedCallResult,
)
from app.modules.calls.storage import JsonCallResultStorage
from app.modules.llm.base import CallMessage, LlmCallContext
from app.modules.llm.factory import get_llm_gateway

logger = logging.getLogger(__name__)


class CallService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm_gateway()
        self.call_runtime = get_call_runtime_gateway()
        self.storage = JsonCallResultStorage()

    async def process(self, payload: ProcessCallsRequest) -> ProcessCallsResponse:
        job_id = str(uuid4())
        metadata = {**payload.metadata, "max_attempts": payload.max_attempts}
        results: list[ProcessedCallResult] = []
        logger.info(
            "Call job started: job_id=%s scenario=%s clients=%s max_attempts=%s",
            job_id,
            payload.scenario,
            len(payload.clients),
            payload.max_attempts,
        )

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
        logger.info("Call job completed: job_id=%s results_file=%s", job_id, result_path)
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
        attempts: list[CallAttemptResponse] = []
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
            logger.info(
                "Call attempt started: job_id=%s call_id=%s attempt=%s phone=%s",
                job_id,
                call_id,
                attempt_number,
                target.phone_number,
            )
            try:
                return await self._process_answered_attempt(
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
            except RetryableCallError as exc:
                last_error = str(exc)
                logger.info(
                    "Call attempt retryable result: job_id=%s call_id=%s attempt=%s status=%s error=%s",
                    job_id,
                    call_id,
                    attempt_number,
                    exc.attempt_status,
                    last_error,
                )
                last_retry_status = exc.attempt_status
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
                logger.exception(
                    "Call attempt failed",
                    extra={"job_id": job_id, "call_id": call_id, "attempt": attempt_number},
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
            return self._empty_result(
                call_id=call_id,
                target=target,
                call_status=CallStatus.no_answer,
                result=CallResult.no_answer,
                attempts=attempts,
                error_message=last_error or "Client did not answer",
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
        context = self._build_context(prompt, scenario, target_payload, history, metadata)

        logger.info("LLM opening request: job_id=%s call_id=%s", job_id, call_id)
        opening_reply = await self.llm.generate_reply(context)
        logger.info("LLM opening response: job_id=%s call_id=%s finish=%s", job_id, call_id, opening_reply.finish_call)
        opening_audio = await self.call_runtime.prepare_audio(opening_reply.message)
        dialog.append(DialogTurnResponse(speaker=DialogSpeaker.bot, text=opening_reply.message))
        history.append(CallMessage(role="bot", content=opening_reply.message))

        logger.info("Runtime start call: job_id=%s call_id=%s phone=%s", job_id, call_id, target.phone_number)
        call_session = await self.call_runtime.start_call(
            phone_number=target.phone_number,
            opening_audio_uri=opening_audio.uri,
            client_payload=target_payload,
        )

        for _ in range(self.settings.max_dialogue_turns):
            client_audio = await self.call_runtime.wait_for_customer_audio(call_session.call_id)
            if client_audio.is_final:
                break

            client_text = await self.call_runtime.recognize_speech(client_audio.audio_uri)
            logger.info("STT result: job_id=%s call_id=%s text=%s", job_id, call_id, client_text)
            dialog.append(DialogTurnResponse(speaker=DialogSpeaker.client, text=client_text))
            history.append(CallMessage(role="client", content=client_text))

            context = self._build_context(prompt, scenario, target_payload, history, metadata)
            logger.info("LLM dialogue request: job_id=%s call_id=%s turns=%s", job_id, call_id, len(history))
            reply = await self.llm.generate_reply(context)
            logger.info("LLM dialogue response: job_id=%s call_id=%s finish=%s", job_id, call_id, reply.finish_call)
            reply_audio = await self.call_runtime.prepare_audio(reply.message)
            await self.call_runtime.play_audio(call_session.call_id, reply_audio.uri)
            dialog.append(DialogTurnResponse(speaker=DialogSpeaker.bot, text=reply.message))
            history.append(CallMessage(role="bot", content=reply.message))

            if reply.finish_call:
                break

        logger.info("Runtime finish call: job_id=%s call_id=%s session_id=%s", job_id, call_id, call_session.call_id)
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
        return LlmCallContext(
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

