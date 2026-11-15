import pytest

from careflow.observability.budget import RequestBudget, current_budget, request_budget


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    ("tokens", "seconds", "exceeded"),
    [(0, 0, False), (9, 4.9, False), (10, 0, True), (0, 5, True)],
)
def test_budget_exceeded(tokens: int, seconds: float, exceeded: bool) -> None:
    clock = Clock()
    budget = RequestBudget(max_tokens=10, max_seconds=5, clock=clock)
    budget.record(tokens, 0, 0.0)
    clock.now += seconds
    assert budget.exceeded() is exceeded


def test_summary_totals() -> None:
    clock = Clock()
    budget = RequestBudget(clock=clock)
    budget.record(100, 20, 0.001)
    budget.record(50, 10, 0.002)
    clock.now += 1.5
    assert budget.summary() == {
        "input_tokens": 150,
        "output_tokens": 30,
        "cost_usd": 0.003,
        "llm_calls": 2,
        "elapsed_ms": 1500,
    }


def test_nested_request_joins_the_outer_budget() -> None:
    with request_budget() as outer, request_budget() as inner:
        assert inner is outer
    assert current_budget() is None


def test_no_budget_outside_a_request() -> None:
    assert current_budget() is None
