from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fleet Management"
    app_version: str = "dev"
    database_url: str
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
