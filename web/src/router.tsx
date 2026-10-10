import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { SignedIn } from "./auth/SignedIn";
import { SignInReturn } from "./auth/SignInReturn";
import { QuestionsPage } from "./questions/QuestionsPage";
import { SettingsPage } from "./settings/SettingsPage";
import { ConnectPage } from "./start/ConnectPage";
import { FirstQuestion } from "./start/FirstQuestion";
import { GettingStarted } from "./start/GettingStarted";
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

// Getting started (ADR-0058): the export and the company it describes, then the import into that
// company, connecting Claude, and the first question.
const start = createRoute({
  getParentRoute: () => root,
  path: "/",
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

// The issuer sends the person back here with a code; the sign-in provider exchanges it and
// returns them to the page they started from. If the exchange fails, this page says so.
const signedIn = createRoute({
  getParentRoute: () => root,
  path: "/signed-in",
  component: SignInReturn,
});

export const router = createRouter({
  routeTree: root.addChildren([start, importing, connect, ask, questions, settings, signedIn]),
  basepath: "/app",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
