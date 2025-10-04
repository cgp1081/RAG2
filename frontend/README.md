# RAG Assistant Frontend

Minimal Next.js UI for chatting with the RAG backend.

## Getting Started

```bash
npm install
cp .env.example .env.local
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` to the backend origin if it differs from `http://localhost:8000`.

### Quality Gates

- `npm run lint` – Next.js lint rules
- `npm run test` – Jest component tests (network calls mocked with MSW)
- `npm run test:e2e` – Playwright suite (stubs chat/admin endpoints, backend not required)
