import { rest } from "msw";
import { setupServer } from "msw/node";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

import ChatPanel from "../../components/ChatPanel";
import { getApiBaseUrl } from "../../lib/api";

const server = setupServer();

beforeAll(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});

const documentsHandler = rest.get(`${getApiBaseUrl()}/admin/documents`, (req, res, ctx) => {
  return res(
    ctx.json({
      items: [
        { id: "doc-1", title: "Employee Handbook" },
        { id: "doc-2", title: "Support Guide" }
      ],
      total: 2,
      page: 1,
      page_size: 5
    })
  );
});

function getChatHandler(response: { answer: string; citations: unknown[] }) {
  return rest.post(`${getApiBaseUrl()}/chat/query`, async (req, res, ctx) => {
    return res(
      ctx.json({
        ...response,
        token_usage: { prompt_tokens: 5, completion_tokens: 3, total_tokens: 8 },
        model: "stub",
        prompt_id: "prompt-123",
        latency_ms: 12.3
      })
    );
  });
}

async function submitQuestion(question: string) {
  const textarea = screen.getByPlaceholderText(/type your question/i);
  await userEvent.type(textarea, question);
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatPanel", () => {
  test("renders fallback when answer is 'I don't know'", async () => {
    server.use(documentsHandler, getChatHandler({ answer: "I don't know", citations: [] }));

    render(<ChatPanel tenantId="default" />);

    await submitQuestion("What is our refund policy?");

    await waitFor(() => {
      expect(screen.getByText("I don't know")).toBeInTheDocument();
    });
    expect(screen.getByText(/No supporting documents were cited/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/type your question/i)).toHaveValue("");
  });

  test("displays citations for a successful answer", async () => {
    server.use(
      documentsHandler,
      getChatHandler({
        answer: "Refer to the onboarding guide [1].",
        citations: [
          {
            document_id: "doc-1",
            chunk_id: "chunk-1",
            score: 0.9,
            normalized_score: 0.88,
            title: "Employee Handbook",
            snippet: "All employees must review..."
          }
        ]
      })
    );

    render(<ChatPanel tenantId="default" />);

    await submitQuestion("Where is the onboarding guide?");

    await waitFor(() => {
      expect(screen.getByText(/Refer to the onboarding guide/)).toBeInTheDocument();
    });

    const citations = screen.getAllByText(/view document/i);
    expect(citations).toHaveLength(1);
    expect(screen.getByPlaceholderText(/type your question/i)).toHaveValue("");
  });
});
