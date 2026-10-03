import { useAuth } from "react-oidc-context";
import { AppFrame, Card } from "./components";

/** Who is signed in, from the ID token the issuer returned: a name, else the address. */
export function personName(profile: { name?: string; email?: string } | undefined): string {
  return profile?.name ?? profile?.email ?? "";
}

/** The signed-in start of the client. Onboarding begins here. */
export function Home() {
  const auth = useAuth();
  return (
    <AppFrame
      company=""
      person={personName(auth.user?.profile)}
      onSignOut={() => void auth.signoutRedirect()}
    >
      <div className="flex max-w-reading-max flex-col gap-6">
        <h1 className="font-display text-display-compact text-ink tablet:text-display">
          You&apos;re signed in
        </h1>
        <Card title="Next: your company">
          <p className="text-body text-ink">
            Creating your company and importing its books from QuickBooks come next.
          </p>
        </Card>
      </div>
    </AppFrame>
  );
}
