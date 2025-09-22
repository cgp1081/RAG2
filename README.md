# RAG Ingest Application

Retrieval-Augmented Generation (RAG) platform for SMBs that need to unlock internal knowledge and deliver grounded AI-assisted experiences. The service ingests documents and structured data, indexes them in a vector store, and powers both employee- and customer-facing conversational interfaces with citation-backed answers.

---

## Required Companion Documents
- **Read this first:** Always review the README together with the detailed specs in [`PRD.md`](PRD.md) and the architecture outline in [`architecture.md`](architecture.md) before planning or implementing changes.
- Use the PRD for product scope, success metrics, and feature requirements; use the architecture document for component responsibilities and pending decisions.
- **Change policy:** Whenever you modify this README, ensure corresponding updates (or explicit confirmations that no change is needed) are applied to both [`PRD.md`](PRD.md) and [`architecture.md`](architecture.md) in the same edit cycle so the documents stay aligned.

---

## Table of Contents
1. [Product Scope](#product-scope)
2. [User Experiences](#user-experiences)
3. [System Architecture](#system-architecture)
4. [Data Ingestion Pipeline](#data-ingestion-pipeline)
5. [Retrieval & Generation Flow](#retrieval--generation-flow)
6. [Admin & Operations](#admin--operations)
7. [Security & Compliance](#security--compliance)
8. [Deployment & DevOps](#deployment--devops)
9. [Roadmap & Enhancements](#roadmap--enhancements)
10. [Open Questions](#open-questions)

---

## Product Scope

- **Audience:** SMBs (law firms, restaurants, accountants, professional services) adopting AI.
- **Value Proposition:** Fast, accurate Q&A over internal knowledge with full source traceability; customer self-service with compliance-friendly guardrails.
- **Stage:** Prototype rebuild intended for self-hosted deployment first, with a SaaS path later.
- **Success Metrics:** <1.5s response time for 90% of queries, >90% grounded retrieval precision, 10k+ docs per tenant, >50% support deflection, <30m onboarding.
- **Structured Data:** Direct ingestion of business tables with SQL-backed Q&A linked to document context.

---

## User Experiences

### Employee Knowledge Portal
- Authenticated chat UI with history and full citation previews.
- Supports prompt customization (tone, system instructions).
- Offers document browsing, tagging, and ingestion status visibility.

### Customer-Facing Agent
- Configurable exposure to approved knowledge subsets.
- Operates in public or authenticated modes.
- Emphasizes sourced, trustworthy responses with lightweight UX.

### Telephone Support Agent
- Inbound and outbound phone agent that connects callers with the RAG knowledge base.
- Uses speech-to-text for transcription, passes the transcript through the existing retrieval and generation flow, and returns answers via neural text-to-speech.
- Supports DTMF or spoken intents to navigate topics, trigger follow-up questions, or escalate to a human operator when confidence is low.
- Stores full call transcripts, audio recordings, and cited sources for compliance review.

---

## System Architecture

- **Core Components:**
  - Web frontend (likely React/Next.js) for admin and chat portals.
  - Backend API (FastAPI/Node) orchestrating ingestion, retrieval, auth, and RAG.
  - Vector database: Qdrant preferred; swappable alternatives (Weaviate, Pinecone).
  - Orchestration layer: LangChain-style agents & tools.
  - Embedding & LLM engines: Ollama local models by default; abstracted provider layer for OpenAI/Claude.
  - Storage: PostgreSQL for metadata/config; object storage for raw uploads.
  - Structured data service: relational schemas cataloguing ingested tables and guarded SQL execution.
  - Voice pipeline integrating telephony provider (e.g., Twilio) with streaming speech-to-text, RAG orchestration, and neural text-to-speech playback.
  - Scheduler: Cron-driven workers for sync, re-ingest, re-embed.

- **Tenancy:** Single-tenant deployment baseline with namespace isolation in data stores; roadmap to multi-tenant.

- **Integration Layer:** Pluggable connectors using OAuth/token flows per employee; service accounts for shared sources; schema-driven table connectors with scheduled refresh.

---

## Data Ingestion Pipeline

1. **Source Connectors**
   - Document repositories: Google Drive, cloud object stores (S3/GCS), CRM exports.
   - Structured feeds: CSV uploads, spreadsheet tabs, relational tables (Postgres/MySQL).
   - Future extension: DOCX, additional SaaS APIs, no-code automations (Zapier, n8n).

2. **Normalization & Chunking**
   - Recursive character text splitter (~300–500 tokens) with sliding window fallback.
   - Extract metadata (source type, author, tags, timestamps).

3. **Table Normalization & Storage**
   - Infer schema metadata, primary keys, and relationships.
   - Snapshot tables into tenant-scoped Postgres schemas with versioning.
   - Emit per-column statistics and summary embeddings for retrieval.

4. **Deduplication & Tagging**
   - Exact hashing (SHA256) plus near-duplicate cosine similarity.
   - Manual or automated tagging aligned with visibility scopes and categories.

5. **Embedding & Indexing**
   - Synchronous embedding on ingest; background re-embedding when models change.
   - Store vectors + metadata in Qdrant; persist raw docs, table summaries, and relational snapshots.

6. **Access Control**
   - Namespace isolation per tenant + role-based filters (`admin`, `employee`, `customer`).
   - Table and column-level filters enforced at query time and exposed to metadata-driven policies.

---

## Retrieval & Generation Flow

1. User submits message (chat or API).
2. Backend applies guardrails (auth checks, rate limits).
3. Intent classifier routes between document/vector retrieval, structured table retrieval, or hybrid mode.
4. Generate embeddings and retrieve top-K chunks; run parameterized SQL on authorized tables when tabular intent detected.
5. Assemble RAG prompt with document context, table summaries/results, and formatting guidelines.
6. Selected LLM (Ollama default) produces grounded response blending narrative and tabular data.
7. Return message with inline citations referencing documents and table sources, plus optional downloadable table payloads.

- **Customization:** System prompt templates per tenant; adjustable tone, allowed tools, fallback models.
- **Observability:** Log retrieval hits/misses, latency, token usage, and citation quality for metrics dashboards.

---

## Admin & Operations

- **Dashboard Features:**
  - Upload workflows (manual drag/drop, bulk sync status).
  - Connector management (OAuth flows, credentials, sync scheduling).
  - Permissions UI for tagging, visibility scopes, role assignments.
  - Deduplication review queue and conflict resolution tools.
  - Usage analytics: query volume, response accuracy, deflection stats.
  - Call analytics dashboard with transcript search, confidence scoring, and manual escalation logs.
  - Table catalog management with schema previews, column visibility, and export controls.
- **Admin API:**
  - `/admin/ingestion-runs` and `/admin/documents` expose paginated ingestion telemetry for operator dashboards.
  - Clients must send `X-Admin-API-Key` matching the `ADMIN_API_KEY` environment variable; missing or mismatched keys receive `401`, and leaving the variable unset disables the routes entirely.

- **CLI Utilities:**
  - `rag ingest <path>` for manual uploads.
  - `rag reembed --model <name>` to trigger re-embedding.
  - `rag sync <connector>` for ad-hoc refresh.
  - `rag table register <source>` to capture schemas and manage refresh schedules.

- **API Endpoints:**
  - REST endpoints for chat, ingest, and metadata management.
  - Table registration, schema refresh, and guarded SQL execution endpoints.
  - Future addition: user provisioning and role management.

---

## Security & Compliance

- Encryption in transit (TLS) and at rest (storage/provider native).
- Secrets management for OAuth tokens and API keys (e.g., Vault, AWS Secrets Manager).
- Role-based access enforcement across UI, API, and data layers.
- Guarded SQL execution layer with column masking and query auditing for structured data.
- Audit logs for ingestion events, queries, config changes with export support.
- GDPR-friendly data export and deletion roadmap.
- Operational monitoring for anomalies and usage patterns.

---

## Deployment & DevOps

- **Packaging:** Docker-first with docker-compose reference; Helm charts in roadmap.
- **Environment Targets:** Self-hosted (on-prem/cloud), later multi-tenant SaaS.
- **Scaling:** Horizontal scaling on workers and API; asynchronous task queue (Celery/RQ/BullMQ).
- **Observability Stack:** Prometheus + Grafana + Loki; alerting on latency/error thresholds.
- **Testing:** Load tests targeting 100+ concurrent sessions, retrieval precision benchmarks, connector integration tests.
- **Configuration:** Set `ADMIN_API_KEY` wherever the backend runs to enable the operator endpoints; use distinct values per environment and rotate via your secrets manager.

---

## Roadmap & Enhancements

- Multi-tenant SaaS controls and billing.
- Redaction & PII scrubbing during ingest.
- External API tool integrations for agent actions (email, CRM updates).
- Actionable agent workflows (form filling, case summaries).
- AP2 protocol support for payments within chat.
- Expanded connector marketplace and no-code automation recipes.

---

## Open Questions

1. Confirm tech stack preferences (Python vs Node for backend, framework choices).
2. Clarify hosting constraints and target deployment environment for prototype.
3. Determine authentication provider (native, SSO, third-party).
4. Decide on default Ollama models and fallback order for cloud providers.
5. Define SLAs for data sync frequency and maximum supported document size.
6. Clarify natural language → SQL translation controls and review workflows.
7. Establish strategy for large table result limits and download/export handling.


---

## Enhancements (Robust RAG Features)

### 🔍 Hybrid Retrieval (Dense + Sparse)
- Combines Qdrant vector search with BM25 keyword retriever for improved recall.
- Useful for numeric identifiers, names, or exact phrases.

### 📈 Feedback-Driven Retrieval Optimization
- Log retrieved chunks, scores, and feedback (thumbs up/down, click behavior).
- Future support for re-ranking or exclusion of stale/poor chunks.

### 🧪 Retrieval Evaluation Harness
- Golden Q&A dataset with known answers and sources.
- Run precision/recall analysis after ingest or model change.

### 🧠 Chunk Embedding Drift & Shadow Testing
- Detect changes in embedding vectors over time (drift detection).
- Shadow mode runs alternate model/prompt/retriever with logging-only output.

### 🔐 Agent Tooling Controls
- Secure allowlist per tenant for which agents/tools can be invoked.
- Future support for CRM/email/form fill agents.

### 📊 Usage Metering & Tenant Controls
- Track usage: token count, docs ingested, queries/day.
- Add configurable limits for multi-tenant SaaS control.

### ✂️ Redaction Layer
- Inference-time redaction to strip PII or sensitive fields from LLM output.

### 🧰 Prompt Registry
- Versioned, per-tenant prompt templates with overrides via API/CLI.

### 🧱 Row-Level Table Security
- Apply row filters per user or tenant ID during table Q&A.

### 🧭 UX Additions
- “Explain this answer” tooltips with chunk metadata and source strength.
- Multi-turn chat memory and follow-up query linking.

## 18. Optimization Plan for Configurability & Feature Growth


To ensure this platform remains easy to configure, maintain, and extend with tenant-specific features, the following design patterns and enhancements are recommended:

### 18.1 Plugin-Based Connector Architecture
- All document and structured data ingestion connectors follow a shared interface and live in modular directories (e.g., `/connectors/gdrive/`, `/connectors/s3/`).
- Enables addition of new sources without editing core codebase.
- Plugin manifest includes:
  - `auth_type`, `source_type`, `sync_style`, `supported_formats`

### 18.2 Per-Tenant Configuration
- Each tenant has its own YAML or DB-stored config defining:
```yaml
llm:
  provider: ollama
  model: mistral
  fallback: [openai:gpt-3.5, anthropic:claude-3-haiku]
retrieval:
  top_k: 5
  hybrid: true
prompts:
  system: "You are a helpful assistant..."
features:
  pii_redaction: true
  agent_actions: false
```
- Loaded dynamically for ingestion, query, and chat rendering.

### 18.3 Feature Flag Framework
- Feature toggles set per tenant to enable/disable capabilities.
- Backed by DB or Unleash server.
- Exposed in dashboard + API.

### 18.4 Admin UI Schema Editor
- During table ingestion, admins can override inferred schema:
  - Column types, PKs, FKs
  - Visibility per column
- Stores as versioned schema overrides

### 18.5 Prompt Registry & GUI Editor
- Per-tenant prompt templates stored in DB
- Web editor in admin panel with:
  - Tone presets (formal, helpful, fun)
  - Format modes (bullets, paragraphs, JSON)
  - Live preview and test mode

### 18.6 CLI Bootstrap for New Tenants
- One-line CLI to create all config and isolation primitives:
```bash
rag bootstrap-tenant --name acme --llm mistral --connectors gdrive,s3
```

### 18.7 Helm Charts for Deployment
- Helm templates for container orchestration and config.
- Secrets injection, persistent volumes, scaling groups.

### 18.8 Structured Event Bus
- Event-driven ingestion, logging, agent execution.
- Supports webhook listeners, tenant hooks, and internal workflows.

### 18.9 App Store for Agents
- Agents defined via JSON manifest per tenant.
- Controlled via admin panel UI and API.
- Logged executions and audit trail.

### 18.10 Composable Retrieval Pipelines
- Declarative YAML-based retrieval logic per tenant:
```yaml
retrieval_pipeline:
  - filter: visibility_scope=public
  - scorer: bm25
  - scorer: vector_similarity
  - rerank: feedback_boost
```

### 18.11 Unified Trace Logging & Debugging
- Assign `trace_id` to all lifecycle stages
- Expose trace logs in admin panel
- Metrics dashboard powered by Prometheus, Loki

---
