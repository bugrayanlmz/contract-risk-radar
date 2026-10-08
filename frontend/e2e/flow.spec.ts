import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { document, results } from "./fixtures";

async function mockApi(page: Page, failure = false, allowReal = true) {
  let polls = 0;
  let retried = false;
  let uploaded = false;
  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    const json = (value: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (path.startsWith("/api/auth/"))
      return json({ id: "demo-user", email: "demo@example.com" });
    if (path === "/api/capabilities")
      return json({
        supported_languages: ["english", "german"],
        real_documents_allowed: allowReal,
      });
    if (path.endsWith("/file"))
      return route.fulfill({
        contentType: "application/pdf",
        body: readFileSync("e2e/assets/evidence-layout.pdf"),
      });
    if (path === "/api/samples")
      return json([
        {
          id: "balanced-lease",
          name: "The straightforward lease",
          description: "Clear terms and modest fees.",
        },
      ]);
    if (path === "/api/samples/balanced-lease/file")
      return route.fulfill({
        contentType: "application/pdf",
        body: "%PDF-test-fixture",
      });
    if (path === "/api/documents" && method === "GET")
      return json(uploaded ? [document] : []);
    if (path === "/api/documents" && method === "POST") {
      uploaded = true;
      return json(document, 202);
    }
    if (path.endsWith("/results")) return json(results);
    if (path.endsWith("/retry")) {
      retried = true;
      polls = 0;
      return json(document, 202);
    }
    if (path === `/api/documents/${document.id}`) {
      if (failure && !retried)
        return json({
          ...document,
          status: "failed",
          stage: "failed",
          error_code: "PROVIDER_UNAVAILABLE",
          error_message:
            "The analysis provider is temporarily unavailable. Please retry.",
          retryable: true,
        });
      polls += 1;
      return json(
        polls >= 3
          ? {
              ...document,
              status: "completed",
              stage: "completed",
              completed_at: "2026-10-07T18:01:00Z",
            }
          : {
              ...document,
              stage: polls === 2 ? "verifying" : "extracting_clauses",
            },
      );
    }
    return json(
      { error: { code: "NOT_FOUND", message: "Test fixture not found." } },
      404,
    );
  });
}

test("landing, registration, sample upload, polling, and evidence results", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Know what’s in/ }),
  ).toBeVisible();
  await expect(
    page.getByText("Contract analysis demo. Not legal advice."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Explore your contract" }).click();
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password").fill("demo-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(
    page.getByRole("heading", { name: "My contracts." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Start your first analysis" }).click();
  await expect(
    page.getByRole("button", { name: "Analyze contract" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: /The straightforward lease/ }).click();
  await expect(page.getByText("balanced-lease.pdf")).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Analyze contract" }).click();
  await expect(
    page.getByRole("heading", { name: /Extracting contract facts/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Rule-based findings" }),
  ).toBeVisible({ timeout: 12_000 });
  await expect(page.getByText("4 / 5")).toBeVisible();
  await page
    .getByText("Unverified quote", { exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByText("Unverified quote", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Not scored", { exact: true })).toBeVisible();
  await page.getByText("Not found in the extraction").scrollIntoViewIfNeeded();
  await expect(page.getByText("Not found in the extraction")).toBeVisible();
  await page.getByRole("tab", { name: "Contract details" }).click();
  await page
    .getByRole("heading", { name: "Important dates" })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("heading", { name: "Important dates" }),
  ).toBeVisible();
  const calls = await page.evaluate(
    () =>
      performance
        .getEntriesByType("resource")
        .filter((entry) =>
          entry.name.endsWith("/00000000-0000-4000-8000-000000000001"),
        ).length,
  );
  await page.waitForTimeout(2500);
  const later = await page.evaluate(
    () =>
      performance
        .getEntriesByType("resource")
        .filter((entry) =>
          entry.name.endsWith("/00000000-0000-4000-8000-000000000001"),
        ).length,
  );
  expect(later).toBe(calls);
});

test("readable failure can be retried", async ({ page }) => {
  await mockApi(page, true);
  await page.goto(`/app/documents/${document.id}`);
  await expect(
    page.getByText(
      "The analysis provider is temporarily unavailable. Please retry.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry analysis" }).click();
  await expect(
    page.getByRole("heading", { name: "Rule-based findings" }),
  ).toBeVisible({ timeout: 12_000 });
});

test("file limits and confirmation are enforced in the UI", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/app/upload");
  await page.getByLabel("Contract PDF").setInputFiles({
    name: "bad.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not PDF"),
  });
  await expect(page.getByText("Choose a PDF file.")).toBeVisible();
  await page
    .getByLabel("Contract PDF")
    .setInputFiles("../samples/balanced-lease.pdf");
  await expect(
    page.getByRole("button", { name: "Analyze contract" }),
  ).toBeDisabled();
  await page.getByRole("checkbox").check();
  await expect(
    page.getByRole("button", { name: "Analyze contract" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Remove selected file" }).click();
  await expect(
    page.getByRole("button", { name: "Analyze contract" }),
  ).toBeDisabled();
});

test("real uploads require the selected type and fresh provider transmission consent", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/app/upload");
  await page
    .getByLabel("Contract PDF")
    .setInputFiles("../samples/balanced-lease.pdf");
  await page.getByRole("checkbox").check();
  await page
    .getByRole("radio", { name: "Real contract (local development)" })
    .check();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await expect(
    page.getByRole("button", { name: "Analyze contract" }),
  ).toBeDisabled();
  await page.getByRole("checkbox").check();
  const pending = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/api/documents" &&
      request.method() === "POST",
  );
  await page.getByRole("button", { name: "Analyze contract" }).click();
  const request = await pending;
  expect(request.postData()).toContain('name="document_kind"\r\n\r\nreal');
  expect(request.postData()).toContain(
    'name="analysis_consent_confirmed"\r\n\r\ntrue',
  );
});

test("real contract option is absent when the backend capability is disabled", async ({
  page,
}) => {
  await mockApi(page, false, false);
  await page.goto("/app/upload");
  await expect(
    page.getByRole("radio", { name: "Synthetic example" }),
  ).toBeVisible();
  await expect(
    page.getByRole("radio", { name: "Real contract (local development)" }),
  ).toHaveCount(0);
});
