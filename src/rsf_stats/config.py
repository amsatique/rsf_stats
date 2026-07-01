"""Configuration loaded from the environment / `.env`."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_URL = "https://rallysimfans.hu/rbr"
# LiteSpeed returns 403 without a browser-like User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Application settings (env prefix `RSF_`)."""

    model_config = SettingsConfigDict(
        env_prefix="RSF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    username: str = Field(..., description="RallySimFans username")
    password: str = Field(..., description="RallySimFans password")

    host: str = "0.0.0.0"
    port: int = 8000
    request_delay: float = Field(
        0.5, description="Delay (s) between scraping requests to be gentle on the server"
    )
    cache_ttl: float = Field(
        600, description="How long (s) a scraped snapshot is reused before re-scraping"
    )
    leaderboard_ttl: float = Field(
        21600, description="How long (s) a stage leaderboard is cached (they change slowly)"
    )
    db_path: str = Field("rsf_stats.db", description="SQLite file for history and followed drivers")
    log_level: str = Field("INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")


def get_settings() -> Settings:
    """Instantiate settings (raises a clear error if credentials are missing)."""
    return Settings()  # type: ignore[call-arg]
