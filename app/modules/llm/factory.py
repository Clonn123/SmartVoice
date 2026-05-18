from __future__ import annotations

from app.core.config import get_settings
from app.modules.llm.base import LlmGateway
from app.modules.llm.mock import MockLlmGateway
from app.modules.llm.openrouter import OpenRouterLlmGateway


def get_llm_gateway() -> LlmGateway:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockLlmGateway()
    elif settings.llm_provider == "openrouter":
        return OpenRouterLlmGateway(
            api_key=settings.llm_openrouter_api_key or "",
            model=settings.llm_openrouter_model or "",
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

