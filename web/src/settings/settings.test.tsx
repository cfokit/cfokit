import { fireEvent, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { declared, SettingsPage, type Company } from "./SettingsPage";

// The settings page, with the API and the router stood in for. What the API returns is a
// stand-in; what is asserted is what the page shows of it and where its actions go.

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));
vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "a-token", profile: { name: "Dana Whitfield" } },
    settings: { authority: "https://issuer.test/realms/cfokit" },
    signoutRedirect: vi.fn(),
  }),
}));

const ACME: Company = {
  id: "e-1",
  slug: "acme",
  name: "Acme LLC",
  accounting_basis: "accrual",
  fiscal_year_end_month: 12,
  fiscal_year_end_day: 31,
  functional_currency: "USD",
  time_zone: "America/New_York",
};

const HARBOR: Company = {
  ...ACME,
  id: "e-2",
  slug: "harbor",
  name: "Harbor Lights LLC",
  accounting_basis: "cash",
  fiscal_year_end_month: 6,
  fiscal_year_end_day: 30,
};

let answers: Record<string, unknown>;

beforeEach(() => {
  navigate.mockReset();
  answers = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      const key = Object.keys(answers).find((suffix) => path.endsWith(suffix));
      return Promise.resolve(
        new Response(JSON.stringify(key === undefined ? {} : answers[key]), { status: 200 }),
      );
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

async function noViolations(container: HTMLElement) {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
}

test("what a company declared reads as the person would say it", () => {
  expect(declared(ACME)).toBe("Accrual basis · year ends December 31 · USD · America/New_York");
  expect(declared(HARBOR)).toBe("Cash basis · year ends June 30 · USD · America/New_York");
});

test("settings lists every company the person holds, and how to connect Claude", async () => {
  answers["/entities"] = { entities: [ACME, HARBOR] };
  answers["/connection"] = { mcp_url: "https://mcp.example.test/mcp" };
  const { container } = render(<SettingsPage />);

  const list = await screen.findByRole("list", { name: "Companies" });
  expect(
    within(list)
      .getAllByRole("listitem")
      .map((item) => item.firstChild?.firstChild?.textContent),
  ).toEqual(["Acme LLC", "Harbor Lights LLC"]);
  await screen.findByRole("figure", { name: "Connector address" });
  await noViolations(container);
});

test("a company's questions, and adding a company, are a click away", async () => {
  answers["/entities"] = { entities: [ACME, HARBOR] };
  render(<SettingsPage />);
  const list = await screen.findByRole("list", { name: "Companies" });

  const harbor = within(list).getAllByRole("listitem")[1];
  if (harbor === undefined) throw new Error("no second company");
  fireEvent.click(within(harbor).getByRole("button", { name: "Questions" }));
  expect(navigate).toHaveBeenCalledWith({
    to: "/companies/$entityId/questions",
    params: { entityId: "e-2" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Add a company" }));
  expect(navigate).toHaveBeenCalledWith({ to: "/" });
});

test("a person holding no books is told so, and can add a company", async () => {
  answers["/entities"] = { entities: [] };
  render(<SettingsPage />);
  await screen.findByText("You do not hold the books of any company yet.");
  expect(screen.getByRole("button", { name: "Add a company" })).toBeTruthy();
});

test("the frame opens settings within the app", async () => {
  answers["/entities"] = { entities: [] };
  render(<SettingsPage />);
  const [settings] = await screen.findAllByRole("button", { name: "Settings" });
  if (settings === undefined) throw new Error("no Settings in the frame");
  fireEvent.click(settings);
  expect(navigate).toHaveBeenCalledWith({ to: "/settings" });
});
