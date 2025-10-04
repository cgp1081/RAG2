/* Centralised API helpers for talking to the backend chat/admin endpoints.
 * Requests run through a small timeout helper using AbortController so the UI can
 * provide responsive feedback even when the backend is unavailable.
 */

export type ChatMetadataFilters = {
  source_type?: string[] | null;
  tags?: string[] | null;
  visibility_scope?: string | null;
};

export type ChatRequestPayload = {
  query: string;
  tenant_id?: string;
  filters?: ChatMetadataFilters | null;
};

export type Citation = {
  document_id: string;
  chunk_id: string;
  score: number;
  normalized_score: number;
  source_type?: string | null;
  title?: string | null;
  snippet: string;
};

export type TokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type ChatResponse = {
  answer: string;
  citations: Citation[];
  token_usage: TokenUsage;
  model: string;
  prompt_id: string;
  latency_ms: number;
};

export type DocumentSummary = {
  id: string;
  title?: string | null;
  status?: string | null;
  metadata_json?: Record<string, unknown>;
};

export type PaginatedDocumentsResponse = {
  items: DocumentSummary[];
  total: number;
  page: number;
  page_size: number;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

const DEFAULT_TIMEOUT_MS = 15000;

export function getApiBaseUrl(): string {
  // Shared base URL so CLI/dev/test runs can route through Next's rewrite when needed.
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function fetchWithTimeout<T>(input: RequestInfo | URL, init?: RequestInit, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(input, { ...init, signal: controller.signal });
    if (!response.ok) {
      const detail = await safeParseError(response);
      throw new ApiError(detail || `Request failed with status ${response.status}`, response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Request timed out", 408);
    }
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError((error as Error)?.message ?? "Unknown error", 500);
  } finally {
    clearTimeout(timeout);
  }
}

async function safeParseError(response: Response): Promise<string | null> {
  try {
    const payload = await response.json();
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    return JSON.stringify(payload);
  } catch (error) {
    try {
      return await response.text();
    } catch {
      return null;
    }
  }
}

export async function postChatQuery(payload: ChatRequestPayload, timeoutMs?: number): Promise<ChatResponse> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/chat/query`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };
  const chatKey = process.env.NEXT_PUBLIC_CHAT_API_KEY;
  if (chatKey) {
    headers["X-Chat-API-Key"] = chatKey;
  }
  return fetchWithTimeout<ChatResponse>(
    url,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload)
    },
    timeoutMs ?? DEFAULT_TIMEOUT_MS
  );
}

export async function fetchDocuments(tenantId: string, timeoutMs?: number): Promise<PaginatedDocumentsResponse> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/admin/documents?tenant=${encodeURIComponent(tenantId)}&page=1&page_size=5`;
  return fetchWithTimeout<PaginatedDocumentsResponse>(url, { method: "GET" }, timeoutMs ?? DEFAULT_TIMEOUT_MS);
}
