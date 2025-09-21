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

## Next Immediate Steps
- Kick off Phase P0 Task P0-S1 using its handoff brief.
- Track progress and surface any new assumptions or risks here to avoid repeated discovery.
