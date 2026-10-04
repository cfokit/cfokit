import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "react-oidc-context";
import { useApi } from "../api";
import { ActionBar, Button, Card, CopyBlock, Notice } from "../components";
import { StartFrame } from "./StartFrame";

// The port mcp-remote listens on for the sign-in's return, fixed so the client is registered once.
const CALLBACK_PORT = 44196;

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
        cfokit: {
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

const SKILL = "cd skills && zip -r ~/Downloads/bookkeeper.zip bookkeeper";

/** Step 4: adding CFOKit to Claude Desktop, and the bookkeeper skill to Claude. */
export function ConnectPage({ entityId }: { entityId: string }) {
  const navigate = useNavigate();
  const endpoint = useRegistrationEndpoint();
  const mcpUrl = useMcpUrl();
  return (
    <StartFrame step={3} title="Connect Claude">
      <p className="text-body text-ink">
        Claude Desktop reaches your CFOKit through a local connection that signs in as you. Run the
        commands from the folder CFOKit is in. You do this once, not once per company.
      </p>
      <Card title="1. Register Claude Desktop">
        <p className="text-body text-ink">
          So it signs in with the same client every time. Keep the <code>client_id</code> and{" "}
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
        {mcpUrl === null ? (
          <Notice tone="neutral" label="Finding your CFOKit">
            Reading where Claude connects to…
          </Notice>
        ) : mcpUrl === undefined ? (
          <Notice tone="warning" label="Address not configured">
            This CFOKit does not say where Claude connects. Its operator sets{" "}
            <code>MCP_PUBLIC_BASE_URL</code> on the REST service.
          </Notice>
        ) : (
          <CopyBlock label="Configuration" text={configuration(mcpUrl)} />
        )}
        <p className="text-body text-ink">
          Quit Claude Desktop fully and open it again. The first time it connects, a browser window
          opens: sign in as yourself.
        </p>
      </Card>
      <Card title="3. Add the bookkeeper skill">
        <CopyBlock label="Command" text={SKILL} />
        <p className="text-body text-ink">
          Then in Claude Desktop, choose <strong>Customize → Skills → + → Create skill</strong>, and
          upload <code>bookkeeper.zip</code> from your Downloads folder.
        </p>
      </Card>
      <ActionBar>
        <Button
          variant="primary"
          fullWidth
          className="tablet:w-auto"
          onClick={() => void navigate({ to: "/companies/$entityId/ask", params: { entityId } })}
        >
          Next: your first question
        </Button>
      </ActionBar>
    </StartFrame>
  );
}
