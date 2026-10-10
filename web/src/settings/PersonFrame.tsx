import type { ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "react-oidc-context";
import { AppFrame } from "../components";

/** Who is signed in, from the ID token the issuer returned: a name, else the address. */
export function personName(profile: { name?: string; email?: string } | undefined): string {
  return profile?.name ?? profile?.email ?? "";
}

/**
 * The app frame for the signed-in person: their name, "Settings" and "Sign out". Settings opens
 * within the app, because a page load would drop the sign-in, which lives in page memory only
 * (ADR-0049 § 2).
 */
export function PersonFrame({ company, children }: { company: string; children: ReactNode }) {
  const auth = useAuth();
  const navigate = useNavigate();
  return (
    <AppFrame
      company={company}
      person={personName(auth.user?.profile)}
      onSignOut={() => void auth.signoutRedirect()}
      onSettings={() => void navigate({ to: "/settings" })}
    >
      {children}
    </AppFrame>
  );
}
