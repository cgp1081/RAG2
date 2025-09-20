# Product Requirements Document (PRD): RAG Ingest Application

---

## 1. Overview

The RAG Ingest Application is a SaaS-style service designed for small to medium-sized businesses (SMBs) that want to integrate AI into their operations. Target users include law firms, restaurants, accountants, and other professional service providers.

The product enables ingestion of internal business data — including PDFs, structured databases, CRM platforms, and other common business tools — to power two main conversational AI experiences:
- An **employee-facing chat interface** for internal knowledge access
- A **customer-facing AI agent** that provides accurate, grounded responses with document citations

Both agents rely on Retrieval-Augmented Generation (RAG) using a customizable, business-specific knowledge base. The platform ensures users receive sourced, accurate responses from the documents or records they’ve ingested.

**Key characteristics:**
- Prototype stage: Rebuild from scratch based on a previous version
- Initial deployment: Self-hosted; cloud SaaS model planned later
- Customization: Full configuration support with a generic default experience
- Industry use: General-purpose, with law firms as a sample use case
- Monetization: Likely flat-fee pricing with tiered support plans

---

## 2. Goals & Success Criteria

### Primary Goals

1. **Instant Access to Internal Knowledge**  
   Natural language Q&A over internal documents with accurate, sourced answers

2. **Scalability with Large Data Volumes**  
   Handle thousands of documents and millions of tokens

3. **Customer Experience Automation**  
   Reduce human support load by providing useful, intuitive AI help to customers

### Success Metrics

- ⏱️ Response time under 1.5s for 90% of queries
- 📄 Scale tested up to 10,000+ documents per tenant
- ✅ Retrieval grounding precision >90%
- 👥 >50% support deflection by AI
- 🛠️ Onboarding time <30 minutes
- 🔁 High retention over 3 months

---

## 3. Core Features & Functional Requirements

### Retrieval-Augmented Chat Interfaces
- Internal chat with citations
- External customer bot with configurable access
- Structured data Q&A returning tabular answers linked to document context

### Ingestion & Connectors
- PDF, DOCX, SQL DBs, CRM exports, cloud storage (S3, GCS)
- Modular connector framework

### Agent & LLM Architecture
- Built using agents + LangChain-style orchestration
- Tools and reasoning flows fully supported

### Admin Dashboard
- Ingest control
- Permission/tagging management
- Document exposure settings

---

## 4. Data Sources & Connectors

### Initial Source Types
- Google Drive
- SQL Databases (Postgres, MySQL)
- Cloud Storage (S3, GCS)
- Tabular sources (CSV uploads, spreadsheets, database tables)

### Integration Model
- Per-user connections for employees (OAuth, tokens)
- Public or authenticated access tiers for customers
- Structured sources maintain tenant-specific schema catalogs with scheduled refresh jobs

---

## 5. Vector Store & Metadata Strategy

### Chosen Vector DB
- **Qdrant** (preferred)
- Alternatives: Weaviate, Pinecone

### Metadata Strategy
- `source_type`, `tag`, `author`, `visibility_scope`, `created_at`
- Rich filtering and ranking supported
- Table linkage metadata (`table_id`, `column_id`) to bridge structured answers and documents

### Access Control
- Namespace-based separation
- Role-linked filtering in query layer
- Table- and column-level guards derived from RBAC settings

---

## 6. LLM(s) & RAG Query Flow

### LLM Strategy
- Default: **Ollama local models**
- Optional: Cloud models via OpenAI, Claude, etc.

### Query Flow
1. User submits query
2. Intent classifier selects document/vector retrieval, structured table retrieval, or hybrid
3. Embed + retrieve top-K chunks and/or run parameterized SQL over authorized tables
4. RAG prompt constructed with tabular summaries and document context
5. LLM generates grounded answer with optional table payloads
6. Sources (documents and tables) are cited inline

### Prompt Config
- Customers can customize system prompt, tone, and behavior
- System Prompt Template Example:
  ```
  You are a helpful business assistant. Always answer using only the provided context. If you don’t know the answer, say “I don’t know.”

  Format:
  - Answer concisely
  - Cite sources as [Doc Title](URL) after each fact

  Context:
  {{retrieved_chunks}}

  User Question:
  {{user_input}}
  ```

### LLM Provider Routing & Fallback
```yaml
llm_config:
  provider: "ollama"
  model: "mistral"
  fallback_providers:
    - openai:gpt-3.5
    - anthropic:claude-3-haiku
```

---

## 7. Ingestion Workflow

### Chunking
- Recursive Character Text Splitter (~300–500 tokens)
- Sliding Window fallback

### Embeddings
- Generated on ingest
- Re-embed when model version changes

### Deduplication
- Exact (SHA256)
- Near-duplicate (cosine similarity)

### Tagging
- Configurable (auto or manual)
- Categorized by visibility, type, origin

### Table Normalization & Storage
- Detect structured datasets (CSV uploads, spreadsheet tabs, relational tables)
- Capture schema metadata, primary keys, and relationships
- Persist per-tenant table snapshots in relational storage (Postgres)
- Generate column statistics and summary embeddings for retrieval
- Link table and column records to vector entries for hybrid doc/table responses

---

## 8. UI / UX

### Admin Dashboard
- Uploads, tagging, deduplication
- Permissions & exposure settings
- Table catalog with schema previews, access controls, and exports
- Logs and usage stats

### User Chat Portals
- **Employee Portal**:
  - Full access + history + source previews
  - Chat response streaming enabled
- **Customer Portal**:
  - Public access to approved content
  - Authenticated access to personal data

### Chat UX Features
- Streaming responses
- Clickable citations
- Thumbs up/down feedback
- Full query history with timestamps
- Optional filters, search, and starred chats
- Render tabular answers with download/export options when queries target structured data

---

## 9. Security, Privacy & Access Controls

### Tenancy
- Single-tenant to start
- Multi-tenant roadmap with Qdrant namespaces and DB tenant_id isolation

### Roles
- Admin, Employee, Customer
- Optional column-level permissions for sensitive structured data

### Authentication
- Email/password login with JWTs for prototype
- Future: OAuth or SSO options

### Security
- Encryption at rest + transit
- OAuth secrets stored securely
- Guarded SQL execution layer with column masking for sensitive fields

### Audit Logs
- Track ingestion, queries, access, and config changes
- GDPR data export support (future)

---

## 10. Integration Points

### API
- REST API for chat and ingest
- Structured data endpoints for registering tables, refreshing schemas, and executing guarded queries
- User management endpoints (future)

### CLI
- Upload
- Re-ingest
- Re-embed
- Register table schemas and trigger refresh jobs

### Scheduler
- Cron for drive/db sync
- Re-ingest polling

### No-Code Tools
- Zapier
- n8n

---

## 11. Non-Functional Requirements

### Performance
- Target response: <1.5s first token, <3s full answer
- Fast retrieval under 300ms

### Scalability
- 10k+ docs
- 100+ concurrent sessions

### Deployment
- Docker-first
- Cloud/on-prem friendly

### Observability
- Prometheus, Grafana, Loki (open source)
- Logs for ingestion, errors, usage
- Monitor:
  - Query latency
  - Retrieval hit/miss ratio
  - Embedding model drift
  - Chunk count per doc
  - Ingestion failures

### Performance Testing
- Use Locust or k6 for concurrent chat testing
- Use pytest for ingestion and embedding benchmarks

---

## 12. Known Risks & Assumptions

### Risks
- Unvalidated scale
- Industry-specific user expectations
- Security concerns from potential customers
- Solo maintenance risk
- SQL guardrails must prevent over-broad queries or leakage
- Schema drift between source systems and stored snapshots

### Assumptions
- Self-hosting is acceptable
- Open-source stack remains stable
- RAG > generative-only LLM
- Chat UX is accepted for business ops
- Natural language table querying remains accurate with user feedback loops

---

## 13. Future Enhancements

- **Redaction & PII removal**
- **External API Lookups**
- **Actionable Agents** (email, form-filling)
- **AP2 protocol** support for chat-based payments
- **SaaS Billing Roadmap**
  - Stripe or Paddle integration
  - Usage metering
  - Tenant-specific limits

---

## 14. Appendices

### A. Architecture Diagram
*Placeholder*

### B. Prompt Templates
See Section 6 for default system prompt

### C. Data Schemas

```json
{
  "Chunk": {
    "id": "uuid",
    "text": "string",
    "embedding": "[float]",
    "document_id": "uuid",
    "tags": ["invoice", "confidential"],
    "visibility": "employee | public | private",
    "source_type": "gdrive | sql | s3",
    "created_at": "timestamp"
  }
}
```

### D. LLM Compatibility Matrix
*Placeholder*
