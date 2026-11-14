import time

from careflow.agents.intake import IntakeRecord, run_intake
from careflow.config import EVAL_CASE_INTERVAL_SECONDS, PROJECT_ROOT, load_settings
from careflow.evaluation.intake_eval import IntakeCase, load_cases, score
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError, build_llm

REPORT_PATH = PROJECT_ROOT / "reports" / "intake_m1.json"


def run_case(llm: LLM, case: IntakeCase) -> IntakeRecord | None:
    time.sleep(EVAL_CASE_INTERVAL_SECONDS)
    try:
        record = run_intake(llm, case.message, [])
    except (LLMOutputError, LLMUnavailableError) as error:
        print(f"{case.id}: failed ({type(error).__name__})")
        return None
    print(f"{case.id}: {record.urgency} {sorted({item.kind.value for item in record.items})}")
    return record


def main() -> None:
    llm = build_llm(load_settings())
    cases = load_cases()
    records = [run_case(llm, case) for case in cases]
    scores = score(cases, records)
    for name, value in scores.model_dump().items():
        print(f"{name:<22} {value}")
    REPORT_PATH.write_text(scores.model_dump_json(indent=2) + "\n")
    print(f"report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
