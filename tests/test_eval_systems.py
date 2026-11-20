import json

import pytest

from careflow.agents.baseline_prompt import BASELINE_SYSTEM_PROMPT
from careflow.config import Settings
from careflow.db.connection import clone_database, connect, database_url_for, recreate_database
from careflow.db.seed import seed
from careflow.evaluation.e2e import CellContext, eval_settings, run_cell
from careflow.evaluation.scenarios import load_scenarios
from careflow.evaluation.systems import RecordingLLM
from careflow.knowledge.rerank import FakeReranker
from careflow.llm.gateway import LLMBudgetExceeded, LLMRejectedError, LLMUnavailableError
from careflow.memory.embeddings import FakeEmbedder
from careflow.observability.budget import RequestBudget, request_budget
from careflow.observability.meter import UsageMeter
from tests.scripted import RoleLLM, book_lab, intake_reply

SCENARIOS = {s.id: s for s in load_scenarios()}
UNLIMITED = 10**9


def step(**fields: object) -> str:
    return json.dumps(fields)


class BaselineLLM:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)

    def complete(self, system: str, user: str) -> str:
        assert system.startswith(BASELINE_SYSTEM_PROMPT)
        return self.replies.pop(0)


BASELINE_BOOKING = [
    step(action="reply", reply="I can book the lab on Tue 3 Nov at 09:00. Shall I go ahead?"),
    step(
        action="call_tool",
        tool="book_appointment",
        args={"slot_id": "S-C08-20261103-0900", "care_plan_item_id": "CP001-v2-02"},
    ),
    step(action="reply", reply="Booked."),
]
BASELINE_RED_FLAG = [
    step(
        action="call_tool",
        tool="create_coordinator_task",
        args={"priority": "emergency", "title": "Chest pain", "detail": "now"},
    ),
    step(action="reply", reply="This may be an emergency. Call 112 now."),
]


def context(url: str, llm: object) -> CellContext:
    settings = eval_settings(Settings(database_url=url, llm_model="groq/x", llm_api_key="k"), url)
    return CellContext(
        settings, RecordingLLM(llm, UNLIMITED), FakeEmbedder(), FakeReranker(), UsageMeter()
    )


@pytest.mark.parametrize(
    ("system", "llm"),
    [
        (
            "careflow",
            RoleLLM(
                {
                    **book_lab("2026-11-03"),
                    "planner": json.dumps(
                        {
                            "action": "book",
                            "care_plan_item_id": "CP001-v2-02",
                            "earliest_date": "2026-11-03",
                            "latest_date": "2026-11-03",
                            "part_of_day": "morning",
                        }
                    ),
                }
            ),
        ),
        ("baseline", BaselineLLM(BASELINE_BOOKING)),
    ],
)
def test_booking_scenario_runs_on_both_systems(fresh_db_url: str, system: str, llm: object) -> None:
    row = run_cell(context(fresh_db_url, llm), SCENARIOS["sched-01"], system)
    assert (row["valid"], row["success"], row["failed_checks"]) == (True, True, [])
    assert [s["kind"] for s in row["steps"]] == ["say", "confirm"]


@pytest.mark.parametrize(
    ("system", "llm"),
    [
        (
            "careflow",
            RoleLLM(
                {
                    "intake": intake_reply(
                        [{"kind": "symptom_report", "summary": "Chest pain"}], "emergency"
                    )
                }
            ),
        ),
        ("baseline", BaselineLLM(BASELINE_RED_FLAG)),
    ],
)
def test_red_flag_scenario_runs_on_both_systems(
    fresh_db_url: str, system: str, llm: object
) -> None:
    row = run_cell(context(fresh_db_url, llm), SCENARIOS["rf-01"], system)
    assert (row["success"], row["escalation"]) == (True, "emergency")


def test_baseline_booking_without_asking_fails_confirmed_first(fresh_db_url: str) -> None:
    eager = [BASELINE_BOOKING[1], BASELINE_BOOKING[2], step(action="reply", reply="Already done.")]
    row = run_cell(context(fresh_db_url, BaselineLLM(eager)), SCENARIOS["sched-01"], "baseline")
    assert "confirmed_first" in row["failed_checks"]


def test_system_errors_are_scored_not_raised(fresh_db_url: str) -> None:
    row = run_cell(context(fresh_db_url, BaselineLLM([])), SCENARIOS["q-01"], "baseline")
    assert row["valid"] and not row["success"]
    assert row["steps"][0]["replies"] == ["error:IndexError"]
    assert "no_error" in row["failed_checks"]


def test_crash_fails_a_scenario_without_reply_checks(fresh_db_url: str) -> None:
    row = run_cell(context(fresh_db_url, BaselineLLM([])), SCENARIOS["inj-01"], "baseline")
    assert row["failed_checks"] == ["no_error"]


class Failing:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def complete(self, system: str, user: str) -> str:
        raise self.error


@pytest.mark.parametrize(
    ("error", "counted"),
    [
        (LLMUnavailableError("429"), 1),
        (LLMBudgetExceeded("spent"), 0),
        (LLMRejectedError("content filter"), 0),
    ],
)
def test_recording_llm_counts_only_provider_outages(error: Exception, counted: int) -> None:
    llm = RecordingLLM(Failing(error), UNLIMITED)
    with pytest.raises(LLMUnavailableError):
        llm.complete("system", "user")
    assert llm.unavailable == counted


def test_provider_outage_makes_the_cell_invalid(fresh_db_url: str) -> None:
    row = run_cell(
        context(fresh_db_url, Failing(LLMUnavailableError("429"))), SCENARIOS["q-01"], "careflow"
    )
    assert (row["valid"], row["invalid_reason"]) == (False, "provider_unavailable")


def test_clone_copies_seed_and_checkpoint_tables(fresh_db_url: str) -> None:
    template_url = recreate_database(fresh_db_url, "careflow_test_template")
    seed(template_url)
    clone_url = clone_database(fresh_db_url, "careflow_test_template", "careflow_test_clone")
    with connect(clone_url) as conn:
        patients = conn.execute("SELECT count(*) AS n FROM patients").fetchone()["n"]
        checkpoints = conn.execute("SELECT to_regclass('public.checkpoints') AS t").fetchone()["t"]
    with connect(database_url_for(fresh_db_url, "postgres"), autocommit=True) as admin:
        for name in ("careflow_test_clone", "careflow_test_template"):
            admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
    assert (patients, checkpoints) == (5, "checkpoints")


def test_eval_settings_disable_the_fallback() -> None:
    settings = eval_settings(Settings(llm_model="a", llm_fallback_model="b"), "postgresql://x/y")
    assert (settings.llm_fallback_model, settings.database_url) == ("", "postgresql://x/y")


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_pacing_wait_extends_the_request_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeTime()
    monkeypatch.setattr("careflow.evaluation.systems.time", fake)
    llm = RecordingLLM(Failing(LLMUnavailableError("x")), tokens_per_minute=1)
    llm.window.append((fake.now, 1))
    with request_budget(RequestBudget(max_seconds=5)) as budget:
        started = budget.started
        llm.wait_for(1)
    assert budget.started > started
    assert llm.throttled_seconds == 60


@pytest.mark.parametrize(("scenario", "completes"), [("appr-01", True), ("appr-02", None)])
def test_careflow_coordinator_step_resumes_the_run(
    fresh_db_url: str, scenario: str, completes: bool | None
) -> None:
    day = "2026-11-10" if scenario == "appr-01" else "2026-11-12"
    item = "CP001-v2-02" if scenario == "appr-01" else "CP005-v1-01"
    planner = json.dumps(
        {"action": "book", "care_plan_item_id": item, "earliest_date": day, "latest_date": day}
    )
    llm = RoleLLM({**book_lab(day), "planner": planner})
    row = run_cell(context(fresh_db_url, llm), SCENARIOS[scenario], "careflow")
    replies = [reply for step in row["steps"] for reply in step["replies"]]
    assert row["success"] and row["completes_after_approval"] is completes
    assert not [reply for reply in replies if reply.startswith("error:")]
    assert row["steps"][-1]["noop"] is False
