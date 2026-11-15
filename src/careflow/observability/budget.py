import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from careflow.config import REQUEST_TIME_BUDGET_SECONDS, REQUEST_TOKEN_BUDGET


@dataclass
class RequestBudget:
    max_tokens: int = REQUEST_TOKEN_BUDGET
    max_seconds: float = REQUEST_TIME_BUDGET_SECONDS
    clock: Callable[[], float] = time.monotonic
    started: float = field(default=-1.0)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0

    def __post_init__(self) -> None:
        if self.started < 0:
            self.started = self.clock()

    def elapsed(self) -> float:
        return self.clock() - self.started

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed())

    def exceeded(self) -> bool:
        tokens = self.input_tokens + self.output_tokens
        return tokens >= self.max_tokens or self.elapsed() >= self.max_seconds

    def record(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost_usd
        self.llm_calls += 1

    def summary(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "llm_calls": self.llm_calls,
            "elapsed_ms": round(self.elapsed() * 1000),
        }


ACTIVE_BUDGET: ContextVar[RequestBudget | None] = ContextVar("active_budget", default=None)


def current_budget() -> RequestBudget | None:
    return ACTIVE_BUDGET.get()


@contextmanager
def request_budget(budget: RequestBudget | None = None) -> Iterator[RequestBudget]:
    """Use the active budget if one is set, otherwise start a fresh one for this request."""
    active = current_budget()
    if active is not None:
        yield active
        return
    token = ACTIVE_BUDGET.set(budget or RequestBudget())
    try:
        yield ACTIVE_BUDGET.get()
    finally:
        ACTIVE_BUDGET.reset(token)
