"""Bounded retry with per-attempt timeout and exponential backoff with jitter.

Used to protect calls to external dependencies (Redis). Retrying is always
finite: at most ``max_attempts`` calls, each capped by ``attempt_timeout``,
separated by growing randomized pauses, so a struggling dependency is never
hammered by a synchronous retry storm.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger("fleet_management.resilience")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    attempt_timeout: float
    base_delay: float
    max_delay: float

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.attempt_timeout <= 0:
            raise ValueError("attempt_timeout must be > 0")

    def backoff_delay(self, attempt: int, rand: Callable[[], float] = random.random) -> float:
        """Pause after the failed ``attempt`` (1-based): equal jitter over exponential backoff.

        The exponential part doubles per attempt (capped by ``max_delay``); the
        jitter keeps at least half of it and randomizes the rest so that many
        clients failing at the same moment do not retry in lockstep.
        """
        exponential = min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
        return exponential / 2 + rand() * exponential / 2

    @property
    def worst_case_seconds(self) -> float:
        """Upper bound of time spent before giving up (all attempts time out)."""
        pauses = sum(
            min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
            for attempt in range(1, self.max_attempts)
        )
        return self.max_attempts * self.attempt_timeout + pauses


class RetryExhaustedError(Exception):
    """Raised when every attempt allowed by the policy has failed."""

    def __init__(self, operation: str, attempts: int, last_error: BaseException):
        super().__init__(f"{operation} failed after {attempts} attempts: {last_error!r}")
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error


async def call_with_retry[T](
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    retry_on: tuple[type[BaseException], ...],
    name: str,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rand: Callable[[], float] = random.random,
) -> T:
    """Run ``operation`` until it succeeds or the policy is exhausted.

    Only exceptions listed in ``retry_on`` (plus the per-attempt timeout) are
    retried; anything else is a bug or a permanent error and propagates at once.
    """
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await asyncio.wait_for(operation(), timeout=policy.attempt_timeout)
        except (TimeoutError, *retry_on) as exc:
            logger.warning(
                "%s failed on attempt %d/%d: %r", name, attempt, policy.max_attempts, exc
            )
            if attempt == policy.max_attempts:
                raise RetryExhaustedError(name, attempt, exc) from exc
            await sleep(policy.backoff_delay(attempt, rand))

    raise AssertionError("unreachable: RetryPolicy guarantees max_attempts >= 1")
