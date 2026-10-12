import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useApi } from "../api";
import { Card, CopyBlock, Notice } from "../components";

// The port mcp-remote listens on for the sign-in's return, fixed so the client is registered once.
const CALLBACK_PORT = 44196;

/** The hosted service's MCP address, which a person adds to Claude as a custom connector. */
export const HOSTED_MCP_URL = "https://mcp.cfokit.ai/mcp";

/** Where Claude finds the plugin: this repository, as a marketplace. */
const MARKETPLACE = "cfokit/cfokit";

/**
 * Where the issuer registers clients (RFC 7591), from its published metadata — never a path that
 * belongs to one issuer (ADR-0019).
 */
function useRegistrationEndpoint(): string | null {
  const authority = useAuth().settings.authority;
  const [endpoint, setEndpoint] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    fetch(`${authority.replace(/\/+$/, "")}/.well-known/openid-configuration`)
      .then((response) => response.json() as Promise<{ registration_endpoint?: string }>)
      .then((metadata) => {
        if (current) setEndpoint(metadata.registration_endpoint ?? null);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [authority]);
  return endpoint;
}

/**
 * Where this deployment's MCP surface is reachable, as its operator configured it: `null` while
 * asking, `undefined` when the deployment does not say.
 */
function useMcpUrl(): string | null | undefined {
  const api = useApi();
  const [url, setUrl] = useState<string | null | undefined>(null);
  useEffect(() => {
    let current = true;
    api
      .get<{ mcp_url: string | null }>("/connection")
      .then((connection) => {
        if (current) setUrl(connection.mcp_url ?? undefined);
      })
      .catch(() => {
        if (current) setUrl(undefined);
      });
    return () => {
      current = false;
    };
  }, [api]);
  return url;
}

/**
 * Whether an address is this computer. Claude's custom connectors are reached from Anthropic's
 * cloud and cannot open one, so a local CFOKit is connected through a proxy on the same machine.
 */
export function onThisComputer(url: string): boolean {
  const host = new URL(url).hostname;
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "[::1]" ||
    host.startsWith("127.")
  );
}

function registration(endpoint: string): string {
  const client = {
    client_name: "CFOKit for Claude Desktop",
    redirect_uris: [
      `http://localhost:${CALLBACK_PORT}/oauth/callback`,
      `http://127.0.0.1:${CALLBACK_PORT}/oauth/callback`,
    ],
    grant_types: ["authorization_code", "refresh_token"],
    response_types: ["code"],
    token_endpoint_auth_method: "client_secret_post",
  };
  return [
    `curl -s --cacert .local/tls/ca/ca.pem -X POST \\`,
    `  ${endpoint} \\`,
    `  -H 'content-type: application/json' \\`,
    `  -d '${JSON.stringify(client)}'`,
  ].join("\n");
}

function configuration(mcpUrl: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        "cfokit-local": {
          command: "npx",
          args: [
            "-y",
            "mcp-remote@0.14.3",
            mcpUrl,
            String(CALLBACK_PORT),
            "--static-oauth-client-info",
            '{"client_id":"CLIENT_ID","client_secret":"CLIENT_SECRET","token_endpoint_auth_method":"client_secret_post"}',
          ],
          env: { NODE_EXTRA_CA_CERTS: "/path/to/cfokit/.local/tls/ca/ca.pem" },
        },
      },
    },
    null,
    2,
  );
}

/** The hosted service: the plugin for the bookkeeper skill, and a custom connector for the books. */
function Plugin() {
  return (
    <>
      <Card title="1. Add the CFOKit plugin to Claude">
        <p className="text-body text-ink">
          In Claude, open <strong>Customize → Plugins</strong>, choose{" "}
          <strong>Add → Add marketplace</strong>, and enter:
        </p>
        <CopyBlock label="Marketplace" text={MARKETPLACE} />
        <p className="text-body text-ink">
          <strong>CFOKit</strong> then appears under <strong>From marketplaces you added</strong>.
          Turn on <strong>Sync automatically</strong> for it, so Claude keeps it current.
        </p>
      </Card>
      <Card title="2. Add the CFOKit connector">
        <p className="text-body text-ink">
          In Claude, open <strong>Customize → Connectors</strong>, choose{" "}
          <strong>Add custom connector</strong>, name it <strong>CFOKit</strong>, and paste this
          address. Leave the advanced settings empty.
        </p>
        <CopyBlock label="Connector address" text={HOSTED_MCP_URL} />
        <p className="text-body text-ink">
          Choose <strong>Add</strong>, then <strong>Connect</strong>, and sign in with your CFOKit
          account.
        </p>
      </Card>
      <Card title="3. Allow Claude in your company">
        <p className="text-body text-ink">
          The first time Claude uses CFOKit, it gives you a link. Open it and choose{" "}
          <strong>Allow to keep the books</strong> for your company. Claude acts only in the
          companies you allow it in.
        </p>
      </Card>
    </>
  );
}

/** A CFOKit others can reach: one custom connector, in Claude on the web or Claude Desktop. */
function CustomConnector({ mcpUrl }: { mcpUrl: string }) {
  return (
    <Card title="1. Add CFOKit to Claude">
      <p className="text-body text-ink">
        In Claude, open <strong>Settings → Connectors</strong>, choose{" "}
        <strong>Add custom connector</strong>, name it <strong>CFOKit</strong>, and paste this
        address:
      </p>
      <CopyBlock label="Connector address" text={mcpUrl} />
      <p className="text-body text-ink">
        Choose <strong>Connect</strong>, and sign in as yourself in the window that opens. The
        connector then works in Claude on the web and in Claude Desktop alike.
      </p>
    </Card>
  );
}

/** A CFOKit on this computer: a local proxy that Claude Desktop starts and that signs in as you. */
function LocalProxy({ mcpUrl }: { mcpUrl: string }) {
  const endpoint = useRegistrationEndpoint();
  return (
    <>
      <Card title="1. Register Claude Desktop">
        <p className="text-body text-ink">
          This CFOKit runs on your computer, so Claude Desktop reaches it through a local proxy. Run
          the commands from the folder CFOKit is in. Keep the <code>client_id</code> and{" "}
          <code>client_secret</code> this prints.
        </p>
        {endpoint === null ? (
          <Notice tone="neutral" label="Finding your sign-in service">
            Reading where it registers clients…
          </Notice>
        ) : (
          <CopyBlock label="Command" text={registration(endpoint)} />
        )}
      </Card>
      <Card title="2. Add CFOKit to Claude Desktop">
        <p className="text-body text-ink">
          In <code>~/Library/Application Support/Claude/claude_desktop_config.json</code>, with the
          client from step 1 and the full path to your CFOKit folder:
        </p>
        <CopyBlock label="Configuration" text={configuration(mcpUrl)} />
        <p className="text-body text-ink">
          Quit Claude Desktop fully and open it again. The first time it connects, a browser window
          opens: sign in as yourself.
        </p>
      </Card>
    </>
  );
}

/**
 * How to connect Claude to this CFOKit, with its own addresses filled in. Shown in getting started
 * and on each company's settings page, so the instructions are there whenever they are needed.
 * You connect once, not once per company.
 */
export function ConnectClaude() {
  const mcpUrl = useMcpUrl();
  if (mcpUrl === null) {
    return (
      <Notice tone="neutral" label="Finding your CFOKit">
        Reading where Claude connects to…
      </Notice>
    );
  }
  if (mcpUrl === undefined) {
    return (
      <Notice tone="warning" label="Address not configured">
        This CFOKit does not say where Claude connects. Its operator sets{" "}
        <code>MCP_PUBLIC_BASE_URL</code> on the REST service.
      </Notice>
    );
  }
  if (mcpUrl === HOSTED_MCP_URL) return <Plugin />;
  return onThisComputer(mcpUrl) ? (
    <LocalProxy mcpUrl={mcpUrl} />
  ) : (
    <CustomConnector mcpUrl={mcpUrl} />
  );
}
