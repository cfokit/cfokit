import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import type { Company } from "../settings/SettingsPage";
import { AgentPage, type Grant } from "./AgentPage";
import { agentName, describeAgent, type AgentConnection } from "./name";

// The allow page (ADR-0066 § 2), with the API stood in for. Asserted: what the page shows of
// each company's standing, and what allowing and revoking send.

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "a-token", profile: { name: "Dana Whitfield" } },
    settings: { authority: "https://issuer.test/realms/cfokit" },
    signoutRedirect: vi.fn(),
  }),
}));
const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));

const AGENT = "client:claude-abc";

function company(id: string, name: string): Company {
  return {
    id,
    slug: id,
    name,
    accounting_basis: "accrual",
    fiscal_year_end_month: 12,
    fiscal_year_end_day: 31,
    functional_currency: "USD",
    time_zone: "UTC",
  };
}

function grant(principal: string, role: string, id = "g-1"): Grant {
  return {
    grant_id: id,
    principal_id: principal,
    role,
    granted_by: "user:dana",
    granted_at: "2026-10-11T00:00:00Z",
    lapses_at: null,
  };
}

type Reply = { status: number; body?: unknown };
let replies: Record<string, Reply>;
let sent: { method: string; path: string; body: unknown }[];

beforeEach(() => {
  sent = [];
  replies = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      sent.push({
        method,
        path,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      });
      const reply = replies[`${method} ${path}`] ?? { status: 200, body: {} };
      return Promise.resolve(
        new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
          status: reply.status,
        }),
      );
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

const CONNECTED: AgentConnection = {
  agent_id: AGENT,
  client_name: "claude-ai",
  client_version: "0.1.0",
  person_email: "dana@example.test",
  person_name: "Dana Whitfield",
  first_connected_at: "2026-10-12T15:00:00Z",
  last_connected_at: "2026-10-13T15:00:00Z",
};

test("an agent is named by the client it signed in through", () => {
  expect(agentName(AGENT)).toBe("Client claude-abc");
});

test("an agent that connected is named by what it reported, and by its ID otherwise", () => {
  expect(describeAgent(AGENT, CONNECTED)).toBe("claude-ai 0.1.0");
  expect(describeAgent(AGENT, { ...CONNECTED, client_version: null })).toBe("claude-ai");
  expect(describeAgent(AGENT, { ...CONNECTED, client_name: null })).toBe("Client claude-abc");
  expect(describeAgent(AGENT, undefined)).toBe("Client claude-abc");
});

test("the page says what the agent reported, the account it signed in as, and its client ID", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [] } };
  replies["GET /agents"] = { status: 200, body: { agents: [CONNECTED] } };
  render(<AgentPage agent={AGENT} />);

  await screen.findByText(/^claude-ai 0\.1\.0 is software you signed in to CFOKit through/);
  expect(screen.getByText("Dana Whitfield (dana@example.test)")).toBeTruthy();
  expect(screen.getByText("claude-abc")).toBeTruthy();
});

test("an agent with no recorded connection is shown by its ID, and says so", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [] } };
  replies["GET /agents"] = { status: 200, body: { agents: [] } };
  render(<AgentPage agent={AGENT} />);

  await screen.findByText(/CFOKit has no record of it connecting/);
  expect(screen.getByText(/^Client claude-abc is software you signed in/)).toBeTruthy();
});

test("each company shows where the agent stands, and what the person can do there", async () => {
  replies["GET /entities"] = {
    status: 200,
    body: {
      entities: [company("e-1", "Acme LLC"), company("e-2", "Harbor LLC"), company("e-3", "Coop")],
    },
  };
  replies["GET /entities/e-1/grants"] = {
    status: 200,
    body: { grants: [grant("user:dana", "owner", "g-0"), grant(AGENT, "bookkeeper")] },
  };
  replies["GET /entities/e-2/grants"] = {
    status: 200,
    body: { grants: [grant("user:dana", "owner")] },
  };
  replies["GET /entities/e-3/grants"] = {
    status: 403,
    body: { code: "not_authorized", message: "this principal may not grant in this entity" },
  };
  const { container } = render(<AgentPage agent={AGENT} />);

  const [acme, harbor, coop] = within(
    await screen.findByRole("list", { name: "Companies" }),
  ).getAllByRole("listitem") as [HTMLElement, HTMLElement, HTMLElement];
  await within(acme).findByRole("button", { name: "Remove" });
  await within(harbor).findByRole("button", { name: "Allow to keep the books" });
  await within(coop).findByText(/Only someone who administers this company/);

  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
});

test("allowing grants the agent the chosen role in that company", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-2", "Harbor LLC")] } };
  replies["GET /entities/e-2/grants"] = { status: 200, body: { grants: [] } };
  replies["POST /entities/e-2/grants"] = { status: 201, body: { grant_id: "g-9" } };
  render(<AgentPage agent={AGENT} />);

  fireEvent.click(await screen.findByRole("button", { name: "Allow to read only" }));

  await waitFor(() =>
    expect(sent).toContainEqual({
      method: "POST",
      path: "/entities/e-2/grants",
      body: { principal_id: AGENT, role: "reader" },
    }),
  );
});

test("removing ends that grant and no other", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-1", "Acme LLC")] } };
  replies["GET /entities/e-1/grants"] = {
    status: 200,
    body: {
      grants: [grant("client:someone-else", "reader", "g-7"), grant(AGENT, "reader", "g-8")],
    },
  };
  replies["DELETE /entities/e-1/grants/g-8"] = { status: 204 };
  render(<AgentPage agent={AGENT} />);

  fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

  await waitFor(() =>
    expect(sent.filter((call) => call.method === "DELETE").map((call) => call.path)).toEqual([
      "/entities/e-1/grants/g-8",
    ]),
  );
});

test("an agent holding both roles shows each, removable, and offers neither again", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-1", "Acme LLC")] } };
  replies["GET /entities/e-1/grants"] = {
    status: 200,
    body: { grants: [grant(AGENT, "reader", "g-1"), grant(AGENT, "bookkeeper", "g-2")] },
  };
  replies["DELETE /entities/e-1/grants/g-1"] = { status: 204 };
  const { container } = render(<AgentPage agent={AGENT} />);

  const roles = within(await screen.findByRole("list", { name: "Roles in Acme LLC" }));
  const [reading, keeping] = roles.getAllByRole("listitem") as [HTMLElement, HTMLElement];
  expect(within(reading).getByText(/Reads the books/)).toBeTruthy();
  expect(within(keeping).getByText(/Keeps the books/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /^Also allow/ })).toBeNull();

  fireEvent.click(within(reading).getByRole("button", { name: "Remove" }));
  await waitFor(() =>
    expect(sent.filter((call) => call.method === "DELETE").map((call) => call.path)).toEqual([
      "/entities/e-1/grants/g-1",
    ]),
  );

  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
});

test("an agent holding one role is offered only the other", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-1", "Acme LLC")] } };
  replies["GET /entities/e-1/grants"] = {
    status: 200,
    body: { grants: [grant(AGENT, "reader", "g-1")] },
  };
  render(<AgentPage agent={AGENT} />);

  fireEvent.click(await screen.findByRole("button", { name: "Also allow to keep the books" }));

  expect(screen.queryByRole("button", { name: "Also allow to read only" })).toBeNull();
  await waitFor(() =>
    expect(sent).toContainEqual({
      method: "POST",
      path: "/entities/e-1/grants",
      body: { principal_id: AGENT, role: "bookkeeper" },
    }),
  );
});

test("once allowed, the page says to go back to Claude", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-2", "Harbor LLC")] } };
  replies["GET /entities/e-2/grants"] = { status: 200, body: { grants: [] } };
  replies["POST /entities/e-2/grants"] = { status: 201, body: { grant_id: "g-9" } };
  render(<AgentPage agent={AGENT} />);

  const allowing = await screen.findByRole("button", { name: "Allow to keep the books" });
  replies["GET /entities/e-2/grants"] = {
    status: 200,
    body: { grants: [grant(AGENT, "bookkeeper", "g-9")] },
  };
  fireEvent.click(allowing);

  expect(await screen.findByText(/Go back to Claude and ask again/)).toBeTruthy();
});

test("once CFOKit's own agent is allowed, the page leads back to its chat, with the question", async () => {
  const cfokit = "client:cfokit-agent";
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-2", "Harbor LLC")] } };
  replies["GET /entities/e-2/grants"] = { status: 200, body: { grants: [] } };
  replies["POST /entities/e-2/grants"] = { status: 201, body: { grant_id: "g-9" } };
  render(<AgentPage agent={cfokit} draft="How did we do?" />);

  const allowing = await screen.findByRole("button", { name: "Allow to keep the books" });
  replies["GET /entities/e-2/grants"] = {
    status: 200,
    body: { grants: [grant(cfokit, "bookkeeper", "g-9")] },
  };
  fireEvent.click(allowing);

  fireEvent.click(await screen.findByRole("button", { name: "Ask CFOKit" }));
  expect(screen.queryByText(/Go back to Claude/)).toBeNull();
  expect(navigate).toHaveBeenCalledWith({
    to: "/companies/$entityId/chat",
    params: { entityId: "e-2" },
    search: { draft: "How did we do?" },
  });
});

test("the page leads back to Settings", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [] } };
  render(<AgentPage agent={AGENT} />);

  fireEvent.click(await screen.findByRole("button", { name: "← Back to Settings" }));

  expect(navigate).toHaveBeenCalledWith({ to: "/settings" });
});

test("an agent a member connected is shown with their account, read from the company", async () => {
  replies["GET /entities"] = { status: 200, body: { entities: [company("e-1", "Acme LLC")] } };
  replies["GET /entities/e-1/grants"] = { status: 200, body: { grants: [grant(AGENT, "reader")] } };
  replies["GET /agents"] = { status: 200, body: { agents: [] } };
  replies["GET /entities/e-1/agents"] = {
    status: 200,
    body: {
      agents: [{ ...CONNECTED, person_name: "Sam Ortiz", person_email: "sam@example.test" }],
    },
  };
  render(<AgentPage agent={AGENT} />);

  await screen.findByText("Sam Ortiz (sam@example.test)");
});
