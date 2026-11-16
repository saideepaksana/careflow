import hashlib
import json
import subprocess
import sys

from careflow import clock
from careflow.config import (
    CORPUS_DIR,
    EVAL_DATABASE,
    EVAL_MAX_CELL_ATTEMPTS,
    EVAL_MAX_INVALID_IN_A_ROW,
    EVAL_TEMPLATE_DATABASE,
    EVAL_TRIALS,
    PROJECT_ROOT,
    load_settings,
)
from careflow.db.connection import clone_database, connect, database_url_for, recreate_database
from careflow.db.seed import seed
from careflow.evaluation.e2e import CellContext, eval_settings, run_cell
from careflow.evaluation.judge import JUDGED_CATEGORIES, judge_reply
from careflow.evaluation.metrics import SYSTEMS, cell_key
from careflow.evaluation.scenarios import SCENARIOS_PATH, Scenario, load_scenarios
from careflow.evaluation.systems import RecordingLLM
from careflow.knowledge.corpus import ingest_corpus
from careflow.knowledge.rerank import FastReranker
from careflow.llm.gateway import LiteLLMClient, LLMOutputError, LLMUnavailableError
from careflow.memory.embeddings import FastEmbedder
from careflow.observability.meter import UsageMeter
from careflow.observability.tracing import setup_tracing

RUNS_PATH = PROJECT_ROOT / "reports" / "m8" / "runs.jsonl"
JUDGEMENTS_PATH = PROJECT_ROOT / "reports" / "m8" / "judgements.jsonl"
QUOTA_REASON = "provider_unavailable"


def read_jsonl(path) -> list[dict]:
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line]
        if path.exists()
        else []
    )


def append_jsonl(path, row: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def fingerprint(model: str) -> dict:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    digest = hashlib.sha256(SCENARIOS_PATH.read_bytes()).hexdigest()[:12]
    return {"commit": commit.stdout.strip(), "model": model, "scenarios": digest}


def build_template(database_url: str, embedder: FastEmbedder) -> str:
    template_url = recreate_database(database_url, EVAL_TEMPLATE_DATABASE)
    seed(template_url)
    with connect(template_url, autocommit=True) as conn:
        ingest_corpus(conn, embedder, CORPUS_DIR)
    return template_url


def cell_state(rows: list[dict], key: tuple) -> tuple[bool, int]:
    """Done when the latest row is valid or the cell failed repeatedly for non-quota reasons."""
    mine = [row for row in rows if cell_key(row) == key]
    counted = [row for row in mine if row["invalid_reason"] != QUOTA_REASON]
    done = bool(mine) and (mine[-1]["valid"] or len(counted) >= EVAL_MAX_CELL_ATTEMPTS)
    return done, len(mine)


def describe(row: dict) -> str:
    outcome = "ok  " if row["success"] else "FAIL"
    validity = "" if row["valid"] else f"INVALID {row['invalid_reason']}"
    checks = ",".join(row["failed_checks"])
    cell = f"trial {row['trial']} {row['scenario']:<9} {row['system']:<8}"
    return f"{cell} {outcome} {validity} {checks}"


def run_one(ctx: CellContext, scenario: Scenario, system: str, trial: int, meta: dict) -> dict:
    clone_database(ctx.settings.database_url, EVAL_TEMPLATE_DATABASE, EVAL_DATABASE)
    ctx.llm.inner = LiteLLMClient(ctx.settings)
    row = run_cell(ctx, scenario, system)
    row.update(scenario=scenario.id, category=scenario.category, system=system, trial=trial, **meta)
    append_jsonl(RUNS_PATH, row)
    print(describe(row), flush=True)
    return row


def run_trial(ctx: CellContext, scenarios: list[Scenario], trial: int, stamp: dict) -> bool:
    """Runs the missing cells of one trial; False when the provider looks exhausted."""
    rows, invalid_streak = read_jsonl(RUNS_PATH), 0
    for scenario in scenarios:
        for system in SYSTEMS:
            done, attempts = cell_state(rows, (scenario.id, system, trial))
            if done:
                continue
            meta = {"attempt": attempts + 1, "fingerprint": stamp}
            row = run_one(ctx, scenario, system, trial, meta)
            invalid_streak = 0 if row["valid"] else invalid_streak + 1
            if invalid_streak >= EVAL_MAX_INVALID_IN_A_ROW:
                return False
    return True


def judge_trial(ctx: CellContext, template_url: str, trial: int) -> None:
    rows = [r for r in read_jsonl(RUNS_PATH) if r["trial"] == trial and r["valid"]]
    latest = {cell_key(r): r for r in rows if r["category"] in JUDGED_CATEGORIES}
    judged = {cell_key(j) for j in read_jsonl(JUDGEMENTS_PATH) if not j.get("error")}
    with connect(template_url) as conn:
        for key, row in latest.items():
            if key in judged:
                continue
            judgement = {"scenario": key[0], "system": key[1], "trial": key[2]}
            try:
                result = judge_reply(
                    ctx.llm,
                    conn,
                    ctx.embedder,
                    ctx.reranker,
                    row_patient(row),
                    row["question"],
                    row["final_reply"],
                )
                judgement["claims"] = [claim.model_dump() for claim in result.claims]
            except (LLMOutputError, LLMUnavailableError) as error:
                judgement["error"] = type(error).__name__
            append_jsonl(JUDGEMENTS_PATH, judgement)
            ctx.meter.take()


def row_patient(row: dict) -> str:
    return SCENARIO_PATIENTS[row["scenario"]]


SCENARIO_PATIENTS = {scenario.id: scenario.patient_id for scenario in load_scenarios()}


def main() -> None:
    if clock.today() != clock.FROZEN_TODAY:
        sys.exit("unset CAREFLOW_TODAY: scenarios assume the frozen date")
    settings = load_settings()
    embedder, reranker, meter = FastEmbedder(), FastReranker(), UsageMeter()
    setup_tracing(exporter=meter)
    template_url = build_template(settings.database_url, embedder)
    cell_settings = eval_settings(settings, database_url_for(settings.database_url, EVAL_DATABASE))
    llm = RecordingLLM(LiteLLMClient(cell_settings))
    ctx = CellContext(cell_settings, llm, embedder, reranker, meter)
    scenarios, stamp = load_scenarios(), fingerprint(settings.llm_model)
    for trial in range(1, EVAL_TRIALS + 1):
        if not run_trial(ctx, scenarios, trial, stamp):
            print("provider unavailable twice in a row (quota?); run again later to resume")
            return
        judge_trial(ctx, template_url, trial)
        print(f"trial {trial} complete", flush=True)


if __name__ == "__main__":
    main()
