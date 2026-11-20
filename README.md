# CareFlow

CareFlow is a multi-agent care-coordination assistant for patients in the 30 days after hospital discharge, and for the nurse coordinators responsible for them. It completes routine coordination work on its own: structured intake, follow-up scheduling within care-plan rules, and answers grounded in the patient's own discharge plan. Red flags and out-of-scope clinical questions always go to a human coordinator, through a durable workflow that can pause and resume.

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

**Research question:** can a multi-agent design with deterministic safety gates and a durable human-in-the-loop handoff correctly resolve more routine requests than a single tool-using agent, while keeping missed escalations and unsupported clinical answers at zero?

Course project 2 for CS5903 (Generative AI Systems Engineering, Pillar 1).

## Documentation

- [Proposal (PDF)](docs/proposal.pdf) and [source](docs/proposal.tex): problem statement, architecture, evaluation plan and milestones.
- [Architecture](docs/architecture.md): components, permissions, data model and invariants.

## Repository layout

| Path | Contents | Milestone |
|---|---|---|
| `src/careflow/llm/` | Provider-agnostic LLM gateway, structured output and repair loop, retry, circuit breaker | M1, M7 |
| `src/careflow/db/` | PostgreSQL schema migrations, repository, synthetic seed data, checkpointer | M1, M5 |
| `src/careflow/agents/` | Intake, care-plan answerer, scheduling planner, single-agent baseline | M1, M2, M4, M5 |
| `src/careflow/safety/` | Red-flag gate, deterministic verifier, clinical memory guard | M3, M5 |
| `src/careflow/mcp_servers/` | `records` (read-only), `knowledge` (search), `actions` (write) MCP servers | M6 |
| `src/careflow/memory/` | Working, episodic and semantic memory; consolidation | M3 |
| `src/careflow/knowledge/` | Ingestion, chunking, hybrid retrieval, reranking | M4 |
| `src/careflow/graph/` | LangGraph state, nodes, routing, executor, interrupts | M5 |
| `src/careflow/api/` | FastAPI app: demo login, conversations, confirmation, coordinator actions | M2, M5, M6 |
| `src/careflow/observability/` | OpenTelemetry tracing, request budgets, usage metering | M7, M8 |
| `src/careflow/evaluation/` | Scripted scenarios, systems under test, metrics, judge | M1, M3, M4, M8 |
| `frontend/` | React + TypeScript patient portal and coordinator console | M2, M6 |
| `corpus/` | Shared knowledge documents: condition protocols, operational FAQs | M4 |
| `scripts/` | Seed, ingest and evaluation entry points | — |
| `tests/` | pytest suite, including architecture and permission tests | all |
| `reports/` | Saved evaluation reports | M4, M8 |

## Status

All milestones (M1–M8) are built. Results are in the [final report](docs/report.md).

## Running it

Requires Python 3.14 (the tested version), Node 20.19+ or 22.12+ (Vite 8) and Docker. Copy `.env.example` to `.env`, set `LLM_API_KEY` (Groq) and change `COORDINATOR_TOKEN`.

```bash
sudo docker compose up -d                      # PostgreSQL + pgvector, Phoenix on :6006
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m careflow.db.seed           # schema and synthetic patients
.venv/bin/python scripts/ingest_corpus.py      # embed the document corpus
.venv/bin/uvicorn careflow.api.app:app         # API on :8000
cd frontend && npm install && npm run dev      # patient portal and coordinator console
```

Open http://localhost:5173 in a desktop browser. Patients sign in with a seeded id (`P001` to `P005`, no password). The coordinator console asks for the `COORDINATOR_TOKEN` value from `.env`.

Tests: `.venv/bin/pytest -q`, with Docker running. Database tests are skipped, not failed, when PostgreSQL is unreachable. `docker/initdb.sql` creates `careflow_test` only on a fresh volume; on an older volume run `CREATE DATABASE careflow_test` once.

If the API stops in the middle of a request, `.venv/bin/python scripts/recover_runs.py` resumes runs that have been idle for 5 minutes.

End-to-end evaluation: `.venv/bin/python -u scripts/eval_e2e.py`, then `.venv/bin/python scripts/eval_report.py`. It needs the seed and ingest steps above and a live LLM key, and trial 1 used about 380k tokens for the two systems, plus judge calls that were not metered.

## Scope

All patients and records are synthetic. CareFlow does not diagnose, prescribe or change doses, and it is a research prototype, not a medical device.
