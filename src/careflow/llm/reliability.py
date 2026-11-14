import random
import time
from collections.abc import Callable
from typing import TypeVar

from careflow.config import (
    BREAKER_COOLDOWN_SECONDS,
    BREAKER_FAILURES,
    BREAKER_WINDOW_SECONDS,
    LLM_MAX_ATTEMPTS,
    RETRY_BASE_SECONDS,
    RETRY_MAX_SECONDS,
)

T = TypeVar("T")


class CircuitOpenError(Exception):
    pass


def backoff_seconds(attempt: int, jitter: Callable[[], float]) -> float:
    return jitter() * min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * 2**attempt)


def call_with_retry(
    fn: Callable[[], T],
    retryable: tuple[type[Exception], ...],
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    for attempt in range(1, LLM_MAX_ATTEMPTS):
        try:
            return fn()
        except retryable:
            sleep(backoff_seconds(attempt, jitter))
    return fn()


class CircuitBreaker:
    def __init__(
        self,
        counted: tuple[type[Exception], ...],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.counted = counted
        self.clock = clock
        self.failures: list[float] = []
        self.opened_at: float | None = None

    def call(self, fn: Callable[[], T]) -> T:
        if self.opened_at is not None and self.clock() - self.opened_at < BREAKER_COOLDOWN_SECONDS:
            raise CircuitOpenError("circuit is open")
        half_open = self.opened_at is not None
        try:
            result = fn()
        except self.counted:
            self.record_failure(half_open)
            raise
        self.failures.clear()
        self.opened_at = None
        return result

    def record_failure(self, half_open: bool) -> None:
        now = self.clock()
        if half_open:
            self.opened_at = now
            return
        self.failures = [t for t in self.failures if now - t < BREAKER_WINDOW_SECONDS] + [now]
        if len(self.failures) >= BREAKER_FAILURES:
            self.opened_at = now
