import { InMemoryWebStorage, WebStorageStateStore, type UserManagerSettings } from "oidc-client-ts";

// The web client's own client in the bundled realm (infra/keycloak/cfokit-realm.json): public,
// authorization code with PKCE and nothing else (ADR-0049 § 1).
export const CLIENT_ID = "cfokit-web";

/**
 * Where to sign in. The REST service says which issuer guards it (RFC 9728), on the same origin
 * the page is served from, so the client is never configured with a second address (ADR-0004).
 */
export async function discoverIssuer(fetcher: typeof fetch = fetch): Promise<string> {
  const response = await fetcher("/.well-known/oauth-protected-resource");
  if (!response.ok) throw new Error(`protected-resource metadata: HTTP ${response.status}`);
  const metadata = (await response.json()) as { authorization_servers?: string[] };
  const issuer = metadata.authorization_servers?.[0];
  if (issuer === undefined) throw new Error("protected-resource metadata names no issuer");
  return issuer;
}

/**
 * The sign-in settings, as ADR-0049 § 2 holds them. The tokens live in page memory and nowhere
 * else; only the PKCE verifier and `state` survive the round trip to the issuer, in
 * sessionStorage, which is oidc-client-ts's default for them. No renewal in a hidden iframe and no
 * session-monitoring iframe: Safari and Firefox block the issuer's cookie there, so a refresh
 * token renews instead.
 */
export function oidcSettings(issuer: string, origin: string): UserManagerSettings {
  return {
    authority: issuer,
    client_id: CLIENT_ID,
    redirect_uri: `${origin}/app/signed-in`,
    post_logout_redirect_uri: `${origin}/app/`,
    response_type: "code",
    scope: "openid profile email",
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    automaticSilentRenew: true,
    monitorSession: false,
  };
}
