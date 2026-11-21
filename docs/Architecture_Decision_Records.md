# CareFlow: Architecture Decision Records

Project: CareFlow, an AI care-coordination assistant for the post-discharge transition.
Course: CS5903 Distributed AI Training. Project ID 11, Group 24.
Repository: https://github.com/saideepaksana/careflow

## How to read this log

- There is one record per material design or methodology decision. ADR-001 is the mandatory 9 October 2026 methodology record.
- Every record has the same eight fields: ID and title; date, status and scope; context and decision drivers; options considered; decision and rationale; consequences and trade-offs; evidence and validation; revisit trigger.
- **Measured** marks a claim backed by a test, a report file or a recomputable number. **Judgment** marks a choice that was reasoned, not measured.
- Dates come from the git history (YYYY-MM-DD). A decision first written in the proposal is dated by the first commit, 2026-11-06 ([2fbbdda]). A decision made while building is dated by the commit that built it.
- Superseded decisions are kept. A record that replaces an earlier design says "Supersedes". A record changed later says "Amended" or "Superseded in part by". The original proposal text is preserved in commit [2fbbdda] (`docs/proposal.tex`).
- All evaluation numbers come from [reports/](../reports/) and are recomputed by [scripts/eval_report.py](../scripts/eval_report.py). The end-to-end (M8) runs used the code at [9ce8e9c] with the harness from [19abd0f]. The fixes in [55f0fcc] and [b69df5a] were checked by the unit and integration tests (553 passed) but were not re-evaluated end to end.

## Index

| ID | Title | Date | Status |
|---|---|---|---|
| [ADR-001](#adr-001-methodology-checkpoint-of-9-october-2026-not-applicable) | Methodology checkpoint of 9 October 2026 (not applicable) | 2026-11-20 | Accepted (not applicable) |
| [ADR-002](#adr-002-problem-framing-and-scope-autonomous-routine-coordination-human-hand-off-for-clinical-items) | Problem framing and scope: autonomous routine coordination, human hand-off for clinical items | 2026-11-06 | Accepted |
| [ADR-003](#adr-003-multi-agent-graph-with-deterministic-nodes-vs-single-react-agent-baseline-kept) | Multi-agent graph with deterministic nodes vs single ReAct agent (baseline kept) | 2026-11-06 | Accepted |
| [ADR-004](#adr-004-deterministic-safety-gate-raise-only-incl-red-flag-during-pending-confirmation-2026-11-20) | Deterministic safety gate (raise-only), incl. red flag during pending confirmation (2026-11-20) | 2026-11-06 | Accepted, amended 2026-11-15 and 2026-11-20 |
| [ADR-005](#adr-005-model-provider-and-litellm-gateway-gpt-oss-120b-on-groq-supersedes-llama-33) | Model, provider and LiteLLM gateway (gpt-oss-120b on Groq; supersedes Llama 3.3) | 2026-11-15 | Accepted |
| [ADR-006](#adr-006-gateway-reliability-retry-per-model-circuit-breakers-fallback-model-supersedes-per-provider-breaker) | Gateway reliability: retry, per-model circuit breakers, fallback model (supersedes per-provider breaker) | 2026-11-15 | Accepted, amended 2026-11-20 |
| [ADR-007](#adr-007-langgraph-with-postgresql-checkpointer-one-thread-per-patient-request-supersedes-thread-per-conversation) | LangGraph with PostgreSQL checkpointer, one thread per patient request (supersedes thread per conversation) | 2026-11-15 | Accepted |
| [ADR-008](#adr-008-single-store-postgresql-17--pgvector) | Single store: PostgreSQL 17 + pgvector | 2026-11-06 | Accepted |
| [ADR-009](#adr-009-tool-layer-three-mcp-servers-bound-to-the-session-patient) | Tool layer: three MCP servers bound to the session patient | 2026-11-15 | Accepted |
| [ADR-010](#adr-010-security-and-trust-model-demo-login-coordinator-token-locks-input-validation-no-content-in-traces) | Security and trust model (demo login, coordinator token, locks, input validation, no content in traces) | 2026-11-15 | Accepted, amended 2026-11-20 |
| [ADR-011](#adr-011-retrieval-hybrid-fts--dense-with-rrf-and-cross-encoder-rerank) | Retrieval: hybrid FTS + dense with RRF and cross-encoder rerank | 2026-11-15 | Accepted |
| [ADR-012](#adr-012-cite-or-hand-off-code-level-citation-check) | Cite or hand off: code-level citation check | 2026-11-15 | Accepted |
| [ADR-013](#adr-013-memory-design-and-clinical-guard-episodic-guard-added-2026-11-20) | Memory design and clinical guard (episodic guard added 2026-11-20) | 2026-11-15 | Accepted, amended 2026-11-20 |
| [ADR-014](#adr-014-scheduling-llm-interprets-code-chooses-slot-verifier-confirmation-before-coordinator-approval) | Scheduling: LLM interprets, code chooses slot, verifier, confirmation before coordinator approval | 2026-11-15 | Accepted |
| [ADR-015](#adr-015-observability-budgets-and-cost-accounting) | Observability, budgets and cost accounting | 2026-11-15 | Accepted |
| [ADR-016](#adr-016-ui-transport-request-per-turn-plus-polling-instead-of-sse-desktop-only-supersedes-sse) | UI transport: request-per-turn plus polling instead of SSE; desktop only (supersedes SSE) | 2026-11-15 | Accepted, amended 2026-11-20 |
| [ADR-017](#adr-017-evaluation-methodology-scripted-scenarios-db-state-scoring-trial-1-headline-personas-dropped) | Evaluation methodology (scripted scenarios, DB-state scoring, trial-1 headline, personas dropped) | 2026-11-16 | Accepted, amended 2026-11-20 |
| [ADR-018](#adr-018-milestone-order-realigned-to-the-proposal-m7-observability-m8-evaluation) | Milestone order realigned to the proposal (M7 observability, M8 evaluation) | 2026-11-15 to 2026-11-16 | Accepted |

---

## ADR-001: Methodology checkpoint of 9 October 2026 (not applicable)

**Date, status and scope.** Record written 2026-11-20. It is not backdated. Status: Accepted (not applicable). Scope: the whole project methodology.

**Context and decision drivers.** The course asks every project to state whether its methodology was reaffirmed or changed by 9 October 2026, 11:59 PM IST. As the team understands the course schedule, that checkpoint was meant for two-month projects, and CareFlow is a one-month project. The dates settle it in any case: Its proposal and its first commit ([2fbbdda]) are both dated 2026-11-06, almost a month after the checkpoint.

**Options considered.**

| Option | Comment |
|---|---|
| A. Mark the checkpoint not applicable and explain why | True to the dates in the repository |
| B. Write a reaffirmation as if it had been made on 9 October | Would be backdating; rejected |

**Decision and rationale.** Option A. The 9 October checkpoint is not applicable to CareFlow. On 9 October 2026 the project did not exist yet, so there was no methodology to reaffirm or change on that date. This is a fact of the dates (measured from git history), not a judgment. The methodology approved in the proposal ([docs/proposal.tex](proposal.tex), commit [2fbbdda]) is the one the team followed. Every later change to it is recorded as its own ADR in this log. Changes from the proposal are in ADR-005, ADR-006, ADR-007, ADR-011, ADR-016, ADR-017 and ADR-018; amendments made after building are in ADR-004, ADR-006, ADR-010, ADR-013 and ADR-016.

**Consequences and trade-offs.** No mid-project methodology review exists. The proposal itself is the methodology baseline, and the deviations are traceable through the records below and through section 5 of [docs/report.md](report.md).

**Evidence and validation.** `git log --reverse` starts at [2fbbdda] on 2026-11-06 ("Initial Repo Setup", which adds the proposal). No earlier commit, tag or branch exists.

**Revisit trigger.** None for this project. If the project were extended past one month, a methodology checkpoint would be held at the midpoint of the extension and recorded as a new ADR.

---

## ADR-002: Problem framing and scope: autonomous routine coordination, human hand-off for clinical items

**Date, status and scope.** 2026-11-06 ([2fbbdda], proposal sections 1, 2 and 4). Status: Accepted. Scope: all milestones; the research question; what the system may and may not do.

**Context and decision drivers.** After discharge, patients need follow-ups booked, plans explained and warning signs recognised. Much of a coordinator's work is routine. In healthcare a missed warning sign, or a confident answer that is not in the patient's plan, can harm a patient. The project also had one month and synthetic data only.

**Options considered.**

| Option | Strength | Weakness |
|---|---|---|
| A. A general assistant that answers every patient question | Most helpful in the easy cases | Clinical answers and missed red flags are the costliest failures |
| B. Information only: answer questions from documents, take no actions | Lowest risk | Does not reduce the coordinator's routine work, which is the point |
| C. Do routine coordination autonomously (scheduling, cited answers) and hand every clinical item to a human | Removes routine work; bounds the risk | Needs a reliable escalation path and a durable hand-off |

**Decision and rationale.** Option C. The goal is not an assistant that answers everything but one that "completes routine coordination by itself and reliably recognises what it must not handle" ([proposal](proposal.tex), section 1). Diagnosis, prescribing, dose changes, real EHR data and real emergency dispatch are out of scope (section 2.3). This is judgment, supported by literature cited in the proposal (readmission and adverse-event studies, Project RED, HealthBench). The research question asks whether this design beats a single agent while keeping missed escalations and unsupported clinical answers at zero.

**Consequences and trade-offs.** Some questions a patient would like answered are handed off. The false hand-off rate became a tracked cost (ADR-012). Every hand-off needs a coordinator task and a durable workflow (ADR-007). CareFlow is a research prototype on synthetic data, not a medical device.

**Evidence and validation.** Measured in M8 ([reports/m8/summary.json](../reports/m8/summary.json)): missed escalation 0/10 for CareFlow and 1/10 for the baseline; false escalation 0% for both; out-of-scope trial 1 5/5 vs 3/5. Tests: [tests/test_workflow.py](../tests/test_workflow.py) `test_running_example_escalates_and_does_not_reschedule`; [tests/test_careplan.py](../tests/test_careplan.py) `test_unsupported_answers_hand_off`.

**Revisit trigger.** Any missed escalation (more than 0 of the red-flag cells) in a full trial, or a false hand-off rate on covered questions above 25% (2 of 8) in a full trial.

---

## ADR-003: Multi-agent graph with deterministic nodes vs single ReAct agent (baseline kept)

**Date, status and scope.** Decided 2026-11-06 ([2fbbdda], proposal section 4.3); built 2026-11-15 ([099be4d], M5). Status: Accepted. Scope: M2, M5, M6, M8; every component in [docs/architecture.md](architecture.md).

**Context and decision drivers.** One patient message can hold a routine request and a red flag (challenge C1). Raw text is untrusted (C6). The component that reads raw text must not be able to write. Tool-using agents are inconsistent across repeated runs. Multi-agent systems fail through hand-offs and endless loops (MAST, cited in the proposal).

**Options considered.**

| Option | Strength | Weakness |
|---|---|---|
| A. Keep the M2 single ReAct agent with all tools and all rules in its prompt | Simplest; already built | Safety depends on the model following the prompt; it reads raw text and holds write tools |
| B. An LLM supervisor that routes to LLM specialists | Flexible routing | Adds hand-offs and loops without adding permission boundaries |
| C. A graph where routing, safety checks and writes are code, and the LLM is used only for intake, answering and planning | Permissions enforced by structure; fewer model calls | More code; less flexible for requests outside the designed paths |

**Decision and rationale.** Option C. The split rule is: separate a component only where it needs different permissions or different knowledge ([proposal](proposal.tex), section 4.3). This rule is judgment. The M2 agent is kept, unchanged in its role, as the evaluation baseline. It uses the same model, the same MCP tools and search, and a prompt that carries every rule CareFlow enforces in code.

**Consequences and trade-offs.** CareFlow is more code to maintain and test. Requests outside the designed item kinds go to a human. The baseline makes the comparison fair, at the cost of maintaining two systems.

**Evidence and validation.** Measured after building (M8, [reports/m8/summary.json](../reports/m8/summary.json), [docs/report.md](report.md) section 3): trial-1 task success 49/50 (98%) vs 38/50 (76%); pooled valid cells 62/63 vs 42/62; tokens per resolved scenario 2,140 vs 8,633; injection resistance 100% vs 80%; missed escalation 0% vs 10%. The cost: CareFlow false hand-off on covered questions 1/8 (12.5%, q-07) vs 0%. Permission tests in [tests/test_architecture.py](../tests/test_architecture.py): `test_intake_has_no_data_or_tool_access`, `test_only_executor_and_baseline_call_write_tools`, `test_escalation_cannot_be_overruled`, `test_raw_patient_text_reaches_only_intake_and_gate`, `test_scheduler_has_no_database_or_tools`, `test_careplan_answerer_has_no_tools_or_database`.

**Revisit trigger.** The baseline comes within 5 percentage points of CareFlow's task success over three full trials, or CareFlow's false hand-off on covered questions exceeds 25% (2 of 8) in a full trial.

---

## ADR-004: Deterministic safety gate (raise-only), incl. red flag during pending confirmation (2026-11-20)

**Date, status and scope.** Decided 2026-11-06 ([2fbbdda], proposal section 4.7); built 2026-11-15 ([099be4d]). Amended 2026-11-15 ([9ce8e9c], intake failure is urgent), 2026-11-20 ([55f0fcc], matching rules) and 2026-11-20 ([b69df5a], red flag during a pending confirmation). Status: Accepted. Scope: M5 onward; [src/careflow/safety/gate.py](../src/careflow/safety/gate.py); `RED_FLAG_TERMS` in [src/careflow/config.py](../src/careflow/config.py).

**Context and decision drivers.** A missed red flag costs far more than an unnecessary escalation (C2). An LLM's helpfulness works against escalation. The M1 intake evaluation measured this: emergency recall was 1.0, but urgency accuracy was 0.967, and case urgent-01 (a 2.8 kg weight gain) was read as routine ([reports/intake_m1.json](../reports/intake_m1.json)).

**Options considered.**

| Option | Strength | Weakness |
|---|---|---|
| A. Trust the intake model's urgency alone | No extra code | Measured miss on urgent-01 |
| B. A second LLM as a safety classifier | Catches paraphrases | Same failure mode as A; more tokens |
| C. Code: red-flag phrases plus the patient's own care-plan measurement rules, combined with intake urgency by logical OR; it can only raise the level | Deterministic, testable, cannot be talked out of escalating | No phrase list is complete; may over-escalate |

**Decision and rationale.** Option C. The level is the highest of: a red-flag phrase in the raw text (emergency), a warning sign in the patient's current plan whose measurement rule matches (that sign's severity), and the intake urgency. No downstream node can lower it, and emergency replies are fixed templates. The OR rule is judgment that favours recall. The measurement rule is backed by the measured urgent-01 miss.

Amendments:

- **2026-11-15 ([9ce8e9c]).** If intake fails, the gate cannot read measurements, so the hand-off is created as urgent.
- **2026-11-20 ([55f0fcc]).** Text is normalised (apostrophes, hyphens, spacing, contractions) and phrases match as whole words with plurals. More phrasings were added, including a phrase for every rule-less emergency sign in the seeded plans. A measurement rule fires if any reading in the message crosses it. Scenarios rf-04 and rf-05 deliberately stay worded outside the list, to test the intake path.
- **2026-11-20 ([b69df5a]).** Superseded in part: before this, any new message during a pending yes/no confirmation was refused with 409. Now a message with a red-flag phrase declines the pending change and escalates. Other messages still get 409.
- **2026-11-20 ([b69df5a]).** Repeat escalations after an emergency (the intake model reads the earlier turn) are accepted as erring on the safe side and disclosed in [docs/report.md](report.md) section 4.

**Consequences and trade-offs.** A question that mentions a red-flag phrase, such as "what if I get chest pain?", is escalated. Coordinators may get duplicate tasks after an emergency. Coverage of paraphrases still depends on the intake model.

**Evidence and validation.** M8 (code at [9ce8e9c]): missed escalation 0/10 for CareFlow, including the two paraphrased explicit red flags, which reached the gate through intake urgency; false escalation 0%. Tests: [tests/test_gate.py](../tests/test_gate.py) `test_red_flag_phrasings_escalate`, `test_rule_less_emergency_signs_are_red_flags`, `test_any_reading_over_the_limit_escalates`, `test_ordinary_messages_do_not_escalate`, `test_highest_rule_wins_over_lower_intake_urgency`; [tests/test_workflow.py](../tests/test_workflow.py) `test_red_flag_overrides_routine_intake`, `test_intake_failure_still_errs_towards_escalation`; [tests/test_api.py](../tests/test_api.py) `test_red_flag_during_pending_confirmation_escalates`, `test_pending_confirmation_blocks_new_messages`. The 2026-11-20 amendments are covered by these tests only, not by a new end-to-end run.

**Revisit trigger.** Any missed escalation (more than 0 red-flag cells) in a re-run of the suite, or a false escalation rate above 0% in the non-clinical categories.

---

## ADR-005: Model, provider and LiteLLM gateway (gpt-oss-120b on Groq; supersedes Llama 3.3)

**Date, status and scope.** Gateway decided 2026-11-06 ([2fbbdda], proposal section 4.8) and built 2026-11-06 ([e51e8d7]). Model switched 2026-11-15, during M2. The model name was first committed in `.env.example` on 2026-11-20 ([55f0fcc]); before that the field was blank. Status: Accepted. Supersedes: a Groq Llama 3.3 model used before the M2 build. Scope: every LLM call; M1 to M8.

**Context and decision drivers.** The proposal names open-weight models through OpenAI-compatible providers, configured by environment variables. The project had no budget for paid inference. The model must return valid structured JSON and must fit Groq's free-tier limits: 8,000 tokens per minute, 1,000 requests per day and 200,000 tokens per day per model.

**Options considered.**

| Option | Comment |
|---|---|
| A. Keep the earlier Groq Llama 3.3 model | Already configured; the exact model id was not recorded |
| B. `groq/openai/gpt-oss-120b`, with `groq/openai/gpt-oss-20b` as fallback | Open-weight; same provider and key for the fallback |
| C. A paid proprietary API | Higher limits; costs money; not open-weight |

For the access layer: call the provider SDK directly, or wrap LiteLLM in one gateway module. The gateway was chosen so the provider can change by configuration only.

**Decision and rationale.** Option B, behind a LiteLLM gateway. No side-by-side measurement of A and B was made, so the model choice is judgment: free-tier limits and an open-weight model, as the proposal requires. Only [src/careflow/llm/gateway.py](../src/careflow/llm/gateway.py) imports LiteLLM, which keeps the provider swappable.

**Consequences and trade-offs.** All results are for one model. The free-tier daily quota shaped the evaluation (ADR-017). The intake evaluation report does not record which model produced it; it was run after the switch.

**Evidence and validation.** [.env.example](../.env.example) sets `LLM_MODEL=groq/openai/gpt-oss-120b` and `LLM_FALLBACK_MODEL=groq/openai/gpt-oss-20b`. Every M8 row in [reports/m8/runs.jsonl](../reports/m8/runs.jsonl) carries the model in its fingerprint. Measured with this model: intake emergency recall 1.0, urgency 0.967, item kinds 0.933, injection flag 0.967 on 30 labelled messages ([reports/intake_m1.json](../reports/intake_m1.json)). Tests: [tests/test_architecture.py](../tests/test_architecture.py) `test_litellm_only_in_gateway`; [tests/test_gateway.py](../tests/test_gateway.py) `test_build_llm_requires_model_and_key`.

**Revisit trigger.** The provider retires the model; or intake emergency recall falls below 1.0 on the 30 labelled messages; or the provider's free-tier limit drops below 200,000 tokens per day per model.

---

## ADR-006: Gateway reliability: retry, per-model circuit breakers, fallback model (supersedes per-provider breaker)

**Date, status and scope.** Retry and breaker built 2026-11-15 ([4eafc86], M2). Per-model breakers and fallback built 2026-11-15 ([9ce8e9c], M7). Amended 2026-11-20 ([55f0fcc]: rejections try the fallback; outage vs rejection split). Status: Accepted. Supersedes: the per-provider circuit breaker in the proposal (section 4.8, [2fbbdda]). Scope: [src/careflow/llm/gateway.py](../src/careflow/llm/gateway.py), [src/careflow/llm/reliability.py](../src/careflow/llm/reliability.py).

**Context and decision drivers.** Free-tier providers fail transiently with rate limits and server errors. A failure must not hang a request or loop forever (invariant 7). The fallback model must use the same key and base URL, so it is on the same provider as the primary.

**Options considered.**

| Option | Comment |
|---|---|
| A. Keep one circuit breaker per provider, as proposed | With the fallback on the same provider, an open breaker for the primary would also block the fallback |
| B. One breaker per model | The fallback stays usable while the primary's breaker is open |
| C. Retry only, no breaker | A provider outage would make every request wait through all retries |

**Decision and rationale.** Option B. This follows from the same-provider constraint; it is a logical consequence that a test checks, not a benchmark. Parameters, all judgment, in [src/careflow/config.py](../src/careflow/config.py): `MAX_REPAIRS = 2`, `LLM_MAX_ATTEMPTS = 4`, backoff from `RETRY_BASE_SECONDS = 1` to `RETRY_MAX_SECONDS = 20` with jitter, breaker opens at `BREAKER_FAILURES = 5` in `BREAKER_WINDOW_SECONDS = 60` and cools down for `BREAKER_COOLDOWN_SECONDS = 30`. Amendment on 2026-11-20: a provider rejection (content filter, bad request, authentication) also moves on to the fallback. If every model rejects the request it is reported as a rejection, which the evaluation scores as a failure. An outage (408, 498 or 5xx) still marks an evaluation cell invalid.

**Consequences and trade-offs.** The fallback does not help when the whole provider is down. The evaluation disables the fallback so both systems use one model (ADR-017).

**Evidence and validation.** Tests: [tests/test_reliability.py](../tests/test_reliability.py) `test_transient_error_is_retried`, `test_gives_up_after_max_attempts`, `test_backoff_grows_and_is_capped`, `test_breaker_opens_and_fails_fast`, `test_half_open_success_closes`; [tests/test_gateway.py](../tests/test_gateway.py) `test_open_primary_breaker_does_not_block_fallback`, `test_fallback_answers_when_primary_fails`, `test_unmapped_capacity_and_server_errors_are_outages`, `test_repairs_are_capped`. In M8, 7 rows of [reports/m8/runs.jsonl](../reports/m8/runs.jsonl) were provider-unavailable and were marked invalid, not scored.

**Revisit trigger.** A fallback on a different provider or key is added (breakers would then need provider scope too), or more than 10% of attempted cells in a full trial end as provider-unavailable (M8: 7 of 132 rows, 5.3%).

---

## ADR-007: LangGraph with PostgreSQL checkpointer, one thread per patient request (supersedes thread per conversation)

**Date, status and scope.** LangGraph with the PostgreSQL checkpointer decided 2026-11-06 ([2fbbdda]). Thread per request decided and built 2026-11-15 ([099be4d], M5). Status: Accepted. Supersedes: "conversations (one LangGraph thread each)" in the original proposal ([2fbbdda], section 4.4). Scope: [src/careflow/graph/](../src/careflow/graph/), [src/careflow/db/checkpointer.py](../src/careflow/db/checkpointer.py), the `workflow_runs` table.

**Context and decision drivers.** A hand-off can wait hours for a nurse. The server may restart and the patient may send more messages meanwhile (C4). A crash or retry must never create two bookings.

**Options considered.**

| Option | Comment |
|---|---|
| A. Keep one thread per conversation | A new message would land on a thread that is paused waiting for a coordinator |
| B. One thread per patient request (`workflow_runs`) | A waiting request is not disturbed by later messages |
| C. A hand-written state machine with its own tables, no LangGraph | No framework; must re-implement interrupts, resume and checkpoints |

**Decision and rationale.** LangGraph with `PostgresSaver` (judgment: interrupts and checkpoints are built in, and state lives in the single store, ADR-008), and Option B for threads. B was adopted when the M5 specification was reviewed before building. The same review added: patient confirmation before coordinator approval (ADR-014), a replay-safe executor, checkpointer setup outside the schema transaction, and crash points after each node as well as before. Each node's checkpoint is saved before the next starts (`durability="sync"`), and every node is idempotent.

**Consequences and trade-offs.** More rows and threads per conversation. Recovery needs a script: [scripts/recover_runs.py](../scripts/recover_runs.py) resumes runs idle for more than `RECOVER_AFTER_SECONDS = 300` and skips busy conversations. The escalation, care-plan answer and hand-off nodes are not crash-tested.

**Evidence and validation.** Measured: [tests/test_crash_resume.py](../tests/test_crash_resume.py) `test_crash_at_any_node_resumes_to_same_state` covers 34 crash points (before and after every node on the booking and approval paths): 0 failed, 0 duplicates (`crash_resume` in [reports/m8/summary.json](../reports/m8/summary.json)). Also [tests/test_api.py](../tests/test_api.py) `test_coordinator_decision_resumes_the_run`, `test_broken_checkpointer_connection_is_reopened`; [tests/test_db.py](../tests/test_db.py) `test_checkpoint_tables_exist`, `test_stale_runs_skip_runs_still_in_flight`.

**Revisit trigger.** Any duplicate booking, message or task after a crash, or any failure when crash points are added to the escalation, answer and hand-off nodes.

---

## ADR-008: Single store: PostgreSQL 17 + pgvector

**Date, status and scope.** 2026-11-06 ([2fbbdda], proposal section 4.4); schema built from [e51e8d7] (migration 001) to [099be4d] (migration 005). Status: Accepted. Scope: all data: clinical records, scheduling, conversations, memories, documents and vectors, audit events and workflow checkpoints.

**Context and decision drivers.** The system needs relational integrity (one booking per slot, unique idempotency keys), full-text and vector search, and durable workflow checkpoints. It runs on one laptop (14 GB RAM, CPU only).

**Options considered.**

| Option | Comment |
|---|---|
| A. PostgreSQL with pgvector as the only store | One backup; the database enforces integrity; FTS and vectors in one query layer |
| B. PostgreSQL plus a separate vector database | Purpose-built vector search; two systems to run and keep consistent |
| C. SQLite plus a separate vector index | Lightest setup; weaker concurrency; checkpoints and vectors in different places |

**Decision and rationale.** Option A. This is judgment: one backup covers everything and the database can enforce the integrity rules itself. The corpus is small (18 documents, 96 chunks), so vector search scale is not a concern.

**Consequences and trade-offs.** Docker is required to run the app and the database tests (without the database, 353 tests pass and 199 are skipped). Vectors are passed as text literals, so no pgvector Python package is needed.

**Evidence and validation.** Migrations [001_core.sql to 005_workflow.sql](../src/careflow/db/migrations/); [docker-compose.yml](../docker-compose.yml) uses `pgvector/pgvector:pg17`. Tests: [tests/test_db.py](../tests/test_db.py) `test_slot_cannot_be_double_booked`, `test_idempotency_key_is_unique`, `test_only_one_published_plan_per_patient`, `test_only_one_pending_confirmation_per_conversation`; [tests/test_architecture.py](../tests/test_architecture.py) `test_database_driver_only_in_db_package`. Full suite at [b69df5a]: 553 passed with the database up.

**Revisit trigger.** The corpus grows past 100,000 chunks, or retrieval latency (search plus rerank) exceeds 1 s at p95 for a single question.

---

## ADR-009: Tool layer: three MCP servers bound to the session patient

**Date, status and scope.** Named in the proposal 2026-11-06 ([2fbbdda]); built 2026-11-15 ([ddaed7d], M6). Status: Accepted. Scope: [src/careflow/mcp_servers/](../src/careflow/mcp_servers/); the workflow and the baseline.

**Context and decision drivers.** A prompt injection must not reach another patient's data (invariant 3). Only the executor may write (invariant 2). For a fair comparison, CareFlow and the baseline must use exactly the same tools (RQ1).

**Options considered.**

| Option | Comment |
|---|---|
| A. Keep the M2 Python function tools | Simplest; already built and tested |
| B. Three MCP servers (`records`, `knowledge`, `actions`), in-process memory transport | Standard tool interface, one tool set for both systems, clear read/write split |
| C. MCP servers over stdio or HTTP for every call | Process isolation; extra latency and process management |

**Decision and rationale.** Option B, using the MCP Python SDK's `MCPServer` (the renamed FastMCP, `mcp==2.3.0`). Each server is built per request and bound to the session's patient, so no tool takes a patient id. Deterministic safety code (gate, verifier, executor replay check) reads the database directly, so it does not depend on the tool layer. [scripts/serve_mcp.py](../scripts/serve_mcp.py) serves `records` and `knowledge` over stdio for external clients and refuses `actions`. These choices are judgment. In-process calls were observed at about 4 ms each during development; no benchmark file was saved.

**Consequences and trade-offs.** More code than plain functions (a typed client and an envelope format). The tool layer adds a dependency on the MCP SDK.

**Evidence and validation.** Tests: [tests/test_architecture.py](../tests/test_architecture.py) `test_tool_args_never_take_patient_id`, `test_repository_writes_only_called_from_actions_server`, `test_server_modules_only_imported_by_client`, `test_mcp_package_only_in_mcp_servers`, `test_agents_read_tool_data_through_mcp`; [tests/test_mcp_servers.py](../tests/test_mcp_servers.py) `test_each_server_lists_exactly_its_tools`, `test_records_are_patient_scoped`, `test_extra_patient_id_argument_has_no_effect`, `test_actions_cannot_touch_other_patients`, `test_baseline_arguments_match_mcp_schemas`. M8 injection resistance: CareFlow 5/5, baseline 4/5 (the one baseline failure was an action taken, not a data leak).

**Revisit trigger.** The tools must be served to another process or host, or MCP overhead exceeds 10% of median turn latency (now 1,212 ms at p50).

---

## ADR-010: Security and trust model (demo login, coordinator token, locks, input validation, no content in traces)

**Date, status and scope.** Demo login 2026-11-15 ([4eafc86], M2). Coordinator token 2026-11-15 ([099be4d]). No content in traces 2026-11-15 ([9ce8e9c]). Locks and input validation 2026-11-20 ([55f0fcc]). Status: Accepted for synthetic data only. Scope: [src/careflow/api/](../src/careflow/api/), [src/careflow/observability/tracing.py](../src/careflow/observability/tracing.py).

**Context and decision drivers.** All data is synthetic, and the project had one month. The trust boundaries that matter to the research question are between the patient's text, the models and the write tools, and between patients. Two requests on one conversation at once could double-apply a decision.

**Options considered.**

| Option | Comment |
|---|---|
| A. Real authentication (passwords or an identity provider) and role-based access | Needed for real use; out of scope for a synthetic prototype |
| B. Demo login by seeded patient id, a random session token, and a shared coordinator token | Enough to enforce per-patient scoping and test it |
| C. No login at all | Would make patient scoping untestable |

**Decision and rationale.** Option B, as judgment for a synthetic-data prototype:

- Patients sign in with a seeded id and no password. Sessions hold a 32-byte random token and live in memory (lost on restart).
- The coordinator API needs an `X-Coordinator-Token` header, compared in constant time.
- The patient id for every tool call comes from the session, never from model output (ADR-009).
- One request at a time may change a conversation or a coordinator task (PostgreSQL advisory locks). A busy conversation gets 423; a confirmation or decision already handled gets 409.
- Text the database cannot store (NUL bytes, unpaired surrogates) is rejected with 422 without echoing the input.
- Spans carry no prompt, reply or patient text. An attribute allowlist test enforces this. `careflow.patient_id` on spans is acceptable only because the data is synthetic.

**Consequences and trade-offs.** Anyone who can reach the API can sign in as any seeded patient. The system must not be used with real data.

**Evidence and validation.** Tests in [tests/test_api.py](../tests/test_api.py): `test_unknown_patient_cannot_sign_in`, `test_posting_without_token_is_rejected`, `test_other_patients_conversation_is_hidden`, `test_coordinator_endpoints_need_the_token`, `test_non_ascii_coordinator_token_is_forbidden`, `test_busy_conversation_is_refused`, `test_unstorable_text_is_bad_input`, `test_approval_for_a_run_in_flight_is_refused`. [tests/test_tracing.py](../tests/test_tracing.py) `test_spans_carry_no_patient_text`. [tests/test_tools.py](../tests/test_tools.py) `test_another_patients_key_is_never_replayed`.

**Revisit trigger.** Any use with a single real patient record, or any deployment beyond one local machine. Either requires real authentication and hashed patient ids in traces first.

---

## ADR-011: Retrieval: hybrid FTS + dense with RRF and cross-encoder rerank

**Date, status and scope.** Decided 2026-11-06 ([2fbbdda], proposal section 4.5); built 2026-11-15 ([0c3ebe4], M4). Status: Accepted. Scope: [src/careflow/knowledge/](../src/careflow/knowledge/), the `knowledge` MCP server, the care-plan answerer.

**Context and decision drivers.** Answers must come from this patient's current plan (C3). Outdated plan versions exist as traps. Questions mix exact terms (drug names, test codes) with paraphrases. Everything runs on a laptop CPU.

**Options considered.**

| Option | Comment |
|---|---|
| A. Dense retrieval only | Simplest; good on paraphrases |
| B. Hybrid: PostgreSQL full-text plus dense, fused with Reciprocal Rank Fusion | Also catches exact terms |
| C. Hybrid plus a cross-encoder rerank from 20 candidates to 4 | Fewer, better chunks in the prompt; extra CPU time |

**Decision and rationale.** Option C. The pipeline: metadata filter to the patient's current documents and shared guides for the patient's conditions, FTS plus `BAAI/bge-small-en-v1.5` embeddings (384-d, fastembed ONNX on CPU), RRF with `RRF_K = 60`, `RECALL_CANDIDATES = 20` reranked by `BAAI/bge-reranker-base` down to `CONTEXT_CHUNKS = 4`. Measured on 53 covered golden questions: recall@5 is 1.0 in all three modes; MRR is 0.964 dense, 0.950 hybrid and 0.976 hybrid plus rerank; stale hits 0. Hybrid alone gave no measured gain on this corpus. Keeping it is judgment: the corpus is small and saturated, and exact drug and test terms are expected on a larger one.

**Consequences and trade-offs.** Two local models (about 1.2 GB, not committed) must be downloaded. The corpus is Markdown only (no PDF parsing), and the knee-replacement protocol became hip replacement, with pneumonia added. All corpus documents were written by the team for this project and are not clinically reviewed.

**Evidence and validation.** [reports/retrieval_m4.json](../reports/retrieval_m4.json), produced by [scripts/eval_retrieval.py](../scripts/eval_retrieval.py) from [src/careflow/evaluation/data/rag_golden.jsonl](../src/careflow/evaluation/data/rag_golden.jsonl) (60 questions, 53 covered). Tests: [tests/test_search.py](../tests/test_search.py) `test_rrf_fuse_rewards_agreement`, `test_superseded_plan_is_never_ranked`, `test_only_own_current_and_matching_shared_documents_are_visible`, `test_keyword_search_finds_exact_drug_name`.

**Revisit trigger.** On a golden set of at least 200 questions, drop the reranker if hybrid plus rerank beats dense MRR by less than 0.01, and drop FTS if hybrid beats dense MRR by less than 0.01.

---

## ADR-012: Cite or hand off: code-level citation check

**Date, status and scope.** Decided 2026-11-06 ([2fbbdda], invariant 5); built 2026-11-15 ([0c3ebe4], M4). Status: Accepted. Scope: [src/careflow/agents/careplan.py](../src/careflow/agents/careplan.py).

**Context and decision drivers.** A confident clinical answer that is not in the patient's plan can harm (C3). The research question targets zero unsupported clinical answers.

**Options considered.**

| Option | Comment |
|---|---|
| A. Ask for citations in the prompt only | No code; the model can still answer without sources |
| B. The model returns sentences with source labels; code checks that every sentence cites a retrieved chunk, otherwise the question is handed off | Deterministic and cheap; checks presence of a valid citation, not that the chunk supports the claim |
| C. A second LLM verifies support at run time | Checks content; doubles model calls; same model family can share blind spots |

**Decision and rationale.** Option B. The answer is a structured list of sentences with source labels. Code hands off when there are no chunks (without calling the model), when the model says the question is not covered, when the call fails, or when any sentence lacks a valid source. Retrieved text is wrapped as source-tagged data. The choice is judgment on cost and determinism. Its limit is known: the check is structural, not semantic.

**Consequences and trade-offs.** Some covered questions are handed off. Support of the claim by the chunk is not checked at run time; it is measured afterwards by an LLM judge (ADR-017).

**Evidence and validation.** Measured in M4 ([reports/careplan_m4.json](../reports/careplan_m4.json)): 53/53 covered questions answered with relevant citations; 7/7 uncovered handed off. Measured in M8: false hand-off 1/8 (12.5%, q-07); the judge flagged 7 of 17 CareFlow answers (41%) as having at least one unsupported claim, mostly fixed template sentences, against 4 of 18 (22%) for the baseline. The zero-unsupported target is not shown. Tests: [tests/test_careplan.py](../tests/test_careplan.py) `test_unsupported_answers_hand_off`, `test_no_chunks_hands_off_without_llm_call`, `test_invalid_output_hands_off`, `test_chunk_text_is_wrapped_as_source_data`, `test_cited_answer_renders_sources`.

**Revisit trigger.** A hand-checked sample of at least 30 judged claims shows any unsupported claim in a cited (non-template) sentence, or false hand-off on covered questions exceeds 25% (2 of 8).

---

## ADR-013: Memory design and clinical guard (episodic guard added 2026-11-20)

**Date, status and scope.** Decided 2026-11-06 ([2fbbdda], proposal section 4.6); built 2026-11-15 ([f8afabb], M3). Amended 2026-11-20 ([b69df5a]). Status: Accepted. Scope: [src/careflow/memory/](../src/careflow/memory/), [src/careflow/safety/memory_guard.py](../src/careflow/safety/memory_guard.py).

**Context and decision drivers.** Remembering preferences improves service. A remembered chat line such as "I stopped taking metoprolol" must not change the medication list (C5). Clinical facts must come only from the record (invariant 6).

**Options considered.**

| Option | Comment |
|---|---|
| A. No long-term memory; conversation history only | Simplest; no continuity across sessions |
| B. Free-text memories written by the model | Flexible; clinical facts can slip in |
| C. CoALA types: working (rolling summary), episodic (session summaries), semantic (a fixed set of non-clinical keys, superseded on key), with a deterministic clinical guard | Bounded, testable; may drop useful facts |

**Decision and rationale.** Option C. The working summary folds older turns when the context exceeds `WORKING_TOKEN_BUDGET = 1500`. Semantic memory accepts only fixed non-clinical keys (preferred days, time of day, clinician, transport, caregiver, contact method and time, accessibility need). A new value supersedes the old one. A deterministic guard rejects clinical values. The design is judgment based on CoALA, cited in the proposal. Superseded in part on 2026-11-20 ([b69df5a]): before, only semantic memory was guarded, so invariant 6 did not hold for episodic summaries. Now clinical sentences are removed from session summaries, and a summary that is wholly clinical is not stored and is audited. The guard also catches number-and-unit doses, blood-pressure readings and common drug and diagnosis names ([55f0fcc]).

**Consequences and trade-offs.** The guard is keyword based. It can drop harmless sentences, and it can miss clinical wording it does not list. Memories link to the source conversation, not the source message.

**Evidence and validation.** Measured in M3 ([reports/memory_m3.json](../reports/memory_m3.json), 8 cases): summary fact survival 0.926 (target at least 0.9), semantic recall 0.933, the guard blocked 1 clinical fact. In M8, memory scenarios trial 1: CareFlow 5/5, baseline 2/5. The 2026-11-20 amendment is covered by tests only. Tests: [tests/test_memory_guard.py](../tests/test_memory_guard.py) `test_clinical_text_is_flagged`, `test_clinical_sentences_are_removed`; [tests/test_memory_manager.py](../tests/test_memory_manager.py) `test_wholly_clinical_episode_is_not_stored`, `test_clinical_value_is_rejected_and_audited`, `test_new_value_supersedes_old`; [tests/test_architecture.py](../tests/test_architecture.py) `test_semantic_keys_are_not_clinical`.

**Revisit trigger.** Summary fact survival falls below 0.9, or any clinical fact is found stored in any memory type in an evaluation.

---

## ADR-014: Scheduling: LLM interprets, code chooses slot, verifier, confirmation before coordinator approval

**Date, status and scope.** 2026-11-15 ([099be4d], M5). Status: Accepted. Scope: [src/careflow/agents/scheduler.py](../src/careflow/agents/scheduler.py), [src/careflow/safety/verifier.py](../src/careflow/safety/verifier.py), [src/careflow/graph/executor.py](../src/careflow/graph/executor.py).

**Context and decision drivers.** Bookings must respect care-plan deadlines and specialties. A model that picks slot ids can invent them. Out-of-plan changes need a nurse, but the patient should agree to a change before the nurse is asked.

**Options considered.**

| Option | Comment |
|---|---|
| A. The model picks the slot from a list (as the baseline does) | Fewer steps; the model can invent or misread ids |
| B. The model only interprets the request (action, item, date window, part of day); code picks the first fitting free slot; a code verifier checks the plan | Slot ids never come from the model |
| C. For out-of-plan changes: coordinator approval first, then patient confirmation | The nurse may approve a change the patient then rejects |
| D. For out-of-plan changes: patient confirmation first, then coordinator approval | The nurse sees only changes the patient wants |

**Decision and rationale.** B and D. The planner returns a structured request; `choose_slot` picks the slot; the verifier approves, rejects (fixable or not) or requires coordinator approval (not in plan, past the due date, cancelling a plan item). Fixable rejections are replanned at most `MAX_REPLANS = 2` times, then handed off. Only the executor writes, with an idempotency key. B and D are judgment. D was adopted when the M5 specification was reviewed before building.

**Consequences and trade-offs.** Requests with no fitting slot are handed off rather than negotiated. The patient may wait hours for approval after saying yes.

**Evidence and validation.** Measured in M8 trial 1: routine scheduling 10/10 vs 6/10, approval scheduling 5/5 vs 4/5; CareFlow completes the booking after coordinator approval in 5/5 cells. The baseline quoted made-up slot ids (`slot123`, `lab1`), which option B prevents ([docs/report.md](report.md), RQ1). Tests: [tests/test_scheduler.py](../tests/test_scheduler.py) `test_choose_slot`; [tests/test_verifier.py](../tests/test_verifier.py) `test_verdicts`; [tests/test_workflow.py](../tests/test_workflow.py) `test_in_plan_booking_needs_patient_confirmation`, `test_booking_past_due_date_waits_for_coordinator`, `test_replans_are_capped_then_handed_off`, `test_part_of_day_picks_a_matching_slot`.

**Revisit trigger.** More than 10% of routine scheduling cells in a full trial end in a hand-off because no slot fitted, or routine scheduling success falls below 9/10.

---

## ADR-015: Observability, budgets and cost accounting

**Date, status and scope.** 2026-11-15 ([9ce8e9c], M7). Status: Accepted. Scope: [src/careflow/observability/](../src/careflow/observability/), the gateway, the supervisor, audit events.

**Context and decision drivers.** The evaluation needs tokens, cost and latency per request. A coordinator should be able to go from a decision to its full trace. Every loop needs a cap, including tokens and time (invariant 7). Traces must not leak patient text (ADR-010).

**Options considered.**

| Option | Comment |
|---|---|
| A. Application logs and audit rows only | No extra service; no span tree, so per-node timing is lost |
| B. OpenTelemetry spans to a self-hosted Phoenix, plus audit rows carrying the trace id | Standard, local, per-node detail |
| C. A hosted tracing service | No local service; sends data off the machine |

For budgets: per model call, per conversation, or per API request.

**Decision and rationale.** Option B, with one budget per API request: 30,000 tokens and 120 s (`REQUEST_TOKEN_BUDGET`, `REQUEST_TIME_BUDGET_SECONDS`). The gateway checks the budget before every model call and the supervisor before every item; a spent budget becomes a hand-off that lists the items left undone. Cost is the LiteLLM list price for the requested model string, from the local price map of the pinned version. These values are judgment. Observed during development: about 1.5k to 2.1k tokens per request.

**Consequences and trade-offs.** Phoenix is one more container. On the free tier the real cost is $0, so cost figures are list-price equivalents. Per-scenario traces were exported but not summarised in the report.

**Evidence and validation.** Measured in M8: tokens per resolved scenario 2,140 vs 8,633; cost per resolved scenario USD 0.00061 vs 0.00200; latency per turn p50/p95 1,212/4,136 ms vs 2,917/6,383 ms. Tests: [tests/test_tracing.py](../tests/test_tracing.py) `test_each_invocation_is_one_root_span_with_node_children`, `test_audit_rows_carry_the_invocation_trace_id`, `test_spans_carry_no_patient_text`; [tests/test_budget.py](../tests/test_budget.py) `test_budget_exceeded`, `test_nested_request_joins_the_outer_budget`; [tests/test_workflow.py](../tests/test_workflow.py) `test_spent_budget_hands_off_before_planning`; [tests/test_gateway.py](../tests/test_gateway.py) `test_spent_budget_stops_before_calling_any_model`, `test_usage_and_cost_are_recorded`; [tests/test_architecture.py](../tests/test_architecture.py) `test_opentelemetry_only_in_observability`.

**Revisit trigger.** More than 1% of requests in a full trial end in a budget hand-off, or p95 turn latency exceeds 10 s.

---

## ADR-016: UI transport: request-per-turn plus polling instead of SSE; desktop only (supersedes SSE)

**Date, status and scope.** Polling built 2026-11-15 ([ddaed7d], M6). Architecture document updated 2026-11-16 ([4b93908]). Desktop-only layout decided 2026-11-18 and committed 2026-11-20 ([55f0fcc]). Status: Accepted. Supersedes: the Server-Sent Events stream of progress events in the proposal (sections 4.1, 4.9 and 4.10, [2fbbdda]). Scope: [frontend/](../frontend/), [src/careflow/api/app.py](../src/careflow/api/app.py).

**Context and decision drivers.** The workflow and MCP calls are synchronous, and running them per call inside an event loop does not work, so streaming would need the graph moved to a worker thread. A coordinator's decision can arrive hours later, so the chat must show new messages without a page reload. Time was limited.

**Options considered.**

| Option | Comment |
|---|---|
| A. Keep SSE progress events, as proposed | Patient sees "checking your care plan..."; needs a worker thread and an event channel |
| B. One HTTP request per turn, plus polling the conversation every 10 s | Simple; works with synchronous code; no live progress |
| C. WebSockets | Two-way and live; the most new code |

**Decision and rationale.** Option B. The chat waits for each reply in one request and reloads the conversation every 10 seconds (`CHAT_POLL_MS = 10000`). This is judgment on effort and risk. SSE was first deferred to a later milestone and then dropped. Amended 2026-11-20 ([55f0fcc]): the interface is a desktop website only. A phone layout was built on 2026-11-18 and removed the same day by the team's decision.

**Consequences and trade-offs.** The patient sees a waiting state instead of progress steps. A coordinator's reply can take up to 10 s to appear. The portal has chat only: no care-plan, appointments or past-conversations panel. The layout needs a window at least 1,100 px wide.

**Evidence and validation.** [frontend/src/App.tsx](../frontend/src/App.tsx) (`CHAT_POLL_MS`), [frontend/src/styles.css](../frontend/src/styles.css) (`min-width: 1100px`), [docs/architecture.md](architecture.md), [docs/report.md](report.md) section 5. Tests: [tests/test_api.py](../tests/test_api.py) `test_message_gets_reply_and_is_stored`, `test_coordinator_decision_resumes_the_run`. M8 latency per turn p50/p95: 1,212/4,136 ms (CareFlow).

**Revisit trigger.** CareFlow p95 turn latency exceeds 10 s, at which point progress events would be worth the work, or mobile use becomes a requirement.

---

## ADR-017: Evaluation methodology (scripted scenarios, DB-state scoring, trial-1 headline, personas dropped)

**Date, status and scope.** Built 2026-11-16 ([19abd0f], M8). Evaluation data first tracked 2026-11-20 ([55f0fcc]). Headline changed to trial 1, decided 2026-11-18 and committed 2026-11-20 ([55f0fcc]). Status: Accepted. Supersedes in part: the proposal's evaluation plan (section 5, [2fbbdda]) for personas, `pass^k`, the unsupported-answer definition and response caching. Scope: [src/careflow/evaluation/](../src/careflow/evaluation/), [scripts/eval_e2e.py](../scripts/eval_e2e.py), [scripts/eval_report.py](../scripts/eval_report.py), [reports/m8/](../reports/m8/).

**Context and decision drivers.** RQ1 to RQ4 must be answered fairly for both systems. Groq's free tier allows 200,000 tokens per day per model and 8,000 tokens per minute. One trial of both systems used about 376k tokens plus unmetered judge calls, so one trial took several days.

**Options considered.**

| Topic | Kept from the proposal | Alternative chosen | Why |
|---|---|---|---|
| Patients | Scripted messages and LLM-simulated personas | Scripted messages only | Personas would roughly double the requests (judgment, from the measured quota) |
| Repeats | `pass^3` over three trials | Trial 1 complete; trial 2 partial (13 scenarios); trial 3 not run; `pass^3` not reported | Quota (measured) |
| Headline | Pooled success over all valid cells | Trial 1, where both systems ran the same 50 scenarios | Trial 2 covers only scheduling, the baseline's weakest category, so pooling lowers the baseline unfairly (judgment) |
| Unsupported answers | Claim-level, cited chunks, hand-checked sample | Answer-level, judged by the same model, blind to the system | The baseline cites as free text, so citation faithfulness cannot be compared |
| Cost control | Cache responses | Not implemented | Dropped for time; disclosed in [docs/report.md](report.md) section 5 |

**Decision and rationale.** 50 scripted scenarios in the proposal's mix. Each cell (scenario, system, trial) runs on a fresh clone of one seeded database with the clock frozen at 2026-11-02, model `groq/openai/gpt-oss-120b` at temperature 0, and the fallback disabled. Scoring is by database state after every step (exact bookings, nothing written before the patient's yes, tasks of the right priority), not by reply wording. Approval scenarios are scored only on outcomes both systems can reach. Provider outages make a cell invalid, never a failure. Harness bugs found during the run were fixed, and the affected rows are kept in `reports/m8/runs_discarded_*.jsonl`.

**Consequences and trade-offs.** Scripted patients answer a confirmation once, which penalises a system that asks twice. No consistency metric over three trials. The unsupported-answer target of 0 is not demonstrated: the judge's hand check was not saved, and the `hand_check_sample` field holds the judge's own labels. The fixes in [55f0fcc] and [b69df5a] were not re-evaluated end to end.

**Evidence and validation.** Measured ([reports/m8/summary.json](../reports/m8/summary.json), [reports/m8/summary.md](../reports/m8/summary.md), raw rows in [reports/m8/runs.jsonl](../reports/m8/runs.jsonl)): trial 1 CareFlow 49/50 (98%), baseline 38/50 (76%; 36/50 as stored, q-06 and q-07 re-scored by [scripts/eval_report.py](../scripts/eval_report.py)); trial 2 CareFlow 13/13, baseline 4/12; pooled 62/63 vs 42/62 over 125 valid cells. Scenario file [scenarios.jsonl](../src/careflow/evaluation/data/scenarios.jsonl), sha256 prefix `ed1f45d8c92f`, recorded in every row's fingerprint. Tests: [tests/test_scenarios.py](../tests/test_scenarios.py) `test_suite_has_the_proposal_mix`, `test_reply_checks_ignore_typographic_spaces_and_dashes`; [tests/test_metrics.py](../tests/test_metrics.py) `test_pass_hat_k_uses_scenarios_complete_for_both_systems`, `test_invalid_cells_are_not_scored`; [tests/test_eval_systems.py](../tests/test_eval_systems.py) `test_eval_settings_disable_the_fallback`, `test_provider_outage_makes_the_cell_invalid`, `test_baseline_booking_without_asking_fails_confirmed_first`.

**Revisit trigger.** Quota allows three full trials (at least about 1.2M tokens for both systems): run them and report `pass^3`. If a hand check of at least 30 judged claims agrees with the judge on less than 80% of them, replace the judge.

---

## ADR-018: Milestone order realigned to the proposal (M7 observability, M8 evaluation)

**Date, status and scope.** 2026-11-15 to 2026-11-16 (commit messages of [9ce8e9c], 2026-11-15, "Add M7: OpenTelemetry tracing..." and [19abd0f], 2026-11-16, "Add M8: end-to-end evaluation suite..."). Status: Accepted. Scope: the M7 and M8 milestones.

**Context and decision drivers.** The proposal's milestone plan (section 6) puts observability and reliability in M7 and the end-to-end evaluation in M8. While building M5 and M6, the team's working plan had swapped them: evaluation as M7, and observability with SSE as M8. The evaluation needs token, cost and latency data from the observability layer.

**Options considered.**

| Option | Comment |
|---|---|
| A. Keep the working plan: evaluation in M7, observability in M8 | Results earlier; the evaluation would lack token, cost and latency data and would need re-running |
| B. Return to the proposal's order: observability in M7, evaluation in M8 | Evaluation measures the finished system, with cost and latency; matches the approved plan |

**Decision and rationale.** Option B. This is judgment: the evaluation should run once, on the system with budgets, fallback and metering in place, and the milestones should match the approved proposal.

**Consequences and trade-offs.** The evaluation started on 2026-11-15, late in the month. The daily quota (ADR-017) then limited how many trials could run.

**Evidence and validation.** The earlier working plan was not committed, so the realignment is visible only in the milestone commit messages and contents. [docs/proposal.tex](proposal.tex) section 6 (M7 "Observability + reliability", M8 "End-to-end evaluation"); commits [9ce8e9c] (M7) and [19abd0f] (M8); the per-cell usage meter in [src/careflow/observability/meter.py](../src/careflow/observability/meter.py), used by the M8 harness.

**Revisit trigger.** Any future milestone plan that runs an evaluation before metering is in place, or a milestone delivered out of the order in the proposal; either needs a new ADR.

---

[2fbbdda]: https://github.com/saideepaksana/careflow/commit/2fbbddaf960d389ecba27a4395736b2ae7697bb7
[e51e8d7]: https://github.com/saideepaksana/careflow/commit/e51e8d74675b238b339b75b3e44c518457a8ba8e
[4eafc86]: https://github.com/saideepaksana/careflow/commit/4eafc86c6667f084771302de961509003f2208a8
[f8afabb]: https://github.com/saideepaksana/careflow/commit/f8afabb303cc298303de8f03347d11faa7cdc84d
[0c3ebe4]: https://github.com/saideepaksana/careflow/commit/0c3ebe4388552c4abcad75d5d0da32b72c5a2726
[099be4d]: https://github.com/saideepaksana/careflow/commit/099be4d5859f2cb36d57f3ed78f2bfc1d3e70098
[ddaed7d]: https://github.com/saideepaksana/careflow/commit/ddaed7df4d47153f6547926f4692906672e561d6
[9ce8e9c]: https://github.com/saideepaksana/careflow/commit/9ce8e9c70a78b267d6c26e83e712f60214e924cb
[19abd0f]: https://github.com/saideepaksana/careflow/commit/19abd0f1e0645c6d5910783c5723d3122e7f8932
[4b93908]: https://github.com/saideepaksana/careflow/commit/4b939086f769434e9c57b54e26922e3708646f90
[55f0fcc]: https://github.com/saideepaksana/careflow/commit/55f0fcc0e63fcaf66c48fbeb3e697754af47c28c
[b69df5a]: https://github.com/saideepaksana/careflow/commit/b69df5aaf6a3d9ba9f89dd05a74e3e47909b07f5
