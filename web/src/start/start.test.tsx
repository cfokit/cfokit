import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { useEffect, type ReactNode } from "react";
import type { Export } from "../quickbooks/read";
import type { Reading } from "../quickbooks/readExport";
import { ConnectPage } from "./ConnectPage";
import { claudeLink, FirstQuestion, firstQuestion } from "./FirstQuestion";
import { GettingStarted } from "./GettingStarted";
import { ImportPage } from "./ImportPage";
import { StartedProvider, useStarted } from "./state";

// The pages of getting started (ADR-0058 § 1), with the reader, the API and the router stood in
// for. What the API returns here is a stand-in; what is asserted is what the page sends, and that
// it shows what it was given.

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));
vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "a-token", profile: { name: "Dana Whitfield" } },
    settings: { authority: "https://issuer.test/realms/cfokit" },
    signoutRedirect: vi.fn(),
  }),
}));
const reading = vi.fn<(file: File) => Promise<Reading>>();
vi.mock("../quickbooks/readExport", () => ({ readExport: (file: File) => reading(file) }));

// The synthetic export's shape, as the reader's own tests establish it from its rows.
const EXPORTED: Export = {
  company: { name: "Synthetic Co", basis: "accrual" },
  books: {
    shape_version: "1",
    system: "QuickBooks Online",
    fingerprint: "f".repeat(64),
    basis: "unknown",
    balances_basis: "cash",
    commodity: "USD",
    accounts: [
      {
        code: "Accounts Receivable",
        name: "Accounts Receivable",
        account_type: "asset",
        parent: "",
      },
      { code: "Checking", name: "Checking", account_type: "asset", parent: "" },
      { code: "Income:Consulting", name: "Income:Consulting", account_type: "income", parent: "" },
      {
        code: "Meals:Client Meals",
        name: "Meals:Client Meals",
        account_type: "unknown",
        parent: "",
      },
    ],
    entries: [
      {
        reference: "1",
        transaction_date: "2026-01-15",
        description: "Consulting",
        lines: [
          { account_code: "Accounts Receivable", amount: "1200.00", commodity: "USD" },
          { account_code: "Income:Consulting", amount: "-1200.00", commodity: "USD" },
        ],
      },
      {
        reference: "2",
        transaction_date: "2026-02-02",
        description: "Coffee",
        lines: [
          { account_code: "Meals:Client Meals", amount: "12.50", commodity: "USD" },
          { account_code: "Checking", amount: "-12.50", commodity: "USD" },
        ],
      },
    ],
    journal_total: { debits: "1212.50", credits: "1212.50" },
    balances: [{ account_code: "Checking", balance: "-12.50" }],
    rollups: [],
    statements: [],
  },
};

let requests: { path: string; body: unknown; authorization: string | null }[];
let answers: Record<string, unknown>;

beforeEach(() => {
  navigate.mockReset();
  reading.mockReset();
  requests = [];
  answers = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      requests.push({
        path,
        body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
        authorization: headers.get("authorization"),
      });
      const key = Object.keys(answers).find((suffix) => path.endsWith(suffix));
      return Promise.resolve(
        new Response(JSON.stringify(key === undefined ? {} : answers[key]), { status: 200 }),
      );
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

function WithExport({ children }: { children: ReactNode }) {
  const { setExported, setCompany } = useStarted();
  useEffect(() => {
    setExported(EXPORTED);
    setCompany("Synthetic Co");
  }, [setExported, setCompany]);
  return <>{children}</>;
}

function withExport(page: ReactNode) {
  return render(
    <StartedProvider>
      <WithExport>{page}</WithExport>
    </StartedProvider>,
  );
}

async function noViolations(container: HTMLElement) {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
}

function choose(container: HTMLElement, name: string) {
  const input = container.querySelector('input[type="file"]');
  if (input === null) throw new Error("no file input");
  fireEvent.change(input, { target: { files: [new File(["zip"], name)] } });
}

describe("the export, then the company", () => {
  test("a chosen export is read, and the company is prefilled from what it states", async () => {
    reading.mockResolvedValue({ ok: true, export: EXPORTED });
    const { container } = render(
      <StartedProvider>
        <GettingStarted />
      </StartedProvider>,
    );
    expect(screen.getByRole("heading", { name: "Bring in your books" })).toBeTruthy();
    await noViolations(container);

    choose(container, "export.zip");
    await screen.findByRole("heading", { name: "Your company" });
    expect(reading).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText("Company name") as HTMLInputElement).value).toBe("Synthetic Co");
    expect(screen.getByRole("button", { name: "Accrual" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect((screen.getByLabelText("Currency") as HTMLInputElement).value).toBe("USD");
    await noViolations(container);
  });

  test("creating the company declares everything, then goes on to the import", async () => {
    reading.mockResolvedValue({ ok: true, export: EXPORTED });
    answers["/entities"] = { entity_id: "ent-1", owner_grant_id: "g-1" };
    const { container } = render(
      <StartedProvider>
        <GettingStarted />
      </StartedProvider>,
    );
    choose(container, "export.zip");
    await screen.findByRole("heading", { name: "Your company" });

    fireEvent.change(screen.getByLabelText("Time zone"), { target: { value: "America/Chicago" } });
    fireEvent.click(screen.getByRole("button", { name: "Create the company" }));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(requests).toHaveLength(1);
    const [created] = requests;
    expect(created?.path).toBe("/entities");
    expect(created?.authorization).toBe("Bearer a-token");
    expect(created?.body).toMatchObject({
      name: "Synthetic Co",
      accounting_basis: "accrual",
      fiscal_year_end_month: 12,
      fiscal_year_end_day: 31,
      functional_currency: "USD",
      time_zone: "America/Chicago",
    });
    expect((created?.body as { slug: string }).slug).toMatch(/^synthetic-co-[0-9a-f]{6}$/);
    expect(navigate).toHaveBeenCalledWith({
      to: "/companies/$entityId/import",
      params: { entityId: "ent-1" },
    });
  });

  test("an impossible fiscal year end is refused before anything is sent", async () => {
    reading.mockResolvedValue({ ok: true, export: EXPORTED });
    const { container } = render(
      <StartedProvider>
        <GettingStarted />
      </StartedProvider>,
    );
    choose(container, "export.zip");
    await screen.findByRole("heading", { name: "Your company" });

    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Create the company" }));

    expect(await screen.findByText("Enter a day that month has.")).toBeTruthy();
    expect(requests).toEqual([]);
  });

  test("a refused export says why in the person's terms", async () => {
    reading.mockResolvedValue({ ok: false, code: "import_refused", detail: "no Journal.xlsx" });
    const { container } = render(
      <StartedProvider>
        <GettingStarted />
      </StartedProvider>,
    );
    choose(container, "export.zip");
    expect(await screen.findByText("Not a QuickBooks export")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Bring in your books" })).toBeTruthy();
  });

  test("a file that is not a .zip is refused without being read", async () => {
    const { container } = render(
      <StartedProvider>
        <GettingStarted />
      </StartedProvider>,
    );
    choose(container, "books.pdf");
    expect(await screen.findByText("Not a .zip file")).toBeTruthy();
    expect(reading).not.toHaveBeenCalled();
  });
});

describe("the import", () => {
  test("what will be imported: the counts, the period, and what to expect", async () => {
    const { container } = withExport(<ImportPage entityId="ent-1" />);
    await screen.findByRole("heading", { name: "What will be imported" });
    const counts = container.querySelector("dl") as HTMLElement;
    expect(within(counts).getByText("Transactions").nextElementSibling?.textContent).toBe("2");
    expect(within(counts).getByText("Posting lines").nextElementSibling?.textContent).toBe("4");
    expect(within(counts).getByText("Accounts").nextElementSibling?.textContent).toBe("4");
    expect(within(counts).getByText("Covering").nextElementSibling?.textContent).toBe(
      "2026-01-15 to 2026-02-02",
    );
    expect(screen.getByText("Accounts with no type")).toBeTruthy();
    expect(screen.getByText("Expect a difference")).toBeTruthy();
    await noViolations(container);
  });

  test("importing opens, posts in batches, reconciles, and leads with the answer", async () => {
    answers["/imports"] = { import_id: "imp-1", accounts_created: 4, accounts_already_present: 0 };
    answers["/entries"] = { posted: 2, replayed: 0, refusals: [] };
    answers["/reconciliation"] = {
      agreed: 2,
      compared: 3,
      journal_total: {
        stated_debits: "1212.50",
        stated_credits: "1212.50",
        our_debits: "1212.50",
        our_credits: "1212.50",
        agrees: true,
        difference: "0",
      },
      divergences_net_to_zero: true,
      divergences: [{ account_code: "Accounts Receivable", ours: "1200.00", theirs: "0" }],
    };
    const { container } = withExport(<ImportPage entityId="ent-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Import" }));

    await screen.findByRole("heading", { name: "Do the books agree?" });
    expect(requests.map((request) => request.path)).toEqual([
      "/entities/ent-1/imports",
      "/entities/ent-1/imports/imp-1/entries",
      "/entities/ent-1/imports/imp-1/reconciliation",
    ]);
    expect(requests[0]?.body).toMatchObject({ fingerprint: "f".repeat(64), basis: "unknown" });
    expect((requests[1]?.body as { entries: unknown[] }).entries).toHaveLength(2);
    expect(requests[2]?.body).toEqual({
      balances: EXPORTED.books.balances,
      journal_total: EXPORTED.books.journal_total,
      statements: [],
    });
    expect(screen.getByText("2 of 3 accounts match QuickBooks exactly.")).toBeTruthy();
    expect(screen.getByText(/Every transaction came across/)).toBeTruthy();
    expect(
      screen.getByRole("table", { name: "Accounts that differ from QuickBooks" }),
    ).toBeTruthy();
    await noViolations(container);

    fireEvent.click(screen.getByRole("button", { name: "Next: connect Claude" }));
    expect(navigate).toHaveBeenCalledWith({
      to: "/companies/$entityId/connect",
      params: { entityId: "ent-1" },
    });
  });

  test("after a reload the export is asked for again, because it is never stored", () => {
    render(
      <StartedProvider>
        <ImportPage entityId="ent-1" />
      </StartedProvider>,
    );
    expect(screen.getByRole("heading", { name: "Choose the export again" })).toBeTruthy();
  });
});

describe("connecting Claude and the first question", () => {
  test("the client registration goes where the issuer's metadata says", async () => {
    answers["/.well-known/openid-configuration"] = {
      registration_endpoint: "https://issuer.test/realms/cfokit/register-here",
    };
    const { container } = withExport(<ConnectPage entityId="ent-1" />);
    await screen.findByText(/register-here/);
    expect(requests[0]?.path).toBe(
      "https://issuer.test/realms/cfokit/.well-known/openid-configuration",
    );
    await noViolations(container);
  });

  test("the first question names the company, and the link drafts it in a new Claude chat", async () => {
    const prompt = firstQuestion("Synthetic Co", "ent-1");
    expect(prompt).toContain('"Synthetic Co" (entity ent-1)');
    expect(prompt).toContain("Confirm they match QuickBooks and explain any differences");
    expect(claudeLink(prompt)).toBe(`claude://claude.ai/new?q=${encodeURIComponent(prompt)}`);

    const { container } = withExport(<FirstQuestion entityId="ent-1" />);
    const block = await screen.findByRole("figure", { name: "Or paste this into Claude" });
    await waitFor(() => expect(block.querySelector("pre")?.textContent).toBe(prompt));
    expect(screen.getByRole("button", { name: "Continue in Claude" })).toBeTruthy();
    await noViolations(container);
  });
});
