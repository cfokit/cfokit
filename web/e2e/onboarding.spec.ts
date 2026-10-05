/**
 * Getting started, end to end (ADR-0058; ADR-0049's confirmation): a new person creates an account
 * on the issuer's page, sets up an authenticator app, chooses the sample export, confirms the company, imports, and reaches the
 * first question — in a real browser, against the compose stack, as the person would.
 *
 * Every expected figure is one the synthetic export states for itself (`synthetic.ts`): two
 * transactions, 1,200.00 and 12.50, a journal total of 1,212.50, and a general ledger stating three
 * account balances — Accounts Receivable 1,200.00, Income:Consulting −1,200.00 and Checking −12.50,
 * with Meals a subtotal rather than a balance (ADR-0036: never a value read back from a first run).
 */

import { expect, test, type Locator, type Page } from "@playwright/test";
import Big from "big.js";
import { syntheticExport } from "../src/quickbooks/synthetic.ts";
import { totp } from "./totp.ts";

// A pause on each screen so a person watching the recording can read it, and typing a person can
// see; neither in a gate run.
const PACE = Number(process.env.E2E_PACE ?? "0");
const settle = (page: Page) => (PACE > 0 ? page.waitForTimeout(PACE) : Promise.resolve());
const type = (field: Locator, text: string) =>
  PACE > 0 ? field.pressSequentially(text, { delay: 35 }) : field.fill(text);

interface TrialBalance {
  balances: boolean;
  total_debit: string;
  total_credit: string;
  lines: { name: string; debit: string | null; credit: string | null }[];
}

test("a new person goes from creating an account to their first question", async ({
  page,
  request,
}) => {
  // The bearer token the web client sends the API, kept so the books can be checked over REST
  // as the same person — the token lives in the client's memory and nowhere else (ADR-0049 § 2).
  let bearer: string | undefined;
  page.on("request", (sent) => {
    const header = sent.headers()["authorization"];
    if (header?.startsWith("Bearer ")) bearer = header;
  });

  const stamp = Date.now();
  await page.goto("./");

  // The issuer's page, in CFOKit's theme.
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await settle(page);
  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await type(page.getByLabel("Email"), `sam.${stamp}@example.test`);
  await type(page.getByLabel("First name"), "Sam");
  await type(page.getByLabel("Last name"), "Sample");
  await type(page.getByLabel("Password", { exact: true }), `Sample-${stamp}-password`);
  await type(page.getByLabel("Confirm password"), `Sample-${stamp}-password`);
  await settle(page);
  await page.getByRole("button", { name: "Create account" }).click();

  // A second factor before the first sign-in completes (SOC2-19): the key an authenticator app
  // would hold, entered by hand, and the code it would show.
  await expect(page.getByRole("heading", { name: "Set up two-step sign-in" })).toBeVisible();
  await settle(page);
  await page.getByRole("link", { name: "Can't scan it? Enter a key instead" }).click();
  const key = await page.locator("li code").innerText();
  await type(page.getByLabel("Device name"), "Phone");
  await type(page.getByLabel("Code", { exact: true }), totp(key));
  await settle(page);
  await page.getByRole("button", { name: "Turn on" }).click();

  // Back in CFOKit, signed in: choose the export.
  await expect(page.getByRole("heading", { name: "Bring in your books" })).toBeVisible();
  await settle(page);
  await page.locator('input[type="file"]').setInputFiles({
    name: "quickbooks-sample.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(await syntheticExport()),
  });

  // The company, as the export states it.
  await expect(page.getByRole("heading", { name: "Your company" })).toBeVisible();
  await expect(page.getByLabel("Company name")).toHaveValue("Synthetic Co");
  await expect(page.getByRole("button", { name: "Accrual", pressed: true })).toBeVisible();
  await expect(page.getByLabel("Currency")).toHaveValue("USD");
  await settle(page);
  await page.getByRole("button", { name: "Create the company" }).click();

  // What will be imported, then the import.
  await expect(page.getByRole("heading", { name: "What will be imported" })).toBeVisible();
  await expect(page.getByText("Transactions").locator("xpath=following-sibling::dd[1]")).toHaveText(
    "2",
  );
  const entityId = /\/companies\/([^/]+)\/import/.exec(page.url())?.[1];
  expect(entityId).toBeDefined();
  await settle(page);
  await page.getByRole("button", { name: "Import", exact: true }).click();

  // The answer first: whether the books agree with QuickBooks.
  await expect(page.getByRole("heading", { name: "Do the books agree?" })).toBeVisible();
  await expect(page.getByText("3 of 3 accounts match QuickBooks exactly.")).toBeVisible();
  await expect(
    page.getByText(/Every transaction came across: the books total 1,212\.50/),
  ).toBeVisible();
  await settle(page);

  // The books landed: the trial balance, read over REST as the same person.
  expect(bearer).toBeDefined();
  const response = await request.get(`/entities/${entityId}/trial-balance`, {
    headers: { authorization: bearer ?? "" },
  });
  expect(response.ok()).toBe(true);
  const trial = (await response.json()) as TrialBalance;
  expect(trial.balances).toBe(true);
  expect(new Big(trial.total_debit).eq("1212.50")).toBe(true);
  expect(new Big(trial.total_credit).eq("1212.50")).toBe(true);
  const net = (name: string) => {
    const line = trial.lines.find((candidate) => candidate.name === name);
    expect(line, name).toBeDefined();
    return new Big(line?.debit ?? "0").minus(line?.credit ?? "0").toFixed(2);
  };
  expect(net("Accounts Receivable")).toBe("1200.00");
  expect(net("Checking")).toBe("-12.50");

  // Connecting Claude, with this deployment's own MCP address.
  await page.getByRole("button", { name: "Next: connect Claude" }).click();
  await expect(page.getByRole("heading", { name: "Connect Claude" })).toBeVisible();
  await expect(page.getByRole("figure", { name: "Configuration" })).toContainText("/mcp");
  await settle(page);
  await page.getByRole("button", { name: "Next: your first question" }).click();

  // The first question, ready to send.
  await expect(page.getByRole("heading", { name: "Ask Claude about your books" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue in Claude" })).toBeVisible();
  await expect(page.getByRole("figure", { name: "Or paste this into Claude" })).toContainText(
    "Confirm they match QuickBooks and explain any differences",
  );
  await settle(page);
  await settle(page);
});
