# CareFlow

CareFlow is a multi-agent care-coordination assistant for patients in the 30 days after hospital discharge, and for the nurse coordinators responsible for them. It completes routine coordination work on its own: structured intake, follow-up scheduling within care-plan rules, and answers grounded in the patient's own discharge plan. Red flags and out-of-scope clinical questions always go to a human coordinator, through a durable workflow that can pause and resume.

**Research question:** can a multi-agent design with deterministic safety gates and a durable human-in-the-loop handoff correctly resolve more routine requests than a single tool-using agent, while keeping missed escalations and unsupported clinical answers at zero?

CS5903 Distributed AI Training, Pillar 1 (agentic systems). Project ID 11, Group 24. Sai Deepak (cs23btech11055) and Harshith (cs23btech11045).

Final submission: tag `cs5903-final-2026`. The evaluated code is identified on the cover of the [report](docs/Project_Report.pdf).

## Documentation

| Document | Contents |
|---|---|
| [Project report (PDF)](docs/Project_Report.pdf) and [source](docs/Project_Report.tex) | Problem, architecture, method, results, limitations, way forward, contributions |
| [Architecture Decision Records](docs/Architecture_Decision_Records.md) | ADR-001 to ADR-018, including the 9 October 2026 methodology record |
| [Final presentation (PDF)](docs/Final_Presentation.pdf) and [source](docs/Final_Presentation.tex) | Slides |
| [Architecture](docs/architecture.md) | Components, permissions, data model, invariants |
| [Evaluation notes](docs/report.md) | Detailed evaluation narrative and the fixes made during and after the evaluation |
| [Proposal (PDF)](docs/proposal.pdf) and [source](docs/proposal.tex) | The approved plan and milestones, approved at commit 2fbbdda (2026-11-06); two lines were updated on 2026-11-15 |
| [Evaluation summary](reports/m8/summary.md) | Generated end-to-end results table |
| [Demo recording](https://drive.google.com/drive/folders/1p8mAcPHe7_rEOtD2hie6rbNffb_X9GL2?usp=sharing) | Narrated presentation and live demo video (Google Drive) |

## Status

| | |
|---|---|
| Working | M1 to M7 as built: LLM gateway and structured intake, baseline agent and idempotent tools, memory with clinical guard, hybrid RAG with cited answers, LangGraph workflow with Postgres checkpoints, three MCP servers and the coordinator console, tracing, budgets and fallback. M8 harness, with trial 1 complete for all 50 scenarios on both systems. 553 automated tests pass. |
| Partial | M8 repeats: trial 2 reached 13 to 14 scenarios and trial 3 was not run, so `pass^3` is not reported. The unsupported-answer metric is judge-only and answer-level. Crash-resume covers the booking and approval paths only. The patient portal has chat only, with no care-plan, appointment or history panels. Phoenix traces are exported but not summarised per scenario. |
| Not done | LLM-simulated patient personas, SSE streaming (the chat polls instead), PDF ingestion, response caching, real authentication. The fixes committed on 2026-11-20 (55f0fcc, b69df5a) were not re-evaluated end to end; only the unit tests were run on them. |

## Architecture

```text
patient message -> intake (LLM, no tools) -> safety gate (code)
    red flag  -> escalation task for a coordinator, fixed reply             -> finalize
    otherwise -> supervisor, one item at a time:
        care-plan question          -> care-plan agent (hybrid RAG, cited)
        appointment request         -> planner -> verifier -> patient confirms
                                       -> (out of plan: coordinator approves) -> executor (only writer)
        symptom or clinical request -> hand-off task for a coordinator
    -> finalize
```

FastAPI serves the patient portal and the coordinator console (React + TypeScript). The workflow is a LangGraph graph whose state is checkpointed in PostgreSQL after every node. Agents reach data only through three MCP servers (`records`, `knowledge`, `actions`) that are bound to the session's patient. PostgreSQL with pgvector is the only store. Traces go to a local Phoenix. See [docs/architecture.md](docs/architecture.md) for the full picture and invariants.

## Repository layout

| Path | Contents | Milestone |
|---|---|---|
| `src/careflow/llm/` | Provider-agnostic LLM gateway, structured output and repair loop, retry, circuit breaker | M1, M7 |
| `src/careflow/db/` | PostgreSQL migrations, repository, synthetic seed data, checkpointer | M1, M5 |
| `src/careflow/agents/` | Intake, care-plan answerer, scheduling planner, single-agent baseline | M1, M2, M4, M5 |
| `src/careflow/safety/` | Red-flag gate, deterministic verifier, clinical memory guard | M3, M5 |
| `src/careflow/mcp_servers/` | `records` (read-only), `knowledge` (search), `actions` (write) MCP servers | M6 |
| `src/careflow/memory/` | Working, episodic and semantic memory; consolidation | M3 |
| `src/careflow/knowledge/` | Ingestion, chunking, hybrid retrieval, reranking | M4 |
| `src/careflow/graph/` | LangGraph state, nodes, routing, executor, interrupts | M5 |
| `src/careflow/api/` | FastAPI app: demo login, conversations, confirmation, coordinator actions | M2, M5, M6 |
| `src/careflow/observability/` | OpenTelemetry tracing, request budgets, usage metering | M7, M8 |
| `src/careflow/evaluation/` | Scenario, golden-set and labelled data (`data/`), systems under test, metrics, judge | M1, M3, M4, M8 |
| `frontend/` | React + TypeScript patient portal and coordinator console | M2, M6 |
| `corpus/` | Per-patient discharge plans, condition protocols and operational FAQs (Markdown) | M4 |
| `scripts/` | Ingest, MCP stdio server, run recovery and evaluation entry points | M4 to M8 |
| `tests/` | pytest suite, including architecture and permission tests | all |
| `reports/` | Saved evaluation results: `intake_m1.json`, `memory_m3.json`, `retrieval_m4.json`, `careplan_m4.json`, `m8/` | M1, M3, M4, M8 |

## Prerequisites

Tested with Python 3.14.7, Node 22.23.4, npm, and Docker with Compose v2 on Linux (Intel i5-1335U, 14 GB RAM, CPU only). `pyproject.toml` allows Python 3.11 and later, but only 3.14.7 was tested.

Dependencies are pinned in [requirements.lock](requirements.lock) (the tested Python environment), [frontend/package-lock.json](frontend/package-lock.json), and [docker-compose.yml](docker-compose.yml) (pgvector image pinned by digest: PostgreSQL 17.12, pgvector 0.8.7; Phoenix 21.0.0).

The first run downloads the embedding model `BAAI/bge-small-en-v1.5` (ONNX) and the reranker `BAAI/bge-reranker-base` from Hugging Face into `data/models/` (about 1.2 GB, gitignored). This needs internet access, but no account.

## Environment variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Meaning |
|---|---|
| `LLM_MODEL` | LiteLLM model id of the primary model. Default `groq/openai/gpt-oss-120b`. |
| `LLM_API_KEY` | Groq API key (secret). Needed by the API, `recover_runs.py` and the live evaluation scripts. The unit tests do not need it. |
| `LLM_BASE_URL` | Optional custom endpoint. Empty uses the provider default. |
| `LLM_FALLBACK_MODEL` | Model used when the primary fails or its breaker is open. Default `groq/openai/gpt-oss-20b`. Empty disables the fallback. |
| `LLM_TEMPERATURE` | Default `0`. |
| `DATABASE_URL` | Application database (`careflow`). The end-to-end evaluation also creates `careflow_eval` and `careflow_eval_template` on the same server. |
| `TEST_DATABASE_URL` | pytest database (`careflow_test`). Its schema is recreated during test runs. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Phoenix endpoint, `http://localhost:6006`. |
| `COORDINATOR_TOKEN` | Shared secret for the coordinator console and API (`X-Coordinator-Token` header). Change it from `change-me`. |
| `CAREFLOW_TODAY` | Optional. Overrides the frozen clock (2026-11-02). Leave it unset for the evaluation. |
| `CAREFLOW_PATIENT_ID` | Used only by `scripts/serve_mcp.py`, to bind the stdio MCP server to one patient. |

## Setup and run

```bash
cp .env.example .env                              # then set LLM_API_KEY and COORDINATOR_TOKEN
sudo docker compose up -d                         # PostgreSQL + pgvector on :5432, Phoenix on :6006
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.lock && .venv/bin/pip install -e . --no-deps
.venv/bin/python -m careflow.db.seed              # applies migrations, loads the synthetic patients
.venv/bin/python scripts/ingest_corpus.py         # embeds the corpus (downloads models on first run)
.venv/bin/uvicorn careflow.api.app:app            # API on :8000, OpenAPI docs at /docs
cd frontend && npm ci && npm run dev              # portal and console on :5173
```

Migrations are the SQL files in `src/careflow/db/migrations/` (`001_core` to `005_workflow`). `python -m careflow.db.seed` drops the schema and applies them in order, then loads 5 synthetic patients, their versioned care plans, clinicians and 540 slots. Run `scripts/ingest_corpus.py` again after every seed.

Open http://localhost:5173 in a desktop browser (the layout is desktop only). Patients sign in with a seeded id (`P001` to `P005`, no password). The coordinator console asks for the `COORDINATOR_TOKEN` value.

## Example input and expected output

The clock is frozen at 2026-11-02, so these work as written on a freshly seeded database.

| Patient | Message | Expected |
|---|---|---|
| P001 | `Please book my basic metabolic panel blood test for Tuesday 3 November in the morning.` | A confirmation question naming the test and time. Answer Yes, and the reply starts `Done.`. A morning appointment on 2026-11-03 appears in the coordinator console timeline. |
| P001 | `I have chest pain right now and it is spreading to my left arm.` | The fixed emergency reply, which includes the 112 line. An emergency task appears at the top of the coordinator queue. Nothing is booked. |
| P001 | `I'd like to move my cardiology visit to next Wednesday. Also my ankles are swollen and I've put on 2.5 kg since Sunday.` | An urgent escalation (the plan's rule is a gain of more than 2 kg in a week). The reschedule is not made; the escalation reply says so. |
| P002 | `How often should I use my tiotropium inhaler?` | "Once a day", with a citation to the patient's discharge plan. |

The same flow over HTTP:

```bash
TOKEN=$(curl -s localhost:8000/api/login -H 'content-type: application/json' \
  -d '{"patient_id":"P001"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
CONV=$(curl -s -X POST localhost:8000/api/conversations -H "authorization: Bearer $TOKEN" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["conversation_id"])')
curl -s localhost:8000/api/conversations/$CONV/messages -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"text":"Please book my basic metabolic panel blood test for Tuesday 3 November in the morning."}'
# {"reply": "...", "status": "awaiting_confirmation", "confirmation": "..."}
curl -s localhost:8000/api/conversations/$CONV/confirm -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"approved": true}'
# {"reply": "Done. ...", "status": "done", ...}
```

## Demo walkthrough

1. Sign in as P001 and send the chest-pain message. Show the emergency reply, then the emergency task in the coordinator console.
2. In a new conversation, send the running example (2.5 kg weight gain plus a reschedule). Show the urgent task in the console.
3. Book the metabolic panel (first example), answer Yes, and show the booking in the console timeline and care-plan progress.
4. Sign in as P002 and ask `How often should I use my tiotropium inhaler?`. Show the cited answer.
5. In a new conversation, send `Please book my pulmonology follow-up for Monday 16 November in the afternoon.` and answer Yes. The request is outside the care plan, so it waits for a coordinator. Approve it in the console with a note. Within 10 seconds the patient sees the booking and the note, because the paused run resumed from its checkpoint.
6. Run `.venv/bin/pytest -q tests/test_crash_resume.py` (expected `34 passed`, about 30 s): the workflow is stopped at 34 points and resumes each time without a duplicate action.

Patient sessions are held in memory, so restarting uvicorn signs patients out; a paused run still resumes from its checkpoint, and the patient sees the result after signing in again.

## Tests

```bash
.venv/bin/pytest -q
```

Expected: `553 passed` with Docker PostgreSQL running (about 70 s). Without PostgreSQL, database tests are skipped, not failed: 353 passed, 200 skipped. Do not run two pytest processes at once, because they share `careflow_test`. `docker/initdb.sql` creates `careflow_test` only on a fresh volume; on an older volume run `CREATE DATABASE careflow_test` once.

| Area | Tests |
|---|---|
| Architecture invariants and permissions | `tests/test_architecture.py` (98 tests) |
| Safety gate and red flags | `tests/test_gate.py`, `tests/test_verifier.py` |
| Crash and resume (34 crash points, no duplicate actions) | `tests/test_crash_resume.py` |
| Offline end-to-end scenarios on both systems | `tests/test_eval_systems.py`, `tests/test_api.py::test_coordinator_decision_resumes_the_run` |
| Robustness: busy (423), already handled (409), bad input (422), dead checkpointer connection | `tests/test_api.py` |
| Memory guard and memory | `tests/test_memory_guard.py`, `tests/test_memory_manager.py`, `tests/test_working_memory.py` |
| Retrieval and cited answers | `tests/test_search.py`, `tests/test_careplan.py`, `tests/test_rag_eval.py` |

The milestone-by-milestone acceptance table (criterion, command, expected and observed) is in section 6 of the [report](docs/Project_Report.pdf).

## Evaluation

| Script | Output | Needs LLM key | Result |
|---|---|---|---|
| `scripts/eval_intake.py` | `reports/intake_m1.json` | yes | Emergency recall 1.0 on 30 labelled messages |
| `scripts/eval_memory.py` | `reports/memory_m3.json` | yes | Summary fact survival 0.926 (target 0.9) |
| `scripts/eval_retrieval.py` | `reports/retrieval_m4.json` | no | Recall@5 1.0; MRR 0.964 dense, 0.950 hybrid, 0.976 hybrid + rerank |
| `scripts/eval_careplan.py` | `reports/careplan_m4.json` | yes | 53/53 covered questions answered with citations, 7/7 uncovered handed off |
| `scripts/eval_e2e.py` | `reports/m8/runs.jsonl`, `judgements.jsonl` | yes | 50 scenarios x 2 systems per trial |
| `scripts/eval_report.py` | `reports/m8/summary.json`, `summary.md` | no | Trial 1: CareFlow 49/50, baseline 38/50 |

All of them need the seed and ingest steps first. To recompute the published tables from the committed raw files without any model calls, run `.venv/bin/python scripts/eval_report.py`. It also runs the crash-resume tests, so it needs PostgreSQL.

`eval_e2e.py` resumes from the existing `reports/m8/runs.jsonl`. To run a fresh evaluation, move `runs.jsonl` and `judgements.jsonl` aside first. The committed runs were produced from a working tree based on commit 9ce8e9c, which every row records. Trial 1 used about 376k tokens for the two systems, plus judge calls that were not metered.

## Operations

- **Stop:** Ctrl-C uvicorn and Vite, then `sudo docker compose down` (data is kept).
- **Reset application data:** `.venv/bin/python -m careflow.db.seed && .venv/bin/python scripts/ingest_corpus.py`.
- **Full reset:** `sudo docker compose down -v && sudo docker compose up -d`, then seed and ingest.
- **Resume interrupted runs:** if the API stops during a request, `.venv/bin/python scripts/recover_runs.py` resumes runs that have been idle for 5 minutes.
- **Logs:** the API logs to uvicorn's stdout. Traces are in Phoenix (http://localhost:6006). Per-request model usage, cost and trace ids are in the `audit_events` table: `sudo docker compose exec postgres psql -U careflow -c "select * from audit_events order by id desc limit 20"`. Container logs: `sudo docker compose logs -f postgres phoenix`.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `LLM_MODEL and LLM_API_KEY must be set` | Fill `.env`. |
| Coordinator console says the token is wrong | It must equal `COORDINATOR_TOKEN` in `.env`. Restart uvicorn after changing it. |
| Replies say the service is unavailable, or the evaluation marks cells invalid | The Groq daily quota is used up. Wait and rerun; `eval_e2e.py` resumes. |
| `port 5432 is already allocated` | Stop the local PostgreSQL, or change the compose port and both database URLs. |
| The first request or ingest is slow | The models are downloading to `data/models/`. |
| `UniqueViolation` or deadlocks in tests | Another pytest process is using `careflow_test`. |
| The chat answers 423 | Another request on the same conversation is still running. Wait for it. |

### External services, cost and quota

- **Groq** (https://console.groq.com) provides `LLM_API_KEY`. On the free tier (as of 2026-11-15) each model allows about 200k tokens per day, 8,000 tokens per minute and 1,000 requests per day. One full end-to-end trial needs about 376k tokens plus judge calls, so a three-trial run takes several days or needs a paid key. At list price, a resolved CareFlow scenario costs about USD 0.0006.
- **Hugging Face:** anonymous model downloads.
- **Phoenix and PostgreSQL** run locally and need no account.
- The unit tests use scripted fakes and need neither a key nor internet once the models are cached.

## Limitations

- Only trial 1 of the end-to-end evaluation is complete, and `pass^3` is not reported (Groq free-tier quota).
- The unsupported-answer rate (CareFlow 41%, baseline 22%) comes from an LLM judge that is the same model as the systems, with no saved hand check. The target of zero unsupported answers is not shown.
- Scripted patients only. All results are for one model, five synthetic patients and a corpus written by the team for this project.
- Patient login is a demo login without a password, sessions are held in memory, and the coordinator uses one shared token.
- After an emergency, later messages in the same conversation are often escalated again, which creates duplicate tasks.

The full list is in section 8 of the [report](docs/Project_Report.pdf). Open work is tracked in [GitHub issues](https://github.com/saideepaksana/careflow/issues) #1 to #7.

## Scope

All patients and records are synthetic. CareFlow does not diagnose, prescribe or change doses, and it is a research prototype, not a medical device.
