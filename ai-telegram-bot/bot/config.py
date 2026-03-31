from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    bot_token: SecretStr
    database_url: SecretStr
    redis_url: str
    secret_key: SecretStr

    # ── App behaviour ─────────────────────────────────────────────────────────
    debug: bool = False
    log_level: str = "INFO"

    # ── YooKassa ──────────────────────────────────────────────────────────────
    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = SecretStr("")

    # ── Webhook ───────────────────────────────────────────────────────────────
    webhook_url: str = ""
    webhook_path: str = "/webhook"

    # ── Tariff limits (requests / day) ────────────────────────────────────────
    FREE_REQUESTS_PER_DAY: int = 5
    BASIC_REQUESTS_PER_DAY: int = 100
    PRO_REQUESTS_PER_DAY: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # игнорировать лишние переменные из .env
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env once)."""
    return Settings()  # type: ignore[call-arg]
