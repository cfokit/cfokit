import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { ConnectClaude, onThisComputer } from "./ConnectClaude";

// Connecting Claude, with the API and the issuer stood in for. What they return is a stand-in;
// what is asserted is what the page asks for, and which instructions it gives for the address.

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "a-token", profile: { name: "Dana Whitfield" } },
    settings: { authority: "https://issuer.test/realms/cfokit" },
  }),
}));

let requests: { path: string; authorization: string | null }[];
let answers: Record<string, unknown>;

beforeEach(() => {
  requests = [];
  answers = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      requests.push({ path, authorization: new Headers(init?.headers).get("authorization") });
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

test("an address on this computer is one a custom connector cannot reach", () => {
  expect(onThisComputer("https://localhost:8081/mcp")).toBe(true);
  expect(onThisComputer("https://127.0.0.1:8081/mcp")).toBe(true);
  expect(onThisComputer("https://[::1]:8081/mcp")).toBe(true);
  expect(onThisComputer("https://mcp.localhost/mcp")).toBe(true);
  expect(onThisComputer("https://mcp.cfokit.ai/mcp")).toBe(false);
  expect(onThisComputer("https://localhost.example.com/mcp")).toBe(false);
});

test("a CFOKit others can reach is added to Claude as a custom connector", async () => {
  answers["/connection"] = { mcp_url: "https://mcp.example.test/mcp" };
  const { container } = render(<ConnectClaude />);
  const address = await screen.findByRole("figure", { name: "Connector address" });
  expect(address.querySelector("pre")?.textContent).toBe("https://mcp.example.test/mcp");
  expect(requests.find((request) => request.path === "/connection")?.authorization).toBe(
    "Bearer a-token",
  );
  expect(screen.queryByRole("figure", { name: "Configuration" })).toBeNull();
  expect(requests.some((request) => request.path.includes("openid-configuration"))).toBe(false);
  await noViolations(container);
});

test("a CFOKit on this computer registers a client where the issuer's metadata says", async () => {
  answers["/connection"] = { mcp_url: "https://localhost:8081/mcp" };
  answers["/.well-known/openid-configuration"] = {
    registration_endpoint: "https://issuer.test/realms/cfokit/register-here",
  };
  const { container } = render(<ConnectClaude />);
  await screen.findByText(/register-here/);
  expect(requests.map((request) => request.path)).toContain(
    "https://issuer.test/realms/cfokit/.well-known/openid-configuration",
  );
  const configuration = await screen.findByRole("figure", { name: "Configuration" });
  expect(configuration.textContent).toContain('"https://localhost:8081/mcp"');
  await noViolations(container);
});

test("the local configuration sends the secret the way the client is registered to", async () => {
  answers["/connection"] = { mcp_url: "https://localhost:8081/mcp" };
  answers["/.well-known/openid-configuration"] = {
    registration_endpoint: "https://issuer.test/realms/cfokit/register-here",
  };
  render(<ConnectClaude />);
  const registration = (await screen.findByText(/register-here/)).closest("figure");
  const configuration = await screen.findByRole("figure", { name: "Configuration" });
  const method = /"token_endpoint_auth_method":\s*"(\w+)"/;
  const registered = method.exec(registration?.querySelector("pre")?.textContent ?? "")?.[1];
  expect(registered).toBe("client_secret_post");
  const config = JSON.parse(configuration.querySelector("pre")?.textContent ?? "") as {
    mcpServers: { cfokit: { args: string[] } };
  };
  expect(method.exec(config.mcpServers.cfokit.args.at(-1) ?? "")?.[1]).toBe(registered);
});

test("a deployment that does not say where Claude connects is told so, not guessed", async () => {
  answers["/connection"] = { mcp_url: null };
  const { container } = render(<ConnectClaude />);
  await screen.findByText(/MCP_PUBLIC_BASE_URL/);
  expect(screen.queryByRole("figure", { name: "Configuration" })).toBeNull();
  expect(screen.queryByRole("figure", { name: "Connector address" })).toBeNull();
  await noViolations(container);
});
