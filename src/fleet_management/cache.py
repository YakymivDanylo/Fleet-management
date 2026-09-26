from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from .config import settings
from .resilience import RetryPolicy

_redis: Redis | None = None


def _create_client() -> Redis:
    if not settings.resilience_enabled:
        # Baseline: library defaults (5 s socket timeout, no handling above it).
        return Redis.from_url(settings.redis_url, decode_responses=True)

    timeout = settings.redis_attempt_timeout_ms / 1000
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=timeout,
        socket_connect_timeout=timeout,
        # Retries are owned by resilience.call_with_retry; a second hidden retry
        # layer inside the driver would multiply the number of calls.
        retry=Retry(NoBackoff(), 0),
    )


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = _create_client()
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_retry_policy() -> RetryPolicy | None:
    if not settings.resilience_enabled:
        return None
    return RetryPolicy(
        max_attempts=settings.redis_retry_max_attempts,
        attempt_timeout=settings.redis_attempt_timeout_ms / 1000,
        base_delay=settings.redis_retry_base_delay_ms / 1000,
        max_delay=settings.redis_retry_max_delay_ms / 1000,
    )
