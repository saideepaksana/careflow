import json
import random
import re
import subprocess

from careflow.config import EVAL_TRIALS, PROJECT_ROOT
from careflow.evaluation import metrics
from careflow.evaluation.scenarios import (
    REPLY_CHECKS,
    Scenario,
    StepResult,
    load_scenarios,
    reply_failures,
)

REPORTS = PROJECT_ROOT / "reports"
OUT_JSON = REPORTS / "m8" / "summary.json"
OUT_MD = REPORTS / "m8" / "summary.md"
HAND_CHECK_SAMPLE = 15
SAMPLE_SEED = 7


def read_jsonl(path) -> list[dict]:
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line]
        if path.exists()
        else []
    )


def crash_resume() -> dict:
    result = subprocess.run(
        [".venv/bin/pytest", "-q", "tests/test_crash_resume.py"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    passed = re.search(r"(\d+) passed", result.stdout)
    failed = re.search(r"(\d+) failed", result.stdout)
    return {
        "points_tested": int(passed.group(1)) if passed else 0,
        "points_failed": int(failed.group(1)) if failed else 0,
    }


def system_metrics(
    rows: list[dict], judgements: list[dict], system: str, covered: set[str]
) -> dict:
    return {
        "pass_at_1": metrics.pass_at_1(rows, system),
        "per_category": metrics.per_category(rows, system),
        "missed_escalation_rate": metrics.missed_escalation_rate(rows, system),
        "false_escalation_rate": metrics.false_escalation_rate(rows, system),
        "false_handoff_rate": metrics.false_handoff_rate(rows, system, covered),
        "injection_resistance": metrics.injection_resistance(rows, system),
        "unsupported_answers": metrics.unsupported_rate(judgements, system),
        "missing_item_links": sum(r["missing_item_link"] for r in metrics.valid(rows, system)),
        "usage": metrics.usage_summary(rows, system),
    }


def cell_counts(rows: list[dict]) -> dict:
    return {
        "valid": sum(r["valid"] for r in rows),
        "invalid": sum(not r["valid"] for r in rows),
        "trials_present": sorted({r["trial"] for r in rows}),
    }


def approval_capability(rows: list[dict]) -> str:
    cells = [
        r for r in metrics.valid(rows, "careflow") if r["completes_after_approval"] is not None
    ]
    return f"{sum(bool(r['completes_after_approval']) for r in cells)}/{len(cells)}"


def hand_check_sample(judgements: list[dict]) -> list[dict]:
    rng = random.Random(SAMPLE_SEED)
    sample = []
    for system in metrics.SYSTEMS:
        claims = [
            {"system": system, "scenario": j["scenario"], **c}
            for j in judgements
            if j["system"] == system
            for c in j.get("claims", [])
        ]
        sample += rng.sample(claims, min(HAND_CHECK_SAMPLE, len(claims)))
    return sample


def earlier_milestones() -> dict:
    load = lambda name: json.loads((REPORTS / name).read_text())  # noqa: E731
    return {
        "intake_m1": load("intake_m1.json"),
        "memory_m3": load("memory_m3.json"),
        "retrieval_m4": {
            mode: {k: v[k] for k in ("recall_at_5", "mrr", "stale_hit_rate")}
            for mode, v in load("retrieval_m4.json").items()
        },
        "careplan_m4": load("careplan_m4.json"),
    }


def rescore(row: dict, scenarios: dict[str, Scenario]) -> dict:
    """Re-run reply checks on stored replies so every row uses the current normalization."""
    steps = [StepResult.model_validate(step) for step in row["steps"]]
    kept = [check for check in row["failed_checks"] if check not in REPLY_CHECKS]
    failed = kept + reply_failures(scenarios[row["scenario"]].expect, steps)
    return {**row, "failed_checks": failed, "success": not failed}


def build_summary() -> dict:
    scenarios = {scenario.id: scenario for scenario in load_scenarios()}
    runs = metrics.latest_rows(read_jsonl(REPORTS / "m8" / "runs.jsonl"))
    rows = [rescore(row, scenarios) for row in runs]
    judgements = list(
        {
            (j["scenario"], j["system"], j["trial"]): j
            for j in read_jsonl(REPORTS / "m8" / "judgements.jsonl")
        }.values()
    )
    covered = {
        s.id
        for s in load_scenarios()
        if s.category == "care_plan_question" and s.expect.reply_includes
    }
    return {
        "cells": cell_counts(rows),
        "pass_hat_k": metrics.pass_hat_k(rows, EVAL_TRIALS),
        "systems": {s: system_metrics(rows, judgements, s, covered) for s in metrics.SYSTEMS},
        "careflow_completes_after_approval": approval_capability(rows),
        "judge_errors": sum(bool(j.get("error")) for j in judgements),
        "hand_check_sample": hand_check_sample(judgements),
        "crash_resume": crash_resume(),
        "earlier": earlier_milestones(),
    }


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def markdown(summary: dict) -> str:
    cf, bl = summary["systems"]["careflow"], summary["systems"]["baseline"]
    rows = [
        ("Task success pass@1", percent(cf["pass_at_1"]), percent(bl["pass_at_1"])),
        (
            f"pass^{summary['pass_hat_k']['k']} (n={summary['pass_hat_k']['n']})",
            percent(summary["pass_hat_k"]["careflow"]),
            percent(summary["pass_hat_k"]["baseline"]),
        ),
        (
            "Missed escalation",
            percent(cf["missed_escalation_rate"]),
            percent(bl["missed_escalation_rate"]),
        ),
        (
            "False escalation",
            percent(cf["false_escalation_rate"]),
            percent(bl["false_escalation_rate"]),
        ),
        (
            "False hand-off (covered questions)",
            percent(cf["false_handoff_rate"]),
            percent(bl["false_handoff_rate"]),
        ),
        (
            "Unsupported answers",
            f"{percent(cf['unsupported_answers']['rate'])} (n={cf['unsupported_answers']['n']})",
            f"{percent(bl['unsupported_answers']['rate'])} (n={bl['unsupported_answers']['n']})",
        ),
        (
            "Injection resistance",
            percent(cf["injection_resistance"]),
            percent(bl["injection_resistance"]),
        ),
        (
            "Tokens per resolved scenario",
            cf["usage"]["tokens_per_resolved"],
            bl["usage"]["tokens_per_resolved"],
        ),
        (
            "Cost per resolved scenario (USD, list price)",
            cf["usage"]["cost_per_resolved_usd"],
            bl["usage"]["cost_per_resolved_usd"],
        ),
        (
            "Latency p50 / p95 (ms)",
            f"{cf['usage']['latency_p50_ms']} / {cf['usage']['latency_p95_ms']}",
            f"{bl['usage']['latency_p50_ms']} / {bl['usage']['latency_p95_ms']}",
        ),
    ]
    lines = ["| Metric | CareFlow | Baseline |", "|---|---|---|"]
    lines += [f"| {name} | {a} | {b} |" for name, a, b in rows]
    lines += ["", "| Category | CareFlow | Baseline |", "|---|---|---|"]
    lines += [
        f"| {cat} | {cf['per_category'].get(cat, '-')} | {bl['per_category'].get(cat, '-')} |"
        for cat in sorted(cf["per_category"] | bl["per_category"])
    ]
    crash = summary["crash_resume"]
    lines += [
        "",
        f"Cells: {summary['cells']}. CareFlow completes after approval: "
        f"{summary['careflow_completes_after_approval']}. Judge errors: {summary['judge_errors']}. "
        f"Crash-resume: {crash['points_tested']} points tested, {crash['points_failed']} failed.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    summary = build_summary()
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    OUT_MD.write_text(markdown(summary))
    print(OUT_MD.read_text())


if __name__ == "__main__":
    main()
