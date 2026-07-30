from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_async_database_url(value: str) -> str:
    """Accept Railway/Heroku PostgreSQL URLs in SQLAlchemy async form."""
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    welcome_credits: int = 5

    bot_token: str = ""
    mini_app_url: str = ""
    support_username: str = ""

    # Telegram Stars payments (Stage 5; disabled until economics/legal review)
    payments_enabled: bool = False
    payment_terms_url: str = ""
    payment_terms_version: str = "2026-07-30"
    payment_order_ttl_minutes: int = 30

    database_url: str = "postgresql+asyncpg://kelbet:kelbet@localhost:5433/kelbet"
    redis_url: str = "redis://localhost:6379/0"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    chat_provider: str = "mock"
    chat_credit_cost: int = 1
    chat_max_input_chars: int = 2000
    chat_timeout_seconds: float = 60.0
    prompt_assistant_credit_cost: int = 1
    prompt_assistant_max_input_chars: int = 1200
    prompt_assistant_max_output_chars: int = 3000

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "https://kelbet.ai"
    openrouter_app_title: str = "KELBET AI"

    # Mini App auth (Stage C)
    telegram_auth_max_age_seconds: int = 86400
    session_ttl_seconds: int = 3600
    cors_origins: str = "https://web.telegram.org"
    quote_ttl_seconds: int = 600

    # Object storage (Stage E) — S3-compatible (R2 / MinIO)
    storage_backend: str = "memory"  # memory | s3
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = "kelbet-assets"
    s3_region: str = "auto"
    s3_presign_ttl_seconds: int = 600
    upload_max_bytes: int = 10_485_760  # 10 MiB
    upload_temp_ttl_hours: int = 48

    # Generations / webhooks (Stage F)
    webhook_secret: str = ""
    webhook_max_body_bytes: int = 65_536
    generation_queue_backend: str = "inline"  # inline | arq

    # Runway (Stage H)
    runway_api_key: str = ""
    runway_base_url: str = "https://api.dev.runwayml.com"
    runway_api_version: str = "2024-11-06"
    runway_http_timeout_seconds: float = 60.0
    runway_poll_interval_seconds: int = 5
    runway_poll_jitter_seconds: int = 2
    runway_image_timeout_seconds: int = 600
    runway_video_timeout_seconds: int = 1800
    runway_output_host_allowlist: str = (
        "runwayml.com,runwayusercontent.com,amazonaws.com,cdn.runway.test"
    )

    # Google Veo — independent video fallback route (Stage 4)
    google_api_key: str = ""
    google_video_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    google_video_timeout_seconds: int = 60
    google_video_output_host_allowlist: str = (
        "googleapis.com,googleusercontent.com,storage.googleapis.com"
    )
    google_webhook_signing_secrets: str = ""
    google_webhook_max_age_seconds: int = 300
    video_output_max_bytes: int = 104_857_600  # 100 MiB

    # Hardening (Stage J)
    text_timeout_seconds: int = 120
    stuck_submitting_seconds: int = 180
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 20
    rate_limit_generations_per_minute: int = 30
    rate_limit_prompt_assistant_per_minute: int = 10
    worker_job_timeout_seconds: int = 900
    max_active_generations_per_user: int = 3
    max_active_video_generations_per_user: int = 1
    notification_batch_size: int = 20
    notification_max_attempts: int = 8

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_async_database_url(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def cors_origin_list(settings: Settings | None = None) -> list[str]:
    cfg = settings or get_settings()
    return [part.strip() for part in cfg.cors_origins.split(",") if part.strip()]
