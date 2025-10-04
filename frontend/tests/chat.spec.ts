import { test, expect } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

test.describe("Chat UI", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`${apiBase}/admin/documents?**`, async (route) => {
      await route.fulfill({
        json: {
          items: [
            { id: "doc-1", title: "Employee Handbook" },
            { id: "doc-2", title: "Support Guide" }
          ],
          total: 2,
          page: 1,
          page_size: 5
        }
      });
    });
  });

  test("shows assistant reply with citations", async ({ page }) => {
    await page.route(`${apiBase}/chat/query`, async (route) => {
      await route.fulfill({
        json: {
          answer: "Refer to the handbook [1].",
          citations: [
            {
              document_id: "doc-1",
              chunk_id: "chunk-1",
              score: 0.9,
              normalized_score: 0.9,
              title: "Employee Handbook",
              snippet: "All employees must review..."
            }
          ],
          token_usage: { prompt_tokens: 2, completion_tokens: 5, total_tokens: 7 },
          model: "stub",
          prompt_id: "prompt-1",
          latency_ms: 21.5
        }
      });
    });

    await page.goto("/");

    const textbox = page.getByPlaceholder("Type your question...");
    await textbox.fill("Where is the handbook?");
    await page.getByRole("button", { name: /send/i }).click();

    await expect(page.getByText("Refer to the handbook [1].")).toBeVisible();
    await expect(page.getByRole("link", { name: /view document/i })).toBeVisible();
  });

  test("renders unknown styling when answer is I don't know", async ({ page }) => {
    await page.route(`${apiBase}/chat/query`, async (route) => {
      await route.fulfill({
        json: {
          answer: "I don't know",
          citations: [],
          token_usage: { prompt_tokens: 2, completion_tokens: 0, total_tokens: 2 },
          model: "stub",
          prompt_id: "prompt-2",
          latency_ms: 18
        }
      });
    });

    await page.goto("/");

    const textbox = page.getByPlaceholder("Type your question...");
    await textbox.fill("Unknown question");
    await page.getByRole("button", { name: /send/i }).click();

    const unknownMessage = page.locator(".message-unknown");
    await expect(unknownMessage).toContainText("I don't know");
  });
});
