from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class CallMessage:
    role: Literal["bot", "client", "system"]
    content: str


@dataclass(frozen=True)
class LlmCallContext:
    prompt: str
    scenario: str
    target: dict[str, Any]
    history: list[CallMessage] = field(default_factory=list)
    extra_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LlmReply:
    message: str
    finish_call: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LlmSummary:
    text: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


class LlmGateway(Protocol):
    async def generate_reply(self, context: LlmCallContext) -> LlmReply:
        raise NotImplementedError

    async def summarize(self, context: LlmCallContext, transcript: str) -> LlmSummary:
        raise NotImplementedError
