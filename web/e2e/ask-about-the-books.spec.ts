/**
 * Ask about the books, end to end: a person with their books imported asks CFOKit about them in
 * the web client's chat, allows CFOKit in the company the first time, and reads the answer
 * (ADR-0068 § 3, ADR-0075, ADR-0077). In a real browser, against the compose stack.
 *
 * CI holds no inference credential (ADR-0004), so the stack runs the agent's scripted stand-in
 * (CFOKIT_AGENT_MODEL=scripted, `src/cfokit/agent/scripted.py`): the tool it calls, the books it
 * reads and every figure on screen are real; only the words around them are a script's.
 *
 * Every expected figure is one the synthetic export states for itself (`synthetic.ts`): income of
 * 1,200.00 and an expense of 12.50, so net income of 1,187.50 (ADR-0036: never a value read back
 * from a first run).
 *
 * Its steps are the clips in `docs/how-to/ask-about-your-books.md` (ADR-0074).
 */

import { expect, test, type Page } from "@playwright/test";
import { syntheticExport } from "../src/quickbooks/synthetic.ts";
import { totp } from "./totp.ts";

const PACE = Number(process.env.E2E_PACE ?? "0");
const settle = (page: Page) => (PACE > 0 ? page.waitForTimeout(PACE) : Promise.resolve());

const SECOND_FACTOR_REQUIRED = process.env.E2E_REQUIRE_SECOND_FACTOR === "true";

/** A new person with the sample export imported: getting started, which is not this use case. */
async function withBooksImported(page: Page): Promise<string> {
  const stamp = Date.now();
  await page.goto("./");
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill(`ask.${stamp}@example.test`);
  await page.getByLabel("First name").fill("Ari");
  await page.getByLabel("Last name").fill("Asker");
  await page.getByLabel("Password", { exact: true }).fill(`Sample-${stamp}-password`);
  await page.getByLabel("Confirm password").fill(`Sample-${stamp}-password`);
  await page.getByRole("button", { name: "Create account" }).click();
  if (SECOND_FACTOR_REQUIRED) {
    await page.getByRole("link", { name: "Can't scan it? Enter a key instead" }).click();
    const key = await page.locator("li code").innerText();
    await page.getByLabel("Device name").fill("Phone");
    await page.getByLabel("Code", { exact: true }).fill(totp(key));
    await page.getByRole("button", { name: "Turn on" }).click();
  }
  await expect(page.getByRole("heading", { name: "Bring in your books" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "quickbooks-sample.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(await syntheticExport()),
  });
  await page.getByRole("button", { name: "Create the company" }).click();
  await expect(page.getByRole("heading", { name: "What will be imported" })).toBeVisible();
  const entityId = /\/companies\/([^/]+)\/import/.exec(page.url())?.[1];
  expect(entityId).toBeDefined();
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByText("4 of 4 accounts match QuickBooks exactly.")).toBeVisible();
  return entityId ?? "";
}

test("a person asks CFOKit about their books in the chat", async ({ page }) => {
  const entityId = await withBooksImported(page);
  await page.goto(`./companies/${entityId}/ask`);
  await expect(page.getByRole("heading", { name: "Ask Claude about your books" })).toBeVisible();

  const composer = page.getByRole("textbox", { name: "Ask about your books" });

  // Each step is a clip of the how-to's (ADR-0074), and its title the clip's caption.
  await test.step("Ask CFOKit here", async () => {
    await settle(page);
    await page.getByRole("button", { name: "Ask CFOKit here instead" }).click();
    // The chat, with the first question waiting; the first time, CFOKit asks to be allowed.
    await expect(page).toHaveURL(/\/chat\/[0-9a-f-]+$/);
    await expect(composer).toHaveValue(/^My books are imported into CFOKit\. Confirm they match/);
    await expect(page.getByText("Not allowed yet")).toBeVisible();
    await settle(page);
  });

  await test.step("Allow CFOKit in your company", async () => {
    await page.getByRole("button", { name: "Allow CFOKit" }).click();
    await page.getByRole("button", { name: "Allow to keep the books" }).click();
    await expect(page.getByText("CFOKit can act in Synthetic Co now.")).toBeVisible();
    await settle(page);
    await page.getByRole("button", { name: "Ask CFOKit" }).click();
    await expect(composer).toHaveValue(/Confirm they match QuickBooks/);
    await expect(page.getByText("Not allowed yet")).toHaveCount(0);
    await settle(page);
  });

  await test.step("Read the answer", async () => {
    await page.getByRole("button", { name: "Send" }).click();
    // The tool it read, then the figures, the books' own.
    await expect(page.getByText("Read profit and loss")).toBeVisible();
    const answer = page.getByRole("table");
    await expect(answer).toContainText("Income:Consulting");
    await expect(answer).toContainText(/1,?200\.00/);
    await expect(answer).toContainText(/12\.50/);
    await expect(answer).toContainText(/1,?187\.50/);
    // The newest message in view, its last line included.
    await expect(answer.getByRole("row").last()).toBeInViewport();
    await settle(page);
    await settle(page);
  });

  await test.step("Come back to it", async () => {
    // A reload shows the conversation as the agent kept it (ADR-0075 § 1).
    await page.reload();
    await expect(page.getByText(/Confirm they match QuickBooks/)).toBeVisible();
    await expect(page.getByRole("table")).toContainText(/1,?187\.50/);
    await settle(page);
  });
});
