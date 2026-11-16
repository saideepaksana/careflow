import pytest

from careflow.evaluation import metrics


def row(scenario: str, system: str, trial: int, success: bool, **extra: object) -> dict:
    base = {
        "scenario": scenario,
        "system": system,
        "trial": trial,
        "success": success,
        "valid": True,
        "category": "routine_scheduling",
        "failed_checks": [] if success else ["booked"],
        "escalation": None,
        "missing_item_link": False,
        "steps": [],
    }
    return {**base, **extra}


def test_latest_row_per_cell_wins() -> None:
    rows = [row("s1", "careflow", 1, False, valid=False), row("s1", "careflow", 1, True)]
    assert [r["success"] for r in metrics.latest_rows(rows)] == [True]


def test_pass_hat_k_uses_scenarios_complete_for_both_systems() -> None:
    rows = [
        row("s1", system, t, t != 2 or system == "careflow")
        for system in metrics.SYSTEMS
        for t in (1, 2)
    ]
    rows += [row("s2", "careflow", 1, True)]
    assert metrics.pass_hat_k(rows, 2) == {"k": 2, "n": 1, "careflow": 1.0, "baseline": 0.0}


def test_invalid_cells_are_not_scored() -> None:
    rows = [row("s1", "careflow", 1, True), row("s2", "careflow", 1, False, valid=False)]
    assert metrics.pass_at_1(rows, "careflow") == 1.0


@pytest.mark.parametrize(
    ("rows", "missed", "false"),
    [
        (
            [
                row(
                    "r",
                    "careflow",
                    1,
                    False,
                    category="explicit_red_flag",
                    failed_checks=["escalation"],
                )
            ],
            1.0,
            None,
        ),
        ([row("r", "careflow", 1, True, category="implicit_red_flag")], 0.0, None),
        (
            [row("q", "careflow", 1, True, category="care_plan_question", escalation="urgent")],
            None,
            1.0,
        ),
        (
            [row("q", "careflow", 1, True, category="care_plan_question", escalation="routine")],
            None,
            0.0,
        ),
    ],
)
def test_escalation_rates(rows: list[dict], missed: float | None, false: float | None) -> None:
    assert metrics.missed_escalation_rate(rows, "careflow") == missed
    assert metrics.false_escalation_rate(rows, "careflow") == false


def test_unsupported_rate_counts_answers_with_claims() -> None:
    judgements = [
        {"system": "careflow", "claims": [{"supported": True}, {"supported": False}]},
        {"system": "careflow", "claims": [{"supported": True}]},
        {"system": "careflow", "claims": []},
    ]
    assert metrics.unsupported_rate(judgements, "careflow") == {"rate": 0.5, "n": 2}


@pytest.mark.parametrize(
    ("values", "share", "expected"),
    [([], 0.5, None), ([5], 0.95, 5), ([1, 2, 3, 4], 0.5, 2), (list(range(1, 21)), 0.95, 19)],
)
def test_percentile(values: list[int], share: float, expected: int | None) -> None:
    assert metrics.percentile(values, share) == expected


def test_usage_per_resolved_scenario_skips_noop_latency() -> None:
    step = {
        "usage": [{"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001}],
        "wall_ms": 400,
        "noop": False,
    }
    noop = {"usage": [], "wall_ms": 0, "noop": True}
    rows = [
        row("s1", "careflow", 1, True, steps=[step, noop]),
        row("s2", "careflow", 1, False, steps=[step]),
    ]
    usage = metrics.usage_summary(rows, "careflow")
    assert (usage["tokens_per_resolved"], usage["cost_per_resolved_usd"]) == (300, 0.002)
    assert (usage["latency_p50_ms"], usage["latency_p95_ms"]) == (400, 400)
