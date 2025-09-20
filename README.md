# RAG Ingest Application

Retrieval-Augmented Generation (RAG) platform for SMBs that need to unlock internal knowledge and deliver grounded AI-assisted experiences. The service ingests documents and structured data, indexes them in a vector store, and powers both employee- and customer-facing conversational interfaces with citation-backed answers.

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

---

## System Architecture

- **Core Components:**
  - Web frontend (likely React/Next.js) for admin and chat portals.
  - Backend API (FastAPI/Node) orchestrating ingestion, retrieval, auth, and RAG.
  - Vector database: Qdrant preferred; swappable alternatives (Weaviate, Pinecone).
  - Orchestration layer: LangChain-style agents & tools.
  - Embedding & LLM engines: Ollama local models by default; abstracted provider layer for OpenAI/Claude.
  - Storage: PostgreSQL for metadata/config; object storage for raw uploads.
  - Scheduler: Cron-driven workers for sync, re-ingest, re-embed.

- **Tenancy:** Single-tenant deployment baseline with namespace isolation in data stores; roadmap to multi-tenant.

- **Integration Layer:** Pluggable connectors using OAuth/token flows per employee; service accounts for shared sources.

---

## Data Ingestion Pipeline

1. **Source Connectors**
   - Early support: Google Drive, SQL (Postgres/MySQL), cloud object stores (S3/GCS).
   - Future extension: CRM exports, DOCX, PDFs, no-code automations (Zapier, n8n).

2. **Normalization & Chunking**
   - Recursive character text splitter (~300–500 tokens) with sliding window fallback.
   - Extract metadata (source type, author, tags, timestamps).

3. **Deduplication & Tagging**
   - Exact hashing (SHA256) plus near-duplicate cosine similarity.
   - Manual or automated tagging aligned with visibility scopes and categories.

4. **Embedding & Storage**
   - Synchronous embedding on ingest; background re-embedding when models change.
   - Store vectors + metadata in Qdrant; persist raw docs + derived artifacts.

5. **Access Control**
   - Namespace isolation per tenant + role-based filters (`admin`, `employee`, `customer`).
   - Query-time metadata filtering for tags, scopes, authorship.

---

## Retrieval & Generation Flow

1. User submits message (chat or API).
2. Backend applies guardrails (auth checks, rate limits).
3. Query embedding generated via configured model.
4. Top-K retrieval with metadata filters applied.
5. RAG prompt assembled with context windows, instructions, and formatting guidelines.
6. Selected LLM (Ollama default) produces grounded response.
7. Return message with inline citations referencing source metadata.

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

- **CLI Utilities:**
  - `rag ingest <path>` for manual uploads.
  - `rag reembed --model <name>` to trigger re-embedding.
  - `rag sync <connector>` for ad-hoc refresh.

- **API Endpoints:**
  - REST endpoints for chat, ingest, and metadata management.
  - Future addition: user provisioning and role management.

---

## Security & Compliance

- Encryption in transit (TLS) and at rest (storage/provider native).
- Secrets management for OAuth tokens and API keys (e.g., Vault, AWS Secrets Manager).
- Role-based access enforcement across UI, API, and data layers.
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

