import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { UserManager, type User } from "oidc-client-ts";
import { AuthProvider } from "react-oidc-context";
import { discoverIssuer, oidcSettings } from "./auth/settings";
import { Notice } from "./components";
import { router } from "./router";
import "./index.css";

const element = document.getElementById("root");
if (element === null) throw new Error("index.html has no #root element");
const root = createRoot(element);

// Back from the issuer: the code is exchanged, then the person returns to where they started,
// without the code and state left in the address bar or the history.
function returnFromSignIn(user: User | undefined) {
  const to =
    typeof user?.state === "string" && user.state.startsWith("/app") ? user.state : "/app/";
  window.history.replaceState(null, "", to);
  void router.navigate({ to: to.replace(/^\/app/, "") || "/", replace: true });
}

function startClient() {
  discoverIssuer()
    .then((issuer) => {
      const userManager = new UserManager(oidcSettings(issuer, window.location.origin));
      root.render(
        <StrictMode>
          <AuthProvider userManager={userManager} onSigninCallback={returnFromSignIn}>
            <RouterProvider router={router} />
          </AuthProvider>
        </StrictMode>,
      );
    })
    .catch(() => {
      root.render(
        <main className="mx-auto max-w-reading-max p-6">
          <Notice tone="danger" label="Can't reach CFOKit" announce>
            The page loaded, but CFOKit isn&apos;t answering. Reload to try again.
          </Notice>
        </main>,
      );
    });
}

// The same build is the issuer's sign-in theme (ADR-0054 § 1): on the issuer's pages, Keycloak
// supplies window.kcContext and the page it names is drawn instead of the client.
const KcPage = lazy(() => import("./login/KcPage"));

if (window.kcContext === undefined) {
  startClient();
} else {
  root.render(
    <StrictMode>
      <Suspense>
        <KcPage kcContext={window.kcContext} />
      </Suspense>
    </StrictMode>,
  );
}
