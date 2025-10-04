import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import CitationList from "./CitationList";
import {
  type ChatRequestPayload,
  type ChatResponse,
  type Citation,
  type PaginatedDocumentsResponse,
  fetchDocuments,
  getApiBaseUrl,
  postChatQuery
} from "../lib/api";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  latencyMs?: number;
};

export type ChatPanelProps = {
  tenantId: string;
};

const documentsFetcher = async (tenantId: string): Promise<PaginatedDocumentsResponse> => {
  return fetchDocuments(tenantId);
};

function createMessage(role: "user" | "assistant", text: string, citations?: Citation[], latencyMs?: number): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    role,
    text,
    citations,
    latencyMs
  };
}

const ChatPanel: React.FC<ChatPanelProps> = ({ tenantId }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  const { data: documents } = useSWR(tenantId ? ["documents", tenantId] : null, () => documentsFetcher(tenantId));

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const ingestionSummary = useMemo(() => {
    if (!documents?.items?.length) {
      return [] as string[];
    }
    return documents.items
      .slice(0, 3)
      .map((item) => item.title || item.metadata_json?.preview || item.id)
      .filter((value): value is string => Boolean(value));
  }, [documents]);

  const handleSubmit = useCallback(
    async (event?: React.FormEvent<HTMLFormElement>) => {
      event?.preventDefault();
      if (!inputValue.trim() || isLoading) {
        return;
      }

      setError(null);
      const userMessage = createMessage("user", inputValue.trim());
      setMessages((prev) => [...prev, userMessage]);
      setInputValue("");
      setIsLoading(true);

      const payload: ChatRequestPayload = {
        query: userMessage.text,
        tenant_id: tenantId || undefined
      };

      try {
        const response: ChatResponse = await postChatQuery(payload);
        const assistantMessage = createMessage("assistant", response.answer, response.citations, response.latency_ms);
        setMessages((prev) => [...prev, assistantMessage]);
      } catch (apiError) {
        setError((apiError as Error).message ?? "Unknown error");
        // Restore input so the user can retry easily.
        setInputValue(userMessage.text);
        setMessages((prev) => prev.filter((message) => message.id !== userMessage.id));
      } finally {
        setIsLoading(false);
      }
    },
    [inputValue, isLoading, tenantId]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <section className="chat-panel">
      <header className="chat-header">
        <div className="chat-header-content">
          <h1>RAG Assistant</h1>
          <p>Ask about your tenant data. Responses are grounded with citations.</p>
          {ingestionSummary.length > 0 ? (
            <p className="chat-ingestion-summary">
              Recently ingested: {ingestionSummary.join(", ")}
            </p>
          ) : (
            <p className="chat-ingestion-summary">No recent documents. Ingest files to improve answers.</p>
          )}
        </div>
        <a
          className="chat-admin-link"
          href={`${getApiBaseUrl()}/admin/documents?tenant=${encodeURIComponent(tenantId || "default")}`}
          target="_blank"
          rel="noreferrer"
        >
          View ingestion status
        </a>
      </header>

      {error ? (
        <div className="chat-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      ) : null}

      <div className="chat-messages" role="log" aria-live="polite">
        {messages.map((message) => {
          const isAssistant = message.role === "assistant";
          const messageClasses = ["message", isAssistant ? "message-assistant" : "message-user"];
          if (isAssistant && message.text.trim().toLowerCase() === "i don't know") {
            messageClasses.push("message-unknown");
          }
          return (
            <div key={message.id} className={messageClasses.join(" ")}>
              <p>{message.text}</p>
              {isAssistant ? (
                <div className="message-meta">
                  {typeof message.latencyMs === "number" ? (
                    <span>Latency: {Math.round(message.latencyMs)} ms</span>
                  ) : null}
                  <CitationList citations={message.citations ?? []} tenantId={tenantId || "default"} />
                </div>
              ) : null}
            </div>
          );
        })}
        <div ref={scrollAnchorRef} />
      </div>

      <form className="chat-input-area" onSubmit={(event) => void handleSubmit(event)}>
        <textarea
          name="chat-input"
          placeholder="Type your question..."
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          rows={3}
        />
        <div className="chat-actions">
          <span className="chat-hint">Press Enter to send, Shift + Enter for a new line.</span>
          <button type="submit" disabled={isLoading || !inputValue.trim()}>
            {isLoading ? "Thinking…" : "Send"}
          </button>
        </div>
      </form>
    </section>
  );
};

export default ChatPanel;
