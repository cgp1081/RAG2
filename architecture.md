# Architecture Outline

> **Reference:** Read together with the product context in [`README.md`](README.md) and full requirements in [`PRD.md`](PRD.md); do not start implementation until all documents agree on scope.

## 1. Purpose & Scope
- Define the end-to-end system that supports document ingestion, structured data syncing, retrieval-augmented chat, and the new telephone support agent.
- Capture dependencies and open decisions so implementation can sequence work safely.
- Guide future implementation by clarifying responsibilities, data flow, and integration points for each component.

## 2. Interaction Channels

### 2.1 Web Portals (Employee & Customer)
- **Function:** Provide chat interfaces and admin tools for employees and customers to query RAG data, manage content, and review analytics.
- **Justification:** Portals already planned in README/PRD; reusing the web stack keeps UX consistent and reduces maintenance overhead.
- **Decisions Pending:** Finalize web framework (React/Next.js vs alternatives) and hosting model before any build.

### 2.2 Telephone Support Agent
- **Function:** Handles inbound/outbound calls, captures speech, orchestrates RAG answers, and delivers responses via neural TTS.
- **Justification:** Addresses phone-support use case with hands-free access, meeting the new success metric (80% AI call resolution).
- **Decisions Pending:** Select telephony provider (e.g., Twilio, Vonage) and speech stack (e.g., Deepgram, AssemblyAI, OpenAI Realtime) prior to implementation.

## 3. Core Services

### 3.1 API Gateway & Orchestration Service
- **Function:** Single entry point for chat, voice, ingestion, and admin APIs; enforces auth, routing, rate limits, and orchestrates retrieval/generation flows.
- **Justification:** Centralized control plane simplifies security and observability while enabling shared business logic.
- **Decisions Pending:** Choose backend framework (FastAPI vs Node/Express/Nest) and hosting (containers vs serverless) before coding.

### 3.2 Retrieval Engine
- **Function:** Manages hybrid document/table retrieval, chunk ranking, and prompt assembly for LLM responses.
- **Justification:** Core capability for grounded answers; aligns with PRD emphasis on high retrieval precision.
- **Decisions Pending:** Confirm retrieval pipeline config (dense-only, hybrid with BM25, rerankers) and library choice (LangChain, LlamaIndex, custom) ahead of build.

### 3.3 LLM Service Layer
- **Function:** Abstracts model providers, handles prompt templating, streaming, fallback logic, and guardrails.
- **Justification:** Decouples business logic from specific model vendors and accommodates on-prem and cloud models.
- **Decisions Pending:** Finalize primary model host (Ollama vs hosted APIs), fallback order, and guardrail tooling (OpenAI policies, Guidance, etc.).

### 3.4 Telephony Pipeline
- **Function:** Connects PSTN/SIP calls to speech-to-text, feeds transcripts to orchestration, receives text responses, and streams TTS back to callers.
- **Justification:** Enables telephone agent while keeping voice processing modular.
- **Decisions Pending:** Select WebRTC vs SIP bridging, pick STT/TTS vendors, determine if media server is in-house or provider-managed.

### 3.5 Ingestion & Connector Workers
- **Function:** Adaptors for document repositories, structured data sources, and scheduling ingest/re-embed jobs.
- **Justification:** Required for building and refreshing the knowledge base across multiple sources.
- **Decisions Pending:** Prioritize connector roadmap, decide on worker tech (Celery, RQ, BullMQ), and define storage for credentials.

### 3.6 Structured Data Service
- **Function:** Catalogs table schemas, enforces SQL guardrails, executes parameterized queries, and links relational data into RAG context.
- **Justification:** Supports tabular answers and hybrid document-table responses highlighted in the PRD.
- **Decisions Pending:** Choose ORM/query layer, confirm supported databases, and finalize policy engine for column/row masking.

### 3.7 Admin & Analytics Service
- **Function:** Aggregates usage metrics, call analytics, transcript search, and compliance reporting accessible via the admin portal.
- **Justification:** Needed for monitoring support effectiveness, especially for telephone transcripts and escalations.
- **Decisions Pending:** Select analytics stack (e.g., ClickHouse, Postgres OLAP, Elastic) and dashboard tooling before build.

## 4. Data & Storage Layers

### 4.1 Vector Store
- **Function:** Stores document/table embeddings and metadata for retrieval queries.
- **Justification:** Qdrant is the preferred store per README/PRD; provides hybrid search support and tenant isolation via namespaces.
- **Decisions Pending:** Confirm final vector DB choice (Qdrant vs Weaviate vs Pinecone) and hosting strategy (managed vs self-hosted) prior to provisioning.

### 4.2 Relational Metadata Store
- **Function:** Persist tenant configs, document metadata, structured table snapshots, prompts, feature flags, and usage logs.
- **Justification:** PostgreSQL aligns with existing assumptions and supports transactional requirements.
- **Decisions Pending:** Validate multi-tenant schema strategy (single DB with schemas vs separate instances) and backup policy.

### 4.3 Object Storage
- **Function:** Retain raw documents, processed chunks, call recordings, and transcription files.
- **Justification:** Durable blob storage is required for audit/compliance and reprocessing.
- **Decisions Pending:** Decide between cloud object stores (S3, GCS) or self-hosted MinIO, and retention rules for call audio.

### 4.4 Observability Stack
- **Function:** Collect logs, metrics, and traces across ingestion, retrieval, telephony, and LLM calls.
- **Justification:** Supports SLA targets (latency, success rates) and debugging complex voice flows.
- **Decisions Pending:** Confirm tooling (Prometheus/Grafana/Loki vs OpenTelemetry SaaS) and data retention windows.

## 5. External Sources & Integrations

### 5.1 Document Repositories
- **Function:** Provide source documents (Google Drive, S3, CRM exports) for ingestion.
- **Justification:** High-value knowledge base inputs; prioritized connectors already listed in PRD.
- **Decisions Pending:** Determine authentication strategy per connector (OAuth vs service accounts) and connector build order.

### 5.2 Structured Data Systems
- **Function:** Supply relational and tabular datasets (Postgres, MySQL, CSV uploads) for SQL-backed Q&A.
- **Justification:** Enables hybrid answers and matches roadmap for structured data support.
- **Decisions Pending:** Define sync frequency, schema change detection, and maximum data volumes per tenant.

### 5.3 Telephony Provider
- **Function:** Terminates phone calls, exposes media streams or webhooks to the telephony pipeline.
- **Justification:** Essential external dependency for telephone support feature.
- **Decisions Pending:** Evaluate provider capabilities (latency, transcription hooks, compliance) before integration.

### 5.4 Speech Providers (STT & TTS)
- **Function:** Convert speech to text and text back to voice during calls.
- **Justification:** Core to voice UX; vendor selection impacts latency and language support.
- **Decisions Pending:** Compare accuracy, latency, pricing, and on-prem availability before implementation.

## 6. Cross-Cutting Concerns

### 6.1 Security & Compliance
- **Function:** Identity, RBAC, audit logging, data retention, and consent capture (especially for recorded calls).
- **Justification:** Protects sensitive information and aligns with compliance requirements.
- **Decisions Pending:** Choose auth provider (native vs SSO), define consent/recording policies, and finalize encryption key management.

### 6.2 Feature Flag & Configuration Management
- **Function:** Enable per-tenant features (e.g., telephone agent) and store prompt templates.
- **Justification:** Needed for gradual rollout and tenant customization.
- **Decisions Pending:** Select flag system (LaunchDarkly, Unleash, homegrown) and config storage strategy.

### 6.3 Testing & Quality Gates
- **Function:** Ensure regression coverage for ingestion, retrieval, and voice flows.
- **Justification:** Voice integrations introduce more failure modes; automated tests mitigate risk.
- **Decisions Pending:** Define test framework (pytest, Playwright, call simulators) and CI/CD pipeline requirements.

## 7. Implementation Guardrails
- Do **not** begin building any components until the pending decisions listed above are explicitly resolved and documented.
- Agents should record chosen vendors, frameworks, and deployment targets in this file (or linked RFC) before implementation tickets are created.
- Any prototype work must be isolated in experimental branches and marked as throwaway until decisions receive product and engineering approval.
- Revisit this architecture outline after decisions are finalized to confirm scope and adjust component responsibilities as needed.
