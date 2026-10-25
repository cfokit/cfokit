import { lazy, Suspense } from "react";
import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import { AgentPage } from "./agents/AgentPage";
import { SignedIn } from "./auth/SignedIn";
import { SignInReturn } from "./auth/SignInReturn";
import { QuestionsPage } from "./questions/QuestionsPage";
import { SettingsPage } from "./settings/SettingsPage";
import { ConnectPage } from "./start/ConnectPage";
import { FirstQuestion } from "./start/FirstQuestion";
import { GettingStarted } from "./start/GettingStarted";
import { Home } from "./start/Home";
import { ImportPage } from "./start/ImportPage";
import { StartedProvider } from "./start/state";

// Where the operator is lives in the URL, so a reload or a link lands on the same page
// (ADR-0049 § 2). The client is served at /app/ (ADR-0049 § 5).

const root = createRootRoute({
  component: () => (
    <StartedProvider>
      <Outlet />
    </StartedProvider>
  ),
});

// Where a signed-in person lands: a company's chat, or getting started when there is none to open.
const home = createRoute({
  getParentRoute: () => root,
  path: "/",
  component: () => (
    <SignedIn>
      <Home />
    </SignedIn>
  ),
});

// Getting started (ADR-0058): the export and the company it describes, then the import into that
// company, connecting Claude, and the first question. Here, for one more company, as Settings'
// "Add a company" opens it.
const start = createRoute({
  getParentRoute: () => root,
  path: "/start",
  component: () => (
    <SignedIn>
      <GettingStarted />
    </SignedIn>
  ),
});

const importing = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId/import",
  component: function Importing() {
    const { entityId } = importing.useParams();
    return (
      <SignedIn>
        <ImportPage entityId={entityId} />
      </SignedIn>
    );
  },
});

const connect = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId/connect",
  component: function Connect() {
    const { entityId } = connect.useParams();
    return (
      <SignedIn>
        <ConnectPage entityId={entityId} />
      </SignedIn>
    );
  },
});

const ask = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId/ask",
  component: function Ask() {
    const { entityId } = ask.useParams();
    return (
      <SignedIn>
        <FirstQuestion entityId={entityId} />
      </SignedIn>
    );
  },
});

// What CFOKit is asking the person about this company. Every `unresolved_transaction`
// notification links here, so the path is part of what the server stores.
const questions = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId/questions",
  component: function Questions() {
    const { entityId } = questions.useParams();
    return (
      <SignedIn>
        <QuestionsPage entityId={entityId} />
      </SignedIn>
    );
  },
});

// The person's settings: their companies, and connecting Claude, whenever they need it again.
const settings = createRoute({
  getParentRoute: () => root,
  path: "/settings",
  component: () => (
    <SignedIn>
      <SettingsPage />
    </SignedIn>
  ),
});

// The chat and the libraries it is built on load only when it is opened, so no other page waits
// for them.
const ChatPage = lazy(() => import("./chat/ChatPage").then((m) => ({ default: m.ChatPage })));

// The chat with CFOKit's agent in a company (ADR-0075). Without a conversation named, the page opens
// the person's newest or starts one, and replaces the address with that conversation's.
// A question another page hands to the chat, left in the composer for the person to send.
function withDraft(search: Record<string, unknown>): { draft?: string } {
  return typeof search.draft === "string" ? { draft: search.draft } : {};
}

const chat = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId/chat",
  validateSearch: withDraft,
  component: function Chat() {
    const { entityId } = chat.useParams();
    const { draft } = chat.useSearch();
    return (
      <SignedIn>
        <Suspense>
          <ChatPage entityId={entityId} draft={draft} />
        </Suspense>
      </SignedIn>
    );
  },
});

const conversation = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId/chat/$conversationId",
  validateSearch: withDraft,
  component: function Conversation() {
    const { entityId, conversationId } = conversation.useParams();
    const { draft } = conversation.useSearch();
    return (
      <SignedIn>
        <Suspense>
          <ChatPage entityId={entityId} conversationId={conversationId} draft={draft} />
        </Suspense>
      </SignedIn>
    );
  },
});

// A company's home in the web client is its chat (ADR-0068 § 3).
const company = createRoute({
  getParentRoute: () => root,
  path: "/companies/$entityId",
  beforeLoad: ({ params }) => {
    throw redirect({ to: "/companies/$entityId/chat", params, replace: true });
  },
});

// Allowing an agent in the person's companies (ADR-0066 § 2). Every `agent_not_allowed` refusal
// links here, so the path is part of what the server says.
const agents = createRoute({
  getParentRoute: () => root,
  path: "/agents/$agent",
  validateSearch: withDraft,
  component: function Agents() {
    const { agent } = agents.useParams();
    const { draft } = agents.useSearch();
    return (
      <SignedIn>
        <AgentPage agent={agent} draft={draft} />
      </SignedIn>
    );
  },
});

// The issuer sends the person back here with a code; the sign-in provider exchanges it and
// returns them to the page they started from. If the exchange fails, this page says so.
const signedIn = createRoute({
  getParentRoute: () => root,
  path: "/signed-in",
  component: SignInReturn,
});

export const router = createRouter({
  routeTree: root.addChildren([
    home,
    start,
    company,
    importing,
    connect,
    ask,
    questions,
    chat,
    conversation,
    settings,
    agents,
    signedIn,
  ]),
  basepath: "/app",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
