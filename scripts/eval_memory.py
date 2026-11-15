import time

from careflow.config import MEMORY_EVAL_CASE_INTERVAL_SECONDS, PROJECT_ROOT, load_settings
from careflow.evaluation.memory_eval import MemoryCase, load_memory_cases, score_memory
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError, build_llm
from careflow.memory.manager import SessionDigest, digest_session
from careflow.memory.working import SessionSummary, WorkingMemory, fold_if_needed

REPORT_PATH = PROJECT_ROOT / "reports" / "memory_m3.json"


def run_case(llm: LLM, case: MemoryCase) -> tuple[SessionSummary | None, SessionDigest | None]:
    time.sleep(MEMORY_EVAL_CASE_INTERVAL_SECONDS)
    memory = WorkingMemory(recent=case.turns)
    try:
        folded = fold_if_needed(llm, memory, list(range(1, len(case.turns) + 1)))
        digest = digest_session(llm, folded.summary, folded.recent)
    except (LLMOutputError, LLMUnavailableError) as error:
        print(f"{case.id}: failed ({type(error).__name__})")
        return None, None
    print(f"{case.id}: {len(folded.summary.key_facts)} key facts, {len(digest.facts)} facts")
    return folded.summary, digest


def main() -> None:
    llm = build_llm(load_settings())
    cases = load_memory_cases()
    results = [run_case(llm, case) for case in cases]
    scores = score_memory(cases, [r[0] for r in results], [r[1] for r in results])
    for name, value in scores.model_dump().items():
        print(f"{name:<22} {value}")
    REPORT_PATH.write_text(scores.model_dump_json(indent=2) + "\n")
    print(f"report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
