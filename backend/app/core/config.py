from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartVoice"
    app_env: str = "local"
    debug: bool = Field(default=True, validation_alias="APP_DEBUG")
    log_level: str = "INFO"

    result_storage_dir: str = "data/call_results"

    llm_provider: str = "mock"
    llm_model: str | None = None
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_openrouter_api_key: str | None = None
    llm_openrouter_model: str | None = Field(
        default=None,
        description="OpenRouter model name, e.g. openai/gpt-4-turbo or meta-llama/llama-2-70b-chat",
    )
    call_runtime_provider: str = "mock"
    vosk_model_path: str | None = Field(
        default=None,
        description="Путь к каталогу модели Vosk, если CALL_RUNTIME_PROVIDER=vosk",
    )
    vosk_sample_rate: int = Field(
        default=16000,
        ge=8000,
        le=48000,
        description="Базовая частота дискретизации Vosk для stream-режима",
    )
    vosk_fallback_text: str = Field(
        default="да",
        description="Текст-заглушка, если распознавание не удалось",
    )
    vosk_test_audio_path: str | None = Field(
        default=None,
        description="Путь к WAV-файлу для локального теста Vosk runtime",
    )
    max_dialogue_turns: int = Field(default=6, ge=1)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()



