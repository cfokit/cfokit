import { discoverIssuer, oidcSettings } from "./settings";

const ISSUER = "https://keycloak.localhost:8443/realms/cfokit";

test("the issuer is the one the API names for itself (RFC 9728)", async () => {
  const fetcher = vi.fn(
    async () => new Response(JSON.stringify({ authorization_servers: [ISSUER] })),
  ) as unknown as typeof fetch;
  await expect(discoverIssuer(fetcher)).resolves.toBe(ISSUER);
  expect(fetcher).toHaveBeenCalledWith("/.well-known/oauth-protected-resource");
});

test("metadata that names no issuer is an error, not a guess", async () => {
  const fetcher = (async () => new Response("{}")) as unknown as typeof fetch;
  await expect(discoverIssuer(fetcher)).rejects.toThrow("names no issuer");
});

describe("the sign-in settings ADR-0049 § 2 requires", () => {
  const settings = oidcSettings(ISSUER, "https://localhost:8080");

  test("authorization code, as the realm's public cfokit-web client", () => {
    expect(settings.client_id).toBe("cfokit-web");
    expect(settings.response_type).toBe("code");
    expect(settings.authority).toBe(ISSUER);
  });

  test("it returns to the client's own path on its own origin", () => {
    expect(settings.redirect_uri).toBe("https://localhost:8080/app/signed-in");
    expect(settings.post_logout_redirect_uri).toBe("https://localhost:8080/app/");
  });

  test("tokens are kept in page memory, not in browser storage", async () => {
    const store = settings.userStore;
    if (store === undefined) throw new Error("no user store");
    await store.set("user:cfokit-web", "a signed-in user");
    await expect(store.get("user:cfokit-web")).resolves.toBe("a signed-in user");
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  test("nothing runs in a hidden iframe", () => {
    expect(settings.monitorSession).toBe(false);
    expect(settings.silent_redirect_uri).toBeUndefined();
  });
});
