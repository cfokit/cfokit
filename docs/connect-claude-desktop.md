# Connecting Claude Desktop to a local CFOKit

> **Tested on macOS only.** The certificate-trust command and the config path below are macOS's.
> Windows and Linux are untested, so expect to adapt those steps.

## How Claude Desktop reaches it

Claude Desktop reaches an MCP server two ways:

| | Custom connector | Local server |
|---|---|---|
| Who connects | Anthropic's cloud | your machine |
| Transport | streamable HTTP | **stdio** |
| Can reach `localhost` | no | yes |

A custom connector can't reach a local stack, so the setup here is a **local server** entry
that runs `mcp-remote`, a stdio-to-HTTP proxy that also performs the OAuth flow.

## 1. Start the stack

```
docker compose up -d --wait
```

Then create the schema. Migrations never run on startup, so a fresh stack has none:

```
docker compose --profile migrate run --rm migrate
```

The first run generates a local certificate authority into `.local/tls/`, and the identity
provider, the web client and the MCP endpoint all serve HTTPS with certificates it signs. OAuth
clients refuse to send credentials to a plain-HTTP token endpoint, so the sign-in does not work
without it.

**Trust that CA once**, so your browser opens CFOKit and its sign-in page without a warning.
macOS asks for your password:

```
security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db .local/tls/ca/ca.pem
```

It stays trusted until you delete `.local/tls/`, which makes a new CA on the next start.

## 2. Create your account and bring in your books

On Windows, first add this line to your hosts file:

```
127.0.0.1 keycloak.localhost
```

Open **https://localhost:8080/app/**, choose **Register** on the sign-in page, and create your
account with your email and a password. That account is the one Claude Desktop signs in as in
step 3.

The web client then takes you through getting started: choose your QuickBooks Online export (the
.zip from **Settings → Export data**, all dates), confirm the company it describes, and import.
The export is read in your browser and never uploaded; what is posted is what was read from it,
signed in as you. When it finishes, the page shows whether the books agree with QuickBooks.

## 3. Configure Claude Desktop

**Register one client and reuse it.** Otherwise `mcp-remote` registers a fresh client and signs
in again on every launch.

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

Keep the `client_id` and `client_secret` it returns. Then in
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cfokit": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.3", "https://localhost:8081/mcp", "44196",
               "--static-oauth-client-info",
               "{\"client_id\":\"…\",\"client_secret\":\"…\"}"],
      "env": {"NODE_EXTRA_CA_CERTS": "/path/to/cfokit/.local/tls/ca/ca.pem"}
    }
  }
}
```

`44196` is the callback port the client above was registered with.

`mcp-remote` is pinned. Without a version, `npx` fetches the newest release on every launch,
and a release that changes behavior changes your setup without anything in this repository
changing.

`NODE_EXTRA_CA_CERTS` takes the absolute path to the CA from step 1. `mcp-remote` runs on Node,
which trusts its own certificate list rather than the macOS keychain, so trusting the CA for
your browser does not reach it.

Quit Claude Desktop fully and reopen it — closing the window is not enough. On first use a
browser window opens; sign in as the user from step 2.

## 4. Install the skill

Package the folder and upload it:

```
cd skills && zip -r ~/Downloads/bookkeeper.zip bookkeeper
```

Then in Claude Desktop: **Customize → Skills → `+` → Create skill**, and upload that zip.

## 5. Ask about your books

The last page of getting started has **Continue in Claude**, which opens Claude Desktop on a new
chat with the first question already written and naming your company. Send it.

## When a tool is missing

The skill will say a tool is not there rather than improvise around it. Before assuming the
connection is at fault, ask the deployment what it serves:

```
curl -s --cacert .local/tls/ca/ca.pem https://localhost:8081/readyz | python3 -m json.tool
```

```json
{"status": "ready",
 "tools": {"count": 19, "digest": "3b1309c30f9a", "names": ["account_detail", …]}}
```

Compare that list against `docs/contracts/mcp-tools.json`. A container built before a tool was
merged serves the tools it was built with.

If they differ, rebuild:

```
docker compose up -d --build mcp ledger
```

## Reading the result

**A cash-basis difference is expected.** QuickBooks' reports are often run on the cash basis, and
CFOKit records every invoice and bill when it happens, so receivables and the income not yet
recognized against them differ by exactly what is unsettled — ADR-0037 predicts it, and the
import page marks it as expected. To compare like with like, set QuickBooks' accounting method to
Accrual and re-export.

**Importing the same file again is safe.** Each transaction's key is derived from the file and
its row, so an import that stopped partway resumes and nothing is counted twice. A *re-export* is
a different file, and therefore a second import: use a fresh company for one.

**Rows left out are refusals decided before anything was posted.** A transaction with one line
records no movement of value; one whose debits and credits differ cannot balance. The page names
each with the row it came from.
