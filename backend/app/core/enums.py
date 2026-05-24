from __future__ import annotations
from enum import Enum

try:
    # Python 3.11+ provides StrEnum
    from enum import StrEnum  # type: ignore
except Exception:
    class StrEnum(str, Enum):
        pass


class CallJobStatus(StrEnum):
    received = "received"
    running = "running"
    completed = "completed"
    failed = "failed"


class CallStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    no_answer = "no_answer"


class CallAttemptStatus(StrEnum):
    pending = "pending"
    calling = "calling"
    answered = "answered"
    no_answer = "no_answer"
    busy = "busy"
    unavailable = "unavailable"
    failed = "failed"


class CallResult(StrEnum):
    success = "success"
    no_answer = "no_answer"
    failed = "failed"
    client_confirmed = "client_confirmed"
    promised_callback = "promised_callback"
    refused = "refused"
    needs_operator = "needs_operator"
    unknown = "unknown"


class DialogSpeaker(StrEnum):
    bot = "bot"
    client = "client"
    system = "system"
