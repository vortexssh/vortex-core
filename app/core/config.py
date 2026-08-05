from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "VortexCore"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: PostgresDsn = Field(
        ...,
        description="Async PostgreSQL DSN (postgresql+asyncpg://...)",
    )
    redis_url: RedisDsn = Field(
        ...,
        description="Redis connection URL",
    )

    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    telemetry_ttl_seconds: int = 60

    cors_origins: str = Field(
        default="*",
        description="Comma-separated CORS origins, or *",
    )

    login_rate_limit_per_minute: int = 20
    agent_connect_rate_limit_per_minute: int = 60

    agent_presence_ttl_seconds: int = 90
    ws_heartbeat_interval_seconds: int = 30

    # Public web URL used in verification emails (no trailing slash)
    web_app_url: str = Field(
        default="http://localhost:5173",
        description="Vortex Web base URL for email verification links",
    )
    email_verification_ttl_hours: int = 24

    # SMTP — if SMTP_HOST is empty, verification links are logged instead of sent
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = Field(
        default="noreply@vortex.local",
        description="From address for transactional mail",
    )
    # STARTTLS (typical for port 587). Port 465 always uses implicit SSL.
    smtp_use_tls: bool = True
    # Force SMTP_SSL even when port is not 465
    smtp_use_ssl: bool = False

    # GeoIP — country flags on hosts (agent connect IP or host ip_address)
    geoip_enabled: bool = True
    geoip_db_path: str = Field(
        default="/app/data/GeoLite2-Country.mmdb",
        description="Path to MaxMind GeoLite2-Country database",
    )
    geoip_http_fallback: bool = True
    geoip_cache_ttl_seconds: int = 604_800  # 7 days
    maxmind_license_key: str = Field(
        default="",
        description="Optional MaxMind license key to auto-download GeoLite2 on startup",
    )

    # FX (Frankfurter / ECB — no API key)
    frankfurter_base_url: str = "https://api.frankfurter.app"
    fx_cache_ttl_seconds: int = 43_200  # 12 hours

    # Official Telegram bot (Core sends messages; bot process handles /start link)
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_bot_api_key: str = Field(
        default="",
        description="Shared secret for vortex-telegram-bot → Core internal API",
    )
    telegram_link_ttl_minutes: int = 10

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "dev", "local"}

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip())

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton for process lifetime)."""
    return Settings()
