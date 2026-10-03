import { useEffect, type ReactNode } from "react";
import { useAuth } from "react-oidc-context";
import { Notice } from "../components";

/**
 * Its children only for a signed-in person. Anyone else is sent to the issuer to sign in or create
 * an account, and comes back to the page they asked for.
 */
export function SignedIn({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const mustSignIn =
    !auth.isLoading && !auth.isAuthenticated && !auth.activeNavigator && !auth.error;

  useEffect(() => {
    if (mustSignIn) {
      void auth.signinRedirect({ state: window.location.pathname + window.location.search });
    }
  }, [mustSignIn, auth]);

  if (auth.error) {
    return (
      <Notice tone="danger" label="Couldn't sign you in" announce>
        {auth.error.message}. Reload the page to try again.
      </Notice>
    );
  }
  if (!auth.isAuthenticated) return null;
  return <>{children}</>;
}
