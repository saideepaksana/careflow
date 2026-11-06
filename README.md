# CareFlow

CareFlow is a multi-agent care-coordination assistant for patients in the 30 days after hospital discharge, and for the nurse coordinators responsible for them. It completes routine coordination work on its own: structured intake, follow-up scheduling within care-plan rules, and answers grounded in the patient's own discharge plan. Red flags and out-of-scope clinical questions always go to a human coordinator, through a durable workflow that can pause and resume.

```text
patient message -> intake (LLM, no tools) -> safety gate (code) -> supervisor
    -> care-plan agent (hybrid RAG, cited)      -> finalize
    -> scheduling planner -> verifier -> confirm -> executor (only writer) -> finalize
    -> coordinator handoff (interrupt, resumes on the nurse's decision)     -> finalize
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
| `src/careflow/db/` | PostgreSQL schema migrations, repository, synthetic seed data | M1 |
| `src/careflow/agents/` | Intake, care-plan, scheduling planner, memory manager, single-agent baseline | M1, M2, M6 |
| `src/careflow/safety/` | Red-flag gate, scope guard, deterministic verifier | M2, M8 |
| `src/careflow/mcp_servers/` | `records` (read-only), `knowledge` (search), `actions` (write) MCP servers | M2, M6 |
| `src/careflow/memory/` | Working, episodic and semantic memory; consolidation | M3 |
| `src/careflow/knowledge/` | Ingestion, chunking, hybrid retrieval, reranking, citation check | M3, M4 |
| `src/careflow/graph/` | LangGraph state, nodes, routing, checkpointer, interrupts | M5, M6 |
| `src/careflow/api/` | FastAPI app: auth and roles, conversations, SSE events, coordinator actions | M2, M6 |
| `src/careflow/observability/` | OpenTelemetry tracing, token and cost accounting | M7 |
| `src/careflow/evaluation/` | Scenarios, simulated patients, runner, metrics, judge | M4, M8 |
| `frontend/` | React + TypeScript patient portal and coordinator console | M2, M6 |
| `corpus/` | Shared knowledge documents: condition protocols, operational FAQs | M4 |
| `scripts/` | Seed, ingest and evaluation entry points | — |
| `tests/` | pytest suite, including architecture and permission tests | all |
| `reports/` | Saved evaluation reports | M4, M8 |

## Status

Proposal stage. The project structure is in place, and implementation starts with Milestone 1.

## Scope

All patients and records are synthetic. CareFlow does not diagnose, prescribe or change doses, and it is a research prototype, not a medical device.
