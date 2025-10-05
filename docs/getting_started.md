# Getting Started with the RAG Platform

This guide walks a self-hosting operator through bootstrapping the modular Retrieval-Augmented Generation (RAG) platform, ingesting content, validating retrieval quality, and chatting with the system. The stack includes a FastAPI backend, Typer-based ingestion/evaluation CLIs, a Next.js chat UI, and optional telephony endpoints.

## 1. Prerequisites

1. Verify tooling is installed:
   - Docker Desktop or compatible container runtime (with `docker compose` v2+)
   - Python 3.11+
   - Poetry 1.6+ (for backend dependency management)
   - Node.js 18+ (ships with npm)
   - Ollama 0.1.30+ (for local embedding/LLM serving) **or** credentials for a remote model provider compatible with the configured endpoints
   ```bash
   docker compose version
   poetry --version
   node --version
   npm --version
   ```
   Ensure the Docker daemon is running and that your user has permission to access the socket before continuing.
   > Tip: If any command above is missing, install the prerequisite (e.g., `pipx install poetry`, Docker Desktop) before moving on. Network access to PyPI and container registries is required for dependency installation and image pulls.
2. Set environment variables. Copy the provided sample and adjust as needed:
   ```bash
   cp .env.example .env
   ```
3. Install Python dependencies via Poetry:
   ```bash
   poetry install
   ```
4. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   cd ..
   ```
5. Review required configuration values (defaults provided in `.env.example`):

| Variable | Purpose | Example |
| --- | --- | --- |
| `POSTGRES_URL` / `DATABASE_URL` | Primary Postgres connection | `postgresql+psycopg://postgres:postgres@postgres:5432/postgres` |
| `QDRANT_URL` | Vector store endpoint | `http://qdrant:6333` |
| `OLLAMA_BASE_URL` / `LLM_BASE_URL` | Embedding + completion endpoint | `http://localhost:11434` when running Ollama locally |
| `ADMIN_API_KEY` | Required for `/admin/*` endpoints | `changeme` |
| `CHAT_API_KEY` | Required for chat API/UI | `changeme-chat` |
| `VOICE_*` | Optional telephony credentials (Twilio, STT/TTS) | leave blank unless enabling voice |
| `CALL_STORAGE_*` | Optional S3/MinIO storage for recordings | configure when storing voice call artifacts |

> Optional: set `CALL_STORAGE_BUCKET` and related values only when provisioning S3/MinIO for call recordings. Leave empty for local development.

If you plan to run embeddings/LLM locally, install and start Ollama before bootstrapping the stack (examples shown for macOS/Homebrew):

```bash
brew install ollama
ollama serve
# Pull the default models used by the project
ollama pull nomic-embed-text
ollama pull mistral
```

When using a remote provider, update `.env` with the appropriate base URLs, model names, and API keys.

## 2. Bootstrap the Stack

1. Build and launch the backend services from the repository root:
   ```bash
   docker compose up --build postgres qdrant api
   ```
   This launches Postgres, Qdrant, and the FastAPI backend (hot reload enabled). Leave this terminal running.
2. In a new terminal, run database migrations inside the API container:
   ```bash
   docker compose exec api python -m alembic upgrade head
   ```
   Alternatively, if you are running the backend locally via Poetry (see below), use `poetry run alembic upgrade head`.
3. (Optional) If you prefer to run the backend outside Docker for development, activate the Poetry environment and start Uvicorn:
   ```bash
   poetry shell
   poetry run uvicorn backend.app.main:app --reload
   ```
   Ensure Postgres and Qdrant are still running via Docker Compose (steps above) or provisioned separately.

## 3. Ingest Documents

1. Prepare sample files under `data/sample_docs/` (create the directory if needed):
   ```bash
   mkdir -p data/sample_docs
   ```
2. Ingest documents for the default tenant:
   ```bash
   poetry run rag ingest-files --path data/sample_docs --tenant default
   ```
   - Successful runs log processed document counts.
   - Check ingestion status via `poetry run rag ingest-files --help` for options, or query the API:
     ```bash
     curl -H "X-Admin-API-Key: $ADMIN_API_KEY" http://localhost:8000/admin/ingestion-runs
     ```
3. Ingest structured data (optional) when CSVs are available:
   ```bash
   poetry run rag ingest-table --csv data/tables/sample.csv --table-name sample_table --tenant default
   ```
   Ensure the CSV header accurately reflects column names; large tables may require tuning `STRUCTURED_MAX_ROWS`.

## 4. Run the Retrieval Evaluation Harness

1. Execute the bundled dataset to verify retrieval quality:
   ```bash
   poetry run rag eval --dataset backend/eval/datasets/example.yaml --tenant default
   ```
2. Reports are written to `reports/last_eval.json` and timestamped copies under `reports/eval-*.json`.

## 5. Launch the Chat Interface

1. Ensure the backend is running (either via Docker Compose or `poetry run uvicorn backend.app.main:app --reload`).
2. Start the frontend from `frontend/`:
   ```bash
   npm run dev
   ```
   The default UI listens on `http://localhost:3000` and proxies API calls to `http://localhost:8000`.
3. Set the chat API key in the browser (UI prompts or configure `.env.local`):
   - Requests must include `X-Chat-API-Key: $CHAT_API_KEY`.
4. Submit a query in the chat UI:
   - Successful answers include citation badges referencing ingested documents.
   - “I don’t know” indicates no high-confidence context was found; verify ingestion status or adjust content.
5. Troubleshooting tips:
   - CORS errors usually stem from mismatched `NEXT_PUBLIC_API_BASE_URL`; align frontend `.env.local` with backend origin.
   - Check `/admin/ingestion-runs` and `/admin/documents` for ingestion progress if responses lack citations.
   - Connection errors to Ollama indicate the embedding/LLM service is not running or the `.env` URLs are incorrect.

## 6. Telephony (Optional)

Voice features require Twilio credentials and optional S3 storage for recordings. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, STT/TTS API keys, and expose a webhook (e.g., via ngrok) before enabling `/voice` endpoints. See telephony documentation for detailed setup.

## 7. Next Steps & Production Considerations

1. Monitor health and performance:
   - `/metrics` exposes Prometheus counters and histograms (ingestion, RAG latency, voice call durations).
   - Consider standing up Grafana/Loki for dashboards and logs.
2. Manage feature rollout:
   - Leverage environment flags (`RETRIEVAL_DIAGNOSTICS`, future feature toggles) to control behavior per tenant/environment.
3. Establish evaluation cadence:
   - Schedule regular `rag eval` runs against curated datasets.
   - Run `poetry run rag voice-call-summary` nightly (or via cron) when voice analytics are enabled.
4. Export call transcripts for audit:
   ```bash
   poetry run rag export-calls --from 2024-01-01 --to 2024-01-31 --tenant <tenant-uuid>
   ```
   Outputs CSV to `reports/calls.csv` by default.

By completing these steps, operators can ingest data, validate retrieval quality, and interact with the chat (and optionally voice) experiences in the RAG platform.
