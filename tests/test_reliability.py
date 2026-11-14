import pytest

from careflow.config import (
    BREAKER_COOLDOWN_SECONDS,
    BREAKER_FAILURES,
    BREAKER_WINDOW_SECONDS,
    LLM_MAX_ATTEMPTS,
    RETRY_MAX_SECONDS,
)
from careflow.llm.reliability import CircuitBreaker, CircuitOpenError, call_with_retry


class Transient(Exception):
    pass


class Flaky:
    def __init__(self, failures: int, error: type[Exception] = Transient) -> None:
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("boom")
        return "ok"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def retry(fn: Flaky, sleeps: list[float]) -> str:
    return call_with_retry(fn, (Transient,), sleep=sleeps.append, jitter=lambda: 1.0)


def trip(breaker: CircuitBreaker) -> None:
    for _ in range(BREAKER_FAILURES):
        with pytest.raises(Transient):
            breaker.call(Flaky(1))


def test_transient_error_is_retried() -> None:
    fn, sleeps = Flaky(1), []
    assert retry(fn, sleeps) == "ok"
    assert fn.calls == 2
    assert len(sleeps) == 1


def test_other_errors_are_not_retried() -> None:
    fn = Flaky(1, ValueError)
    with pytest.raises(ValueError):
        retry(fn, [])
    assert fn.calls == 1


def test_gives_up_after_max_attempts() -> None:
    fn = Flaky(100)
    with pytest.raises(Transient):
        retry(fn, [])
    assert fn.calls == LLM_MAX_ATTEMPTS


def test_backoff_grows_and_is_capped() -> None:
    sleeps: list[float] = []
    with pytest.raises(Transient):
        retry(Flaky(100), sleeps)
    assert sleeps == sorted(sleeps)
    assert sleeps[0] < sleeps[-1] <= RETRY_MAX_SECONDS


def test_breaker_opens_and_fails_fast() -> None:
    breaker = CircuitBreaker((Transient,), clock=FakeClock())
    trip(breaker)
    fn = Flaky(0)
    with pytest.raises(CircuitOpenError):
        breaker.call(fn)
    assert fn.calls == 0


def test_old_failures_do_not_count() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker((Transient,), clock=clock)
    for _ in range(BREAKER_FAILURES - 1):
        with pytest.raises(Transient):
            breaker.call(Flaky(1))
    clock.now += BREAKER_WINDOW_SECONDS
    with pytest.raises(Transient):
        breaker.call(Flaky(1))
    assert breaker.call(Flaky(0)) == "ok"


def test_half_open_success_closes() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker((Transient,), clock=clock)
    trip(breaker)
    clock.now += BREAKER_COOLDOWN_SECONDS
    assert breaker.call(Flaky(0)) == "ok"
    assert breaker.call(Flaky(0)) == "ok"


def test_half_open_failure_reopens() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker((Transient,), clock=clock)
    trip(breaker)
    clock.now += BREAKER_COOLDOWN_SECONDS
    with pytest.raises(Transient):
        breaker.call(Flaky(1))
    with pytest.raises(CircuitOpenError):
        breaker.call(Flaky(0))
