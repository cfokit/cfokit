import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StartedProvider } from "../start/state";
import { AGENT, ChatPage, refusalOf, thread } from "./ChatPage";

// The chat page, with the API and the agent stood in for. What they return here is a stand-in;
// what is asserted is what the page asks for, where it sends the person, and what it shows.

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));
vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "a-token", profile: { name: "Dana Whitfield" } },
    settings: { authority: "https://issuer.test/realms/cfokit" },
    signoutRedirect: vi.fn(),
  }),
}));

const ENTITY = "e-1";
const CONVERSATION = "c-1";
const AGENT_URL = "https://agent.test";

// AG-UI's message model for one turn: the question, a call and its result, then the answer.
const HISTORY = [
  { id: "m-1", role: "user", content: "How did we do last quarter?" },
  {
    id: "m-2",
    role: "assistant",
    toolCalls: [
      { id: "call-1", type: "function", function: { name: "profit_and_loss", arguments: "{}" } },
    ],
  },
  { id: "m-3", role: "tool", toolCallId: "call-1", content: "Revenue 48200.00" },
  { id: "m-4", role: "assistant", content: "Revenue was **48,200.00**." },
];

type Answer = { status: number; body: unknown };
let answers: Record<string, Answer>;
let requests: { url: string; method: string; idempotencyKey: string | null; auth: string | null }[];

beforeEach(() => {
  navigate.mockReset();
  requests = [];
  answers = {
    "/connection": { status: 200, body: { mcp_url: null, agent_url: AGENT_URL } },
    [`/entities/${ENTITY}`]: { status: 200, body: { name: "Northwind" } },
    [`/entities/${ENTITY}/conversations`]: { status: 200, body: { conversations: [] } },
    [`${AGENT_URL}/entities/${ENTITY}/conversations/${CONVERSATION}`]: {
      status: 200,
      body: { messages: HISTORY },
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      const method = init?.method ?? "GET";
      requests.push({
        url,
        method,
        idempotencyKey: headers.get("idempotency-key"),
        auth: headers.get("authorization"),
      });
      // A turn that is still answering: the run stays in progress.
      if (method === "POST" && url.endsWith("/turn")) return new Promise<Response>(() => {});
      const answer =
        method === "POST" && url.endsWith("/conversations")
          ? { status: 201, body: { conversation_id: "c-new", replayed: false } }
          : (answers[url] ?? { status: 404, body: { code: "not_found" } });
      return Promise.resolve(new Response(JSON.stringify(answer.body), { status: answer.status }));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function page(conversationId?: string, draft?: string) {
  return render(
    <StartedProvider>
      <ChatPage entityId={ENTITY} conversationId={conversationId} draft={draft} />
    </StartedProvider>,
  );
}

test("the agent's history becomes a thread, each message after the one before it", () => {
  const entries = thread(HISTORY as never);
  expect(entries[0]?.parentId).toBeNull();
  for (let i = 1; i < entries.length; i += 1) {
    expect(entries[i]?.parentId).toBe(entries[i - 1]?.message.id);
  }
  expect(entries.map((e) => e.message.role)).toContain("user");
});

test("a refusal is known by its stable code (ADR-0015)", () => {
  expect(refusalOf({ payload: { code: "agent_not_allowed", message: "Allow it" } })).toEqual({
    code: "agent_not_allowed",
    message: "Allow it",
  });
  expect(refusalOf(new Error("network down")).code).toBe("unexpected");
});

test("with no conversation named, it starts one and puts it in the address", async () => {
  page();
  await waitFor(() => expect(navigate).toHaveBeenCalled());
  const started = requests.find((r) => r.method === "POST");
  expect(started?.url).toBe(`/entities/${ENTITY}/conversations`);
  expect(started?.idempotencyKey).toBeTruthy();
  expect(navigate).toHaveBeenCalledWith({
    to: "/companies/$entityId/chat/$conversationId",
    params: { entityId: ENTITY, conversationId: "c-new" },
    search: {},
    replace: true,
  });
});

test("it opens the person's newest conversation rather than starting another", async () => {
  answers[`/entities/${ENTITY}/conversations`] = {
    status: 200,
    body: { conversations: [{ conversation_id: "c-newest" }, { conversation_id: "c-older" }] },
  };
  page();
  await waitFor(() => expect(navigate).toHaveBeenCalled());
  expect(requests.some((r) => r.method === "POST")).toBe(false);
  expect(navigate.mock.calls[0]?.[0].params.conversationId).toBe("c-newest");
});

test("it shows the conversation so far, read from the agent with the person's token", async () => {
  page(CONVERSATION);
  expect(await screen.findByText("How did we do last quarter?")).toBeTruthy();
  expect(await screen.findByText("Read profit and loss")).toBeTruthy();
  const read = requests.find((r) => r.url.startsWith(AGENT_URL));
  expect(read?.auth).toBe("Bearer a-token");
});

test("an agent not yet allowed in the company sends the person to allow it", async () => {
  answers[`${AGENT_URL}/entities/${ENTITY}/conversations/${CONVERSATION}`] = {
    status: 403,
    body: { code: "agent_not_allowed", message: "Allow this agent" },
  };
  page(CONVERSATION);
  (await screen.findByRole("button", { name: "Allow CFOKit" })).click();
  expect(navigate).toHaveBeenCalledWith({ to: "/agents/$agent", params: { agent: AGENT } });
});

test("a deployment running no agent says so instead of offering a chat", async () => {
  answers["/connection"] = { status: 200, body: { mcp_url: null, agent_url: null } };
  page(CONVERSATION);
  expect(await screen.findByText("No chat here")).toBeTruthy();
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("a refusal clears when the person tries again", async () => {
  answers[`${AGENT_URL}/entities/${ENTITY}/conversations/${CONVERSATION}`] = {
    status: 403,
    body: { code: "agent_not_allowed", message: "Allow this agent" },
  };
  page(CONVERSATION);
  expect(await screen.findByText("Not allowed yet")).toBeTruthy();

  fireEvent.change(screen.getByRole("textbox", { name: "Ask about your books" }), {
    target: { value: "How did we do?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  await waitFor(() => expect(screen.queryByText("Not allowed yet")).toBeNull());
  expect(requests.some((r) => r.method === "POST" && r.url.endsWith("/turn"))).toBe(true);
});

test("a question handed over is carried to the conversation and waits, unsent, to be sent", async () => {
  page(undefined, "How did we do?");
  await waitFor(() => expect(navigate).toHaveBeenCalled());
  expect(navigate.mock.calls[0]?.[0].search).toEqual({ draft: "How did we do?" });

  page(CONVERSATION, "How did we do?");
  const composer = await screen.findByRole("textbox", { name: "Ask about your books" });
  await waitFor(() => expect((composer as HTMLTextAreaElement).value).toBe("How did we do?"));
  expect(requests.some((r) => r.url.endsWith("/turn"))).toBe(false);
});
