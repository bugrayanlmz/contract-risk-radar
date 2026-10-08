import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { document, results } from "./fixtures";
import type { AiFindingResult } from "../src/api/generated/types.gen";
const bytes = readFileSync("e2e/assets/evidence-layout.pdf");
const ai = (
  id: string,
  title: string,
  quote: string,
  score = 4,
): AiFindingResult => ({
  id,
  title,
  related_category: null,
  quote,
  explanation: "An English explanation of a practical burden.",
  model_score: score,
  score,
  rationale: "A synthetic assessment of practical impact.",
  uncertainties: ["This test is not legal advice."],
  warnings: [],
  quote_verified: true,
});
const output = {
  ...results,
  ai_overall_score: 5,
  ai_review_status: "completed" as const,
  ai_rubric_version: "1.0",
  ai_findings: [
    ai(
      "a1",
      "Shared passage issue",
      "The lease automatically renews for twelve months.",
    ),
    ai(
      "a2",
      "German liability",
      "Der Mieter haftet unbegrenzt für alle Schäden.",
      5,
    ),
    ai(
      "a3",
      "German split words",
      '"Die Überwachung der Straße ist vorgeschrieben."',
    ),
    ai(
      "a4",
      "Cross-page charges",
      "The tenant must pay unlimited extra charges.",
    ),
    ai("a5", "Rotated notice", "A rotated notice requires monthly inspection."),
    ai("a6", "Ligature obligation", "A financial obligation remains.", 2),
    ai(
      "a7",
      "Missing PDF location",
      "A backend-verified quote absent from the PDF.js index.",
    ),
    {
      ...ai("a8", "Unverified AI issue", "An invented AI quote.", 5),
      quote_verified: false,
      score: null,
      warnings: ["Unverified quote excluded from the AI score."],
    },
  ],
};
async function mock(page: Page, previewError: boolean | "corrupt" = false) {
  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/file"))
      return route.fulfill({
        status: previewError === true ? 500 : 200,
        contentType: "application/pdf",
        body: previewError ? "preview failure" : bytes,
      });
    const body = path.endsWith("/results")
      ? output
      : path.startsWith("/api/auth/")
        ? { id: "demo", email: "demo@example.com" }
        : { ...document, status: "completed", stage: "completed" };
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}
async function pdfTab(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole("tab", { name: "PDF", exact: true }).click();
}

test("PDF passage selects a persistent finding and shared evidence opens a chooser", async ({
  page,
  isMobile,
}) => {
  await mock(page);
  await page.goto(`/app/documents/${document.id}`);
  await pdfTab(page, isMobile);
  const mark = page.getByRole("button", {
    name: "AI finding: German liability",
    exact: true,
  });
  await expect(mark).toBeVisible();
  await mark.click();
  const selected = page.locator(".finding-slot.selected");
  await expect(selected).toContainText("German liability");
  await expect(selected).toContainText("Selected finding");
  await expect(
    page.getByRole("heading", { name: "Rule-based risk", exact: true }),
  ).toBeVisible();
  await pdfTab(page, isMobile);
  await page
    .getByRole("button", {
      name: /Rule finding: Auto renewal; AI finding: Shared passage issue/,
    })
    .first()
    .click();
  await expect(
    page.getByRole("dialog", { name: "Choose finding" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "AI · Shared passage issue", exact: true })
    .click();
  await expect(selected).toContainText("Shared passage issue");
  await page.screenshot({
    path: `test-results/pdf-selected-${isMobile ? "mobile" : "desktop"}.png`,
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Contract details" }).click();
  await expect(
    page.getByRole("heading", { name: "Important dates" }),
  ).toBeAttached();
  await page
    .getByRole("tab", { name: /^Findings/ })
    .last()
    .click();
  await expect(selected).toContainText("Shared passage issue");
});

test("cards navigate to all exact matches, split German, ligatures, cross-page and rotated evidence", async ({
  page,
  isMobile,
}) => {
  await mock(page);
  await page.goto(`/app/documents/${document.id}`);
  const card = (id: string) => page.locator(`[id="finding-ai:${id}"]`);
  await expect(card("a7").getByText("PDF location unavailable")).toBeAttached();
  await expect(
    card("a8").getByRole("button", { name: "View in PDF" }),
  ).toHaveCount(0);
  for (const [id, title, number] of [
    ["a3", "German split words", 2],
    ["a4", "Cross-page charges", 2],
    ["a5", "Rotated notice", 4],
    ["a6", "Ligature obligation", 1],
  ] as const) {
    if (isMobile)
      await page.getByRole("tab", { name: "Findings", exact: true }).click();
    await card(id).getByRole("button", { name: "View in PDF" }).click();
    await expect(page.getByLabel("PDF page number")).toHaveValue(
      String(number),
    );
    await expect(
      page
        .getByRole("button", { name: `AI finding: ${title}`, exact: true })
        .first(),
    ).toBeVisible();
    await expect(page.locator(".pdf-mark.selected").first()).toBeInViewport();
  }
  await page.getByLabel("PDF page number").fill("1");
  await page.getByRole("button", { name: "Go to PDF page" }).click();
  await expect(
    page.getByRole("button", { name: /Shared passage issue/ }).first(),
  ).toBeVisible();
  expect(await page.locator(".react-pdf__Page canvas").count()).toBeLessThan(4);
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.getByText("120%", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "AI finding: Ligature obligation",
      exact: true,
    }),
  ).toBeVisible();
  const rect = await page
    .getByRole("button", {
      name: "AI finding: Ligature obligation",
      exact: true,
    })
    .boundingBox();
  expect(rect?.width).toBeGreaterThan(20);
  await page.getByRole("button", { name: "Fit width", exact: true }).click();
  if (!isMobile) {
    await page.setViewportSize({ width: 1100, height: 900 });
    await expect(
      page.getByRole("button", {
        name: "AI finding: Ligature obligation",
        exact: true,
      }),
    ).toBeVisible();
  }
  await page
    .getByRole("button", {
      name: "AI finding: Ligature obligation",
      exact: true,
    })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".finding-slot.selected")).toContainText(
    "Ligature obligation",
  );
});

test("preview failure preserves findings and source download", async ({
  page,
}) => {
  await mock(page, true);
  await page.goto(`/app/documents/${document.id}`);
  await expect(
    page.getByRole("heading", { name: "Rule-based findings" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download PDF" }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("PDF location unavailable").first(),
  ).toBeAttached();
  expect(await page.locator(".pdf-mark").count()).toBe(0);
});

test("invalid PDF preview preserves the completed analysis", async ({
  page,
  isMobile,
}) => {
  await mock(page, "corrupt");
  await page.goto(`/app/documents/${document.id}`);
  await expect(
    page.getByRole("heading", { name: "Rule-based findings" }),
  ).toBeVisible();
  await pdfTab(page, isMobile);
  await expect(
    page.getByRole("heading", { name: "PDF preview unavailable" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download PDF" }).last(),
  ).toBeVisible();
});
