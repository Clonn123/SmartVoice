from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        case_sensitive=False,
        extra="ignore",
    )

    # === APP ===
    APP_NAME: str = "SmartVoice"
    APP_ENV: str = "local"
    APP_DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    result_storage_dir: Path = Field(default=Path("data/call_results"))
    recordings_dir: Path = Field(default=Path("data/call_recordings"))

    @field_validator("result_storage_dir", mode="before")
    @classmethod
    def _resolve_result_storage_dir(cls, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    @field_validator("recordings_dir", mode="before")
    @classmethod
    def _resolve_recordings_dir(cls, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    # === CONFIG POSTGRESQL ===
    PG_USER: str
    PG_PASS: str
    PG_HOST: str
    PG_PORT: str
    PG_DB: str

    # === CONFIG ARI ===
    ARI_USER: str
    ARI_PASS: str
    ARI_HOST: str
    ARI_PORT: str
    ARI_APP: str

    # === CONFIG RTP ===
    RTP_HOST: str
    RTP_PORT: int

    # === LLM ===
    llm_provider: str = "mock"
    llm_openrouter_api_key: str | None = None
    llm_openrouter_model: str | None = None
    llm_timeout_seconds: int = 60

    # === CALL RUNTIME ===
    call_runtime_provider: str = "mock"
    max_dialogue_turns: int = 6

    # === VOSK / VAD ===
    vosk_model_path: str | None = None
    vosk_sample_rate: int = 16000
    vosk_fallback_text: str = "да"
    vosk_test_audio_path: str | None = None

    # Backward-compatible uppercase aliases for modules that still use them.
    VOSK_MODEL_PATH: str | None = None
    VOSK_SAMPLE_RATE: int = 16000
    VOSK_FALLBACK_TEXT: str = "да"
    VOSK_TEST_AUDIO_PATH: str | None = None

    @field_validator("VOSK_MODEL_PATH", mode="before")
    @classmethod
    def _alias_vosk_model_path(cls, value, info):
        return value or info.data.get("vosk_model_path") or "models/vosk-model-ru-0.42"

    @field_validator("VOSK_SAMPLE_RATE", mode="before")
    @classmethod
    def _alias_vosk_sample_rate(cls, value, info):
        return value or info.data.get("vosk_sample_rate") or 16000

    @field_validator("VOSK_FALLBACK_TEXT", mode="before")
    @classmethod
    def _alias_vosk_fallback_text(cls, value, info):
        return value or info.data.get("vosk_fallback_text") or "да"

    @field_validator("VOSK_TEST_AUDIO_PATH", mode="before")
    @classmethod
    def _alias_vosk_test_audio_path(cls, value, info):
        return value or info.data.get("vosk_test_audio_path")


config = Settings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
