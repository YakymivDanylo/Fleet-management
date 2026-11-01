import os
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

Environment = Literal["sandbox", "production"]

MIN_PRODUCTION_SECRET_LENGTH = 32

# Suffixes a database name may carry in each environment. The `_test` suffix is allowed in
# sandbox only, so pytest can use its own database without ever being allowed in production.
_ALLOWED_DB_SUFFIXES: dict[str, tuple[str, ...]] = {
    "sandbox": ("_sandbox", "_test"),
    "production": ("_production",),
}


def _env_file() -> str:
    """`.env.sandbox` or `.env.production`, chosen by APP_ENV (sandbox when unset)."""
    return f".env.{os.getenv('APP_ENV', 'sandbox')}"


class Settings(BaseSettings):
    app_env: Environment = "sandbox"
    debug: bool = False

    app_name: str = "Fleet Management"
    app_version: str = "dev"
    database_url: str
    rabbitmq_url: str = "amqp://localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    telemetry_queue: str = "telemetry"

    resilience_enabled: bool = True

    redis_attempt_timeout_ms: int = 200

    redis_retry_max_attempts: int = 3
    redis_retry_base_delay_ms: int = 50
    redis_retry_max_delay_ms: int = 400

    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _check_environment_rules(self) -> Self:
        self._check_database_matches_environment()
        if self.is_production:
            self._check_production_safety()
        return self

    def _check_database_matches_environment(self) -> None:
        db_name = make_url(self.database_url).database or ""
        suffixes = _ALLOWED_DB_SUFFIXES[self.app_env]
        if not db_name.endswith(suffixes):
            raise ValueError(
                f"APP_ENV={self.app_env} requires a database name ending with "
                f"{' or '.join(suffixes)}, got {db_name!r}; refusing to start against "
                "another environment's database"
            )

    def _check_production_safety(self) -> None:
        if self.debug:
            raise ValueError("DEBUG must be false when APP_ENV=production")
        if not self.jwt_secret_key or len(self.jwt_secret_key) < MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY (at least {MIN_PRODUCTION_SECRET_LENGTH} characters) "
                "is required when APP_ENV=production"
            )


settings = Settings()
