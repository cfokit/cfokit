# Connect Claude to CFOKit

Claude reaches your books through CFOKit's MCP endpoint, signed in as you. You connect once, not
once per company.

**The web app shows these steps with your own addresses filled in.** Open **Settings**, at the top
right of every page, and look under **Connect Claude**. This page explains what those steps do.

How you connect depends on where CFOKit runs:

| | Custom connector | Local proxy |
|---|---|---|
| When | CFOKit is reachable from the internet, like the hosted service | CFOKit runs on your computer |
| Works in | Claude on the web and Claude Desktop | Claude Desktop |
| Who connects | Anthropic's cloud | your computer |

A custom connector cannot reach `localhost`, so a CFOKit on your computer uses a local proxy
instead.

## A CFOKit reachable from the internet

1. In Claude, open **Settings → Connectors** and choose **Add custom connector**.
2. Name it **CFOKit**, and paste the MCP address from CFOKit's Settings page. For the hosted
   service, it is `https://mcp.cfokit.ai/mcp`.
3. Choose **Connect**, and sign in as yourself in the window that opens.

The connector then works in Claude on the web and in Claude Desktop alike.

## A CFOKit on your computer

> **Tested on macOS only.** The config path below is macOS's.

Claude Desktop starts `mcp-remote`, a proxy that turns its local connection into HTTPS and signs
in as you.

**1. Register one client and reuse it.** Otherwise `mcp-remote` registers a new client, and signs
in again, every time Claude Desktop starts. From the folder CFOKit is in:

```bash
curl -s --cacert .local/tls/ca/ca.pem -X POST \
  https://keycloak.localhost:8443/realms/cfokit/clients-registrations/openid-connect \
  -H 'content-type: application/json' -d '{
    "client_name":"CFOKit for Claude Desktop",
    "redirect_uris":["http://localhost:44196/oauth/callback",
                     "http://127.0.0.1:44196/oauth/callback"],
    "grant_types":["authorization_code","refresh_token"],
    "response_types":["code"],
    "token_endpoint_auth_method":"client_secret_post"}'
```

Keep the `client_id` and `client_secret` it returns.

**2. Add CFOKit to Claude Desktop**, in
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cfokit": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.3", "https://localhost:8081/mcp", "44196",
               "--static-oauth-client-info",
               "{\"client_id\":\"…\",\"client_secret\":\"…\",\"token_endpoint_auth_method\":\"client_secret_post\"}"],
      "env": {"NODE_EXTRA_CA_CERTS": "/path/to/cfokit/.local/tls/ca/ca.pem"}
    }
  }
}
```

* `44196` is the callback port the client was registered with.
* `token_endpoint_auth_method` must match the registration. Without it, `mcp-remote` sends the
  secret in a header, and the sign-in fails with `unauthorized_client`.
* `mcp-remote` is pinned. Without a version, `npx` fetches the newest release on every launch,
  and a release that changes behavior changes your setup.
* `NODE_EXTRA_CA_CERTS` is the absolute path to CFOKit's certificate authority. `mcp-remote` runs
  on Node, which keeps its own list of trusted certificates rather than using the macOS keychain.

**3. Restart Claude Desktop.** Quit it fully and open it again; closing the window is not enough.
The first time it connects, a browser window opens. Sign in as yourself.

## Add the bookkeeper skill

The skill tells Claude how to keep books with CFOKit: which tools to call, and what never to do,
such as guess a figure. From the folder CFOKit is in:

```bash
cd skills && zip -r ~/Downloads/bookkeeper.zip bookkeeper
```

Then in Claude, choose **Customize → Skills → + → Create skill**, and upload the zip. Without the
CFOKit folder, the skill's files are
[published on GitHub](https://github.com/cfokit/cfokit/tree/main/skills/bookkeeper).

## Working with more than one company

One connection reaches every company you hold. Name the company when you ask, and Claude finds it
with `list_entities`. Every answer names its company, and Claude says which company each figure
belongs to. It stays with the company you named until you name another.

## When a tool is missing

The skill says a tool is not there rather than work around it. Before blaming the connection, ask
CFOKit which tools it serves:

```bash
curl -s https://mcp.cfokit.ai/readyz | python3 -m json.tool
```

On your computer, use `https://localhost:8081/readyz`, with `--cacert .local/tls/ca/ca.pem`.

```json
{"status": "ready",
 "tools": {"count": 28, "digest": "…", "names": ["account_detail", …]}}
```

Compare that list with `docs/contracts/mcp-tools.json`. A container built before a tool was added
serves the tools it was built with. On your computer, rebuild:

```bash
docker compose up -d --build mcp ledger
```
