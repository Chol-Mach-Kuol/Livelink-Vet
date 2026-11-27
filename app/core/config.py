from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"  # development | test | production
    # SQLite by default so the platform runs out of the box; use PostgreSQL in production.
    DATABASE_URL: str = "sqlite:///./livelink_vet.db"
    SECRET_KEY: str = DEFAULT_DEV_SECRET
    # Apply Alembic migrations on startup. Turn off if a deploy step runs `alembic upgrade head`
    # (e.g. with several app instances starting at once).
    AUTO_MIGRATE: bool = True
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # long sessions: field connectivity is intermittent
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # SMS / USSD (Africa's Talking). With no API key, messages are logged instead of sent.
    AT_USERNAME: str = "sandbox"
    AT_API_KEY: str | None = None
    AT_SENDER_ID: str | None = None
    # If set, the USSD callback URL must include ?token=<value> (Africa's Talking does not sign requests).
    USSD_SHARED_SECRET: str | None = None

    # Early-warning tuning
    CLUSTER_RADIUS_KM: float = 25.0
    CLUSTER_WINDOW_DAYS: int = 14
    CLUSTER_MIN_REPORTS: int = 3
    ADVISORY_RADIUS_KM: float = 60.0

    # Minimum group size in anonymised research exports (k-anonymity).
    RESEARCH_EXPORT_K: int = 5


settings = Settings()

if settings.ENVIRONMENT == "production" and settings.SECRET_KEY == DEFAULT_DEV_SECRET:
    raise RuntimeError("SECRET_KEY must be set in production.")
