import asyncio
import logging

import pytest

from fleet_management.resilience import RetryExhaustedError, RetryPolicy, call_with_retry

POLICY = RetryPolicy(max_attempts=3, attempt_timeout=0.2, base_delay=0.05, max_delay=0.4)


class TransientError(Exception):
    pass


class FlakyOperation:
    """Fails with TransientError ``failures`` times, then returns ``result``."""

    def __init__(self, failures: int, result: str = "ok"):
        self.failures = failures
        self.result = result
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise TransientError(f"boom #{self.calls}")
        return self.result


class RecordingSleep:
    """Replaces asyncio.sleep: records requested pauses instead of waiting."""

    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def max_jitter() -> float:
    return 1.0


async def run(operation, sleep, policy: RetryPolicy = POLICY):
    return await call_with_retry(
        operation,
        policy,
        retry_on=(TransientError,),
        name="test-op",
        sleep=sleep,
        rand=max_jitter,
    )


def test_backoff_doubles_per_attempt_and_is_capped():
    assert [POLICY.backoff_delay(n, rand=max_jitter) for n in (1, 2, 3, 4, 5)] == pytest.approx(
        [0.05, 0.1, 0.2, 0.4, 0.4]
    )


def test_jitter_keeps_at_least_half_of_the_exponential_delay():
    assert POLICY.backoff_delay(2, rand=lambda: 0.0) == pytest.approx(0.05)
    assert POLICY.backoff_delay(2, rand=lambda: 0.5) == pytest.approx(0.075)


def test_worst_case_time_is_bounded():
    # 3 attempts * 200 ms timeout + 50 ms + 100 ms pauses
    assert POLICY.worst_case_seconds == pytest.approx(0.75)


@pytest.mark.parametrize("kwargs", [{"max_attempts": 0}, {"attempt_timeout": 0}])
def test_policy_rejects_unbounded_or_meaningless_values(kwargs):
    params = {"max_attempts": 3, "attempt_timeout": 0.2, "base_delay": 0.05, "max_delay": 0.4}
    with pytest.raises(ValueError):
        RetryPolicy(**(params | kwargs))


async def test_success_on_first_attempt_does_not_retry():
    operation, sleep = FlakyOperation(failures=0), RecordingSleep()

    assert await run(operation, sleep) == "ok"
    assert operation.calls == 1
    assert sleep.delays == []


async def test_transient_failure_is_retried_after_backoff():
    operation, sleep = FlakyOperation(failures=1), RecordingSleep()

    assert await run(operation, sleep) == "ok"
    assert operation.calls == 2
    assert sleep.delays == pytest.approx([0.05])


async def test_gives_up_after_max_attempts_with_backoff_between_them(caplog):
    operation, sleep = FlakyOperation(failures=100), RecordingSleep()

    with caplog.at_level(logging.WARNING, logger="fleet_management.resilience"):
        with pytest.raises(RetryExhaustedError) as exc_info:
            await run(operation, sleep)

    assert operation.calls == 3
    assert sleep.delays == pytest.approx([0.05, 0.1])
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, TransientError)
    assert [record.getMessage() for record in caplog.records] == [
        "test-op failed on attempt 1/3: TransientError('boom #1')",
        "test-op failed on attempt 2/3: TransientError('boom #2')",
        "test-op failed on attempt 3/3: TransientError('boom #3')",
    ]


async def test_hanging_call_is_cut_by_attempt_timeout_and_retried():
    calls = 0

    async def hangs_forever():
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()

    policy = RetryPolicy(max_attempts=2, attempt_timeout=0.01, base_delay=0.05, max_delay=0.4)

    with pytest.raises(RetryExhaustedError) as exc_info:
        await run(hangs_forever, RecordingSleep(), policy)

    assert calls == 2
    assert isinstance(exc_info.value.last_error, TimeoutError)


async def test_non_transient_error_is_not_retried():
    calls = 0

    async def broken():
        nonlocal calls
        calls += 1
        raise ValueError("bug, not an outage")

    sleep = RecordingSleep()
    with pytest.raises(ValueError):
        await run(broken, sleep)

    assert calls == 1
    assert sleep.delays == []
