from functools import lru_cache
from typing import Literal

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
    # A new account has to be able to run something. The cheapest image route
    # costs 10 credits, so the previous default of 5 left every arriving user
    # with a balance that could not buy a single generation.
    welcome_credits: int = 60

    # Observability is opt-in. Production secrets belong in the deployment environment.
    sentry_enabled: bool = False
    sentry_dsn: str = ""
    sentry_environment: str = ""
    sentry_release: str = ""
    sentry_error_sample_rate: float = 1.0
    sentry_traces_sample_rate: float = 0.0
    metrics_enabled: bool = False
    metrics_endpoint_enabled: bool = False
    metrics_bearer_token: str = ""
    readiness_require_redis: bool = True

    # Internal operator surface. Bootstrap IDs are server-only and disabled by default.
    admin_enabled: bool = False
    admin_bootstrap_telegram_ids: str = ""
    admin_rate_limit_per_minute: int = 60

    # Moderation starts in report-only mode. External text moderation is opt-in.
    moderation_mode: Literal["off", "report", "block"] = "report"
    moderation_policy_version: str = "2026-08-01-v1"
    moderation_external_provider: Literal["none", "openai"] = "none"
    moderation_external_failure_policy: Literal["open", "closed"] = "open"
    moderation_max_requests_per_minute: int = 30
    moderation_repeat_violation_threshold: int = 3
    moderation_violation_window_hours: int = 24
    photo_rights_consent_version: str = "2026-08-01-v1"
    openai_moderation_api_key: str = ""
    openai_moderation_model: str = "omni-moderation-latest"
    openai_moderation_base_url: str = "https://api.openai.com/v1"
    openai_moderation_timeout_seconds: float = 10.0

    # Server-owned generation templates and deterministic post-processing.
    server_templates_enabled: bool = True
    template_compositor_enabled: bool = True

    # Multi-operation Veo route. Rollout remains controlled by the DB feature flag.
    veo_extended_step_timeout_seconds: int = 900
    veo_extended_total_timeout_seconds: int = 3600
    veo_extended_step_max_attempts: int = 2

    bot_token: str = ""
    mini_app_url: str = ""
    support_username: str = ""

    # Telegram Stars. Every mutating/reconciliation capability is independently gated.
    payments_enabled: bool = False
    payment_terms_url: str = ""
    payment_terms_version: str = "2026-07-30"
    payment_refund_policy_url: str = ""
    payment_seller_identity: str = ""
    payment_finance_review_confirmed: bool = False
    payment_order_ttl_minutes: int = 30
    stars_refunds_enabled: bool = False
    stars_reconciliation_enabled: bool = False
    stars_canary_telegram_ids: str = ""
    stars_refund_user_daily_limit: int = 2
    stars_refund_operator_daily_limit: int = 20
    stars_refund_retry_limit: int = 3
    stars_refund_processing_timeout_seconds: int = 300
    stars_reconciliation_page_limit: int = 100

    # Recurring Stars subscriptions. Off until the expiry sweep and the cancel path are
    # deployed together: billing without the sweep leaves users on a paid tier after their
    # period ends, and without cancel they cannot stop paying.
    subscriptions_enabled: bool = False
    telegram_update_inbox_batch_size: int = 25
    telegram_update_inbox_max_attempts: int = 10
    telegram_update_inbox_stale_seconds: int = 120

    # Referral MVP. The DB feature flag `referrals` is the rollout/kill switch.
    referral_bot_username: str = ""
    referral_inviter_bonus_credits: int = 5
    referral_invitee_bonus_credits: int = 2
    referral_minimum_purchase_stars: int = 50
    referral_waiting_period_hours: int = 72
    referral_daily_reward_limit: int = 20
    referral_suspicious_daily_attribution_threshold: int = 50

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

    # OpenAI GPT Image is an independent, opt-in image route. The DB feature
    # flag `openai_image` remains disabled until the canary runbook is met.
    openai_image_api_key: str = ""
    openai_image_base_url: str = "https://api.openai.com/v1"
    openai_image_timeout_seconds: float = 120.0
    openai_image_max_output_bytes: int = 20_971_520  # 20 MiB

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
    # Google Gemini native image fallback. Runtime enablement is controlled by
    # the google_image + image_fallback DB feature flags, both off by default.
    google_image_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    google_image_timeout_seconds: int = 120
    google_image_max_output_bytes: int = 20_971_520  # 20 MiB
    google_webhook_signing_secrets: str = ""
    google_webhook_max_age_seconds: int = 300
    video_output_max_bytes: int = 104_857_600  # 100 MiB

    # Hardening (Stage J)
    text_timeout_seconds: int = 120
    stuck_submitting_seconds: int = 180
    # A queued job is waiting for a worker to claim it. If the queue message is
    # lost the job stays queued forever, holding both its reservation and one of
    # the user's concurrent slots, so queued work needs a deadline of its own.
    # Kept well above any plausible backlog: waiting this long has already
    # failed the user, and the recovery is to hand the credits back.
    stuck_queued_seconds: int = 900
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

    @field_validator("sentry_error_sample_rate", "sentry_traces_sample_rate")
    @classmethod
    def validate_sample_rate(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("Sentry sample rates must be between 0 and 1")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def cors_origin_list(settings: Settings | None = None) -> list[str]:
    cfg = settings or get_settings()
    return [
        part.strip().rstrip("/") for part in cfg.cors_origins.split(",") if part.strip().rstrip("/")
    ]


def admin_bootstrap_id_set(settings: Settings | None = None) -> frozenset[int]:
    cfg = settings or get_settings()
    values: set[int] = set()
    for raw in cfg.admin_bootstrap_telegram_ids.split(","):
        candidate = raw.strip()
        if not candidate:
            continue
        if not candidate.isascii() or not candidate.isdigit() or int(candidate) <= 0:
            raise ValueError("ADMIN_BOOTSTRAP_TELEGRAM_IDS must contain positive numeric IDs")
        values.add(int(candidate))
    return frozenset(values)


def stars_canary_id_set(settings: Settings | None = None) -> frozenset[int]:
    cfg = settings or get_settings()
    values: set[int] = set()
    for raw in cfg.stars_canary_telegram_ids.split(","):
        candidate = raw.strip()
        if not candidate:
            continue
        if not candidate.isascii() or not candidate.isdigit() or int(candidate) <= 0:
            raise ValueError("STARS_CANARY_TELEGRAM_IDS must contain positive numeric IDs")
        values.add(int(candidate))
    return frozenset(values)
