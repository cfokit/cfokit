import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { SignedIn } from "./auth/SignedIn";
import { Home } from "./Home";

// Where the operator is lives in the URL, so a reload or a link lands on the same page
// (ADR-0049 § 2). The client is served at /app/ (ADR-0049 § 5).

const root = createRootRoute({ component: Outlet });

const home = createRoute({
  getParentRoute: () => root,
  path: "/",
  component: () => (
    <SignedIn>
      <Home />
    </SignedIn>
  ),
});

// The issuer sends the person back here with a code; the sign-in provider exchanges it and
// returns them to the page they started from. Nothing to show meanwhile.
const signedIn = createRoute({
  getParentRoute: () => root,
  path: "/signed-in",
  component: () => null,
});

export const router = createRouter({
  routeTree: root.addChildren([home, signedIn]),
  basepath: "/app",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
