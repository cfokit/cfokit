import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { StartedProvider } from "../start/state";
import { claudeLink } from "../start/FirstQuestion";
import { dismissalKey, QuestionsPage, unresolvedQuestion } from "./QuestionsPage";

// The page every `unresolved_transaction` notification links to, with the API stood in for. What
// the API returns here is a stand-in; what is asserted is what the page sends, and that it shows
// what it was given.

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "a-token", profile: { name: "Dana Whitfield" } },
    settings: { authority: "https://issuer.test/realms/cfokit" },
    signoutRedirect: vi.fn(),
  }),
}));

const ENTITY = "e-1";

const LINES = [
  {
    source_ref: "ref-coffee",
    transaction_id: "t-1",
    decision_id: "d-1",
    payee: "Blue Bottle",
    description: "Card purchase",
    amount: "-240.0000000000",
    commodity: "USD",
    source_account_id: "a-1",
    transaction_date: "2026-03-14",
    source_kind: "statement",
  },
  {
    source_ref: "ref-transfer",
    transaction_id: "t-2",
    decision_id: "d-2",
    payee: "",
    description: "Transfer in",
    amount: "1250.5050000000",
    commodity: "USD",
    source_account_id: "a-1",
    transaction_date: "2026-03-15",
    source_kind: "statement",
  },
];

const NOTIFICATION = {
  notification_id: "n-1",
  entity_id: ENTITY,
  notification_class: "unresolved_transaction",
  subject_ref: "ref-coffee",
  link: `/app/companies/${ENTITY}/questions`,
  raised_at: "2026-03-14T10:00:00Z",
};

const COMPANY = {
  id: ENTITY,
  slug: "harbor-lane",
  name: "Harbor Lane Bakery",
  accounting_basis: "accrual",
  fiscal_year_end_month: 12,
  fiscal_year_end_day: 31,
  functional_currency: "USD",
  time_zone: "America/New_York",
};

interface Sent {
  path: string;
  method: string;
  idempotencyKey: string | null;
  authorization: string | null;
}

let requests: Sent[];
let answers: Record<string, { status: number; body: unknown }>;

beforeEach(() => {
  requests = [];
  answers = {
    [`/entities/${ENTITY}`]: { status: 200, body: COMPANY },
    "/unresolved-transactions": { status: 200, body: { unresolved: LINES } },
    "/notifications": { status: 200, body: { notifications: [NOTIFICATION] } },
    "/dismissal": { status: 201, body: { notification_id: "n-1", replayed: false } },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      requests.push({
        path,
        method: init?.method ?? "GET",
        idempotencyKey: headers.get("idempotency-key"),
        authorization: headers.get("authorization"),
      });
      const key = Object.keys(answers).find((suffix) => path.endsWith(suffix));
      const answer = key === undefined ? { status: 200, body: {} } : answers[key];
      return Promise.resolve(
        new Response(JSON.stringify(answer?.body ?? {}), { status: answer?.status ?? 200 }),
      );
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function page() {
  return render(
    <StartedProvider>
      <QuestionsPage entityId={ENTITY} />
    </StartedProvider>,
  );
}

async function noViolations(container: HTMLElement) {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
}

describe("questions for you", () => {
  test("lists the lines no rule resolved, as the API gave them, with the person's token", async () => {
    const { container } = page();
    const table = await screen.findByRole("table", { name: "Transactions waiting for a rule" });
    expect(requests.map((r) => r.path).sort()).toEqual([
      `/entities/${ENTITY}`,
      `/entities/${ENTITY}/notifications`,
      `/entities/${ENTITY}/unresolved-transactions`,
    ]);
    expect(requests.every((r) => r.authorization === "Bearer a-token")).toBe(true);

    const [coffee, transfer] = within(table).getAllByRole("row").slice(1);
    expect(coffee?.textContent).toContain("Blue Bottle");
    expect(coffee?.textContent).toContain("2026-03-14");
    // Rounded half-up to the display scale, once, and a negative in parentheses (ADR-0025).
    expect(coffee?.textContent).toContain("(minus 240.00)");
    // A line with no payee is named by its description.
    expect(transfer?.textContent).toContain("Transfer in");
    expect(transfer?.textContent).toContain("1,250.51");
    expect(screen.getByText(/couldn.t categorize 2 transactions/)).toBeTruthy();
    await noViolations(container);
  });

  test("answering happens in Claude, with the question drafted for this company", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    page();
    await screen.findByRole("table");
    // The name comes from the books, so a reload or a notification's link still has it.
    expect(await screen.findByText(COMPANY.name)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue in Claude" }));
    const prompt = unresolvedQuestion(COMPANY.name, ENTITY);
    expect(prompt).toContain(`"${COMPANY.name}" (entity ${ENTITY})`);
    expect(prompt).toContain("couldn't categorize");
    expect(assign).toHaveBeenCalledWith(claudeLink(prompt));
    expect(screen.getByRole("link", { name: "Connect Claude" }).getAttribute("href")).toBe(
      `/app/companies/${ENTITY}/connect`,
    );
  });

  test("without the company's name, the questions still show and the prompt names the entity", async () => {
    answers[`/entities/${ENTITY}`] = {
      status: 403,
      body: { code: "not_authorized", message: "No grant in this entity" },
    };
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    page();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Continue in Claude" }));
    expect(assign).toHaveBeenCalledWith(claudeLink(unresolvedQuestion("", ENTITY)));
    expect(unresolvedQuestion("", ENTITY)).toContain(`entity ${ENTITY}`);
  });

  test("coming back to the tab reads the questions again", async () => {
    let visibility: DocumentVisibilityState = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
    page();
    await screen.findByRole("table");
    const reads = () => requests.filter((r) => r.path.endsWith("/unresolved-transactions")).length;
    expect(reads()).toBe(1);

    // Leaving the tab reads nothing.
    visibility = "hidden";
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(reads()).toBe(1);

    // Answered in Claude meanwhile: nothing is waiting any more.
    answers["/unresolved-transactions"] = { status: 200, body: { unresolved: [] } };
    answers["/notifications"] = { status: 200, body: { notifications: [] } };
    visibility = "visible";
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(await screen.findByText("Nothing waiting")).toBeTruthy();
    expect(reads()).toBe(2);
    expect(screen.queryByRole("table")).toBeNull();
  });

  test("a failed re-read keeps what was shown", async () => {
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => "visible");
    page();
    await screen.findByRole("table");
    answers["/unresolved-transactions"] = {
      status: 503,
      body: { code: "unavailable", message: "Try later" },
    };
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() =>
      expect(requests.filter((r) => r.path.endsWith("/unresolved-transactions"))).toHaveLength(2),
    );
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.queryByText("Couldn't read your questions")).toBeNull();
  });

  test("a line with a notification can be dismissed, with an idempotency key", async () => {
    page();
    const table = await screen.findByRole("table");
    const [, transfer] = within(table).getAllByRole("row").slice(1);
    // Only the line a notification is about offers to dismiss one.
    expect(within(transfer as HTMLElement).queryByRole("button")).toBeNull();

    fireEvent.click(
      within(table).getByRole("button", { name: /Dismiss the notification about Blue Bottle/ }),
    );
    await waitFor(() => expect(within(table).queryByRole("button")).toBeNull());
    const dismissal = requests.find((r) => r.method === "POST");
    expect(dismissal?.path).toBe(`/entities/${ENTITY}/notifications/n-1/dismissal`);
    expect(dismissal?.idempotencyKey).toBe(dismissalKey("n-1"));
    expect(dismissal?.authorization).toBe("Bearer a-token");
    // The line itself stays: dismissing answers nothing.
    expect(within(table).getByText("Blue Bottle")).toBeTruthy();
  });

  test("a refused dismissal says so, and the line keeps its notification", async () => {
    answers["/dismissal"] = {
      status: 403,
      body: { code: "not_a_person", message: "Only a person can dismiss this" },
    };
    page();
    const table = await screen.findByRole("table");
    fireEvent.click(within(table).getByRole("button", { name: /Dismiss the notification/ }));
    expect(await screen.findByText("Not dismissed")).toBeTruthy();
    expect(screen.getByText(/Only a person can dismiss this/)).toBeTruthy();
    expect(within(table).getByRole("button", { name: /Dismiss the notification/ })).toBeTruthy();
  });

  test("with nothing waiting, it says so", async () => {
    answers["/unresolved-transactions"] = { status: 200, body: { unresolved: [] } };
    answers["/notifications"] = { status: 200, body: { notifications: [] } };
    const { container } = page();
    expect(await screen.findByText("Nothing waiting")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    await noViolations(container);
  });

  test("a refused read says what went wrong", async () => {
    answers["/unresolved-transactions"] = {
      status: 403,
      body: { code: "forbidden", message: "No grant in this entity" },
    };
    page();
    expect(await screen.findByText("Couldn't read your questions")).toBeTruthy();
    expect(screen.getByText(/No grant in this entity/)).toBeTruthy();
  });
});
