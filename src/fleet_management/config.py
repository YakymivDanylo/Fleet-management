from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fleet Management"
    database_url: str
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    telemetry_queue: str = "telemetry"

    # Resilience of the Redis read in GET /vehicles/{id}/state.
    # False reproduces the unprotected baseline ("before") for the fault-injection demo.
    resilience_enabled: bool = True
    # A healthy local Redis answers HGETALL in ~1 ms; 200 ms is far above its p99,
    # so a timeout means the dependency is sick, not just slow.
    redis_attempt_timeout_ms: int = 200
    # 1 call + 2 retries: enough to ride out a transient blip, and the worst case
    # (3 * 200 ms + 50 ms + 100 ms pauses = 750 ms) still fits the 1 s UX budget.
    redis_retry_max_attempts: int = 3
    redis_retry_base_delay_ms: int = 50
    redis_retry_max_delay_ms: int = 400

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
