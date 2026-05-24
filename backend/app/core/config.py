from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

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


config = Settings()
