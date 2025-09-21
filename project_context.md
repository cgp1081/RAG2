# Project Context Snapshot

## Purpose & Scope
- Build a modular, self-hosted Retrieval-Augmented Generation (RAG) platform serving SMB use cases: employee knowledge portal, customer bot, and telephone support agent.
- MVP must deliver grounded chat with citations, ingestion of local documents, readiness for structured data Q&A, and foundations for observability and telephony per README/PRD/architecture docs.

## Source Documents
- `README.md`: High-level product scope, user journeys, architecture overview, roadmap themes.
- `PRD.md`: Detailed feature requirements, success metrics (e.g., <1.5s latency, >90% grounded precision, 80% call resolution), connector list, telephony expectations.
- `architecture.md`: Component responsibilities, pending decisions (backend framework, telephony provider, observability stack), implementation guardrails.

## Planning Assets
- `projectmanager.md`: System prompt for Project Manager agent. Ensures deterministic planning, modular phases, test-driven tasks.
- `project_sequence.txt`: End-to-end execution plan produced 2024-?? (fill date when known). Contains:
  - Global roadmap (Phases P0–P7) from foundations through telephony analytics.
  - Dependency map spelling prerequisite relationships.
  - Risk & Unknowns log (framework choice, embedding host, vector DB hosting, SQL guard scope, telephony vendor, structured data scale, eval dataset ownership).
  - Handoff briefs for 14 tasks (P0-S1 … P7-S2) formatted for prompt handoff.
  - Machine-readable JSON tasks array aligning with briefs for automation.

## How to Use the Plan
1. Start at earliest pending task respecting dependencies (P0-S1 first).
2. Copy the entire Handoff Brief section (Task ID through Notes) into the Prompt Engineering Lead agent’s system or user prompt when requesting implementation.
3. Require the engineer to deliver the acceptance tests listed; briefs embed the testing contract.
4. After completion, validate via specified commands/tests (e.g., `pytest`, `rag ingest-files`, `rag eval`). Document results.
5. Update risk log or assumptions in `project_sequence.txt` if decisions change.
6. Move to the next task only after dependent acceptance criteria pass.

## Testing Expectations
- Every task’s acceptance tests define minimum coverage (unit, integration, CLI smoke). Treat them as mandatory.
- Non-functional bullets (latency, determinism, logging) are guardrails to verify during QA.
- Observability and evaluation tasks (P6-S1, P6-S2) add additional validation tools; run them before telephony work.

## Outstanding Decisions / Watchlist
- Confirm backend stack (FastAPI assumed) and note any deviation in architecture.md.
- Finalize embedding/LLM providers and vector DB hosting (Ollama + self-hosted Qdrant currently assumed).
- Decide SQL guard policies, telephony/STT/TTS vendors, CSV size limits, and golden dataset source before corresponding tasks.
- Record all approvals/changes in this context file to keep future planning consistent.

## Files Created So Far
- `projectmanager.md`: Project Manager agent system prompt text.
- `project_sequence.txt`: Sequenced plan, risks, briefs, JSON.
- `project_context.md`: (this file) running summary for future collaborators.
- `backend/` (P0-S1): FastAPI scaffold with structured logging, `/healthz`, configuration helpers, Dockerfile, docker-compose wiring, CI workflow, pytest + httpx tests.
- `backend/db/` (P1-S1): SQLAlchemy declarative base, ORM models (tenant/source/document/chunk/ingestion run/event), session factory, Alembic environment and initial migration (`0001_initial`).
- `backend/tests/test_migrations.py`, `backend/tests/test_models_relationships.py`: Regression coverage for Alembic upgrade and ORM relationships.
- `alembic.ini`: Root Alembic configuration with `path_separator = os` to avoid prepend warning.

## Next Immediate Steps
- Reference `project_sequence.txt` to select the next unblocked task (likely remaining Phase 1 decision work or Phase 2 foundations).
- Keep this context updated with any new architectural decisions, schema changes, or deviations encountered during upcoming tasks.

## Progress Log

### 2025-09-20 — P0-S1: Backend Scaffold
- Implemented FastAPI app factory (`backend/app/main.py`) with request ID middleware and structured logging via `structlog`.
- Added `pydantic-settings`-based configuration (`backend/app/config.py`), including cached dependency injection and `.env` loading.
- Authored health router and tests (`backend/app/routers/__init__.py`, `backend/tests/test_health.py`, `backend/tests/test_logging_request_id.py`).
- Created developer tooling: `pyproject.toml`, `.env.example`, `docker-compose.yml`, `backend/Dockerfile`, CI workflow (`.github/workflows/ci.yml`).
- Verified with `python3 -m ruff check backend`, `python3 -m pytest backend/tests`, and `docker compose up --build` (API served `/healthz`).

### 2025-09-21 — P1-S1: Persistence & Migrations
- Extended settings with `database_url`/`db_pool_size`; standardized DSNs on `postgresql+psycopg`.
- Added SQLAlchemy base, models (`backend/db/models.py`), session factory (`backend/db/session.py`), and package exports.
- Scaffolded Alembic (`alembic.ini`, `backend/db/migrations/env.py`, `backend/db/migrations/versions/0001_initial.py`) creating tenants/sources/documents/document_chunks/ingestion_runs/ingestion_events tables.
- Introduced Postgres-backed tests validating migrations and ORM relationships with Alembic upgrade fixtures.
- Updated project tooling and compose env vars to expose `DATABASE_URL` / `DB_POOL_SIZE`.
- Applied migration to local Postgres via `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres python3 -m alembic upgrade head`.
- Lint/tests executed: `python3 -m ruff check backend`, `python3 -m pytest backend/tests`.

## Deviations & Notes
- Test fixtures reuse the configured Postgres instance instead of creating per-test databases (original brief suggested ephemeral DBs). Document this if multi-tenant isolation becomes critical.
- `documents.metadata` column stored under attribute `metadata_json` to avoid SQLAlchemy reserved-name conflict; accessor convenience not yet added.
- Alembic CLI not on PATH; use `python3 -m alembic …` or install scripts locally.
- PostgreSQL password resets may be required for local testing (`docker compose exec postgres psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'postgres';"`).
- Remember to enable `pgcrypto` (or equivalent) if deploying to a new database so `gen_random_uuid()` works (see migration note).
