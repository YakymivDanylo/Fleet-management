import logging

from pydantic import BaseModel, TypeAdapter
from redis import exceptions as redis_errors
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from .config import settings
from .resilience import RetryPolicy

logger = logging.getLogger("fleet_management.cache")

STATIONS_LIST_KEY = "cache:stations:list"
VEHICLES_LIST_KEY = "cache:vehicles:list"

_redis: Redis | None = None


def _create_client() -> Redis:
    if not settings.resilience_enabled:
        return Redis.from_url(settings.redis_url, decode_responses=True)

    timeout = settings.redis_attempt_timeout_ms / 1000
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=timeout,
        socket_connect_timeout=timeout,
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


async def read_through_json[T: BaseModel](
    redis: Redis, key: str, adapter: TypeAdapter[list[T]], load
) -> str:
    """JSON for a list endpoint: from Redis when cached, otherwise built by ``load`` and stored.

    The cache is an optimisation only: any Redis error falls back to the database, and the
    entry expires after ``list_cache_ttl_seconds`` even if an invalidation was missed.
    """
    if not settings.list_cache_enabled:
        return adapter.dump_json(await load()).decode()

    try:
        cached = await redis.get(key)
    except redis_errors.RedisError as exc:
        logger.warning("cache read failed for %s (%r); using the database", key, exc)
        cached = None
    if cached is not None:
        return cached

    payload = adapter.dump_json(await load()).decode()
    try:
        await redis.set(key, payload, ex=settings.list_cache_ttl_seconds)
    except redis_errors.RedisError as exc:
        logger.warning("cache write failed for %s (%r)", key, exc)
    return payload


async def invalidate(redis: Redis, *keys: str) -> None:
    try:
        await redis.delete(*keys)
    except redis_errors.RedisError as exc:
        # The TTL still bounds how long a stale list can be served.
        logger.warning("cache invalidation failed for %s (%r)", keys, exc)
