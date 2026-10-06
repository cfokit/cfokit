import { useAuth } from "react-oidc-context";
import { Button, Notice } from "../components";

/**
 * Where the issuer sends a person back with a code. The sign-in provider exchanges it and then
 * returns them to the page they started from, so this page is seen only for a moment — or when the
 * exchange fails, which it must then say. A code is single-use and belongs to the tab that asked
 * for it, so an old tab, a reload or a second tab all end here; a blank page there is a dead end.
 */
export function SignInReturn() {
  const auth = useAuth();

  if (auth.error) {
    return (
      <main className="mx-auto flex max-w-reading-max flex-col gap-4 p-6">
        <Notice tone="danger" label="That sign-in didn't finish" announce>
          The link back from signing in had expired or was opened in another tab. Signing in again
          takes you straight back.
        </Notice>
        <div>
          <Button
            variant="primary"
            onClick={() => {
              // To the client's root, not the page they started from: that was stored with the
              // sign-in that failed, and is gone with it.
              window.history.replaceState(null, "", "/app/");
              void auth.signinRedirect({ state: "/app/" });
            }}
          >
            Sign in again
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-reading-max p-6">
      <p role="status" className="text-body text-ink-muted">
        Signing you in…
      </p>
    </main>
  );
}
