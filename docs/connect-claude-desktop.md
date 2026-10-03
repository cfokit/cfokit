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

## 2. Create your account

On Windows, first add this line to your hosts file:

```
127.0.0.1 keycloak.localhost
```

Open **https://localhost:8080/app/**, choose **Register** on the sign-in page, and create your
account with your email and a password. The web client signs you in when you're done; that
account is the one Claude Desktop signs in as in step 3.

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

## 5. Create your books

In Claude Desktop:

> Create an entity called "My Company", accrual basis, fiscal year ending 31 December, USD,
> America/New_York.

Creating an entity needs an authenticated caller and no prior role — it is the one act with
that property, and **the act of creating it is what makes you its owner** (`IAM-05`, `IAM-06`).
There is nothing to provision and no grant for anyone to make.

Every declaration is required and none has a default. The basis, the fiscal year end, the
currency and the time zone are what every report the entity ever produces is computed against,
and a default would be an undeclared state wearing a value (`LED-14`, `LED-15`, `PLT-08`).

Keep the `entity_id` it returns.

## 6. Import, reconcile, compare

Attach the QuickBooks export to a Claude Desktop chat and ask the skill to import it into the
entity from step 5. The skill's script reads the export in Claude's sandbox and first shows you
what it holds:

```
QuickBooks Online, USD
  5556 transactions, 11580 posting lines
  62 accounts
  covering 2018-04-11 to 2026-09-01
  entries unknown basis, stated balances cash basis
  2 accounts the source states no type for: [...]
  NOTE: the stated balances were run on a different basis from the journal, so the
  obligation accounts will differ by what is unsettled (ADR-0037)
```

Nothing has been sent yet. When you are satisfied, the skill imports through the MCP tools —
`open_import`, `import_entries` in batches, then `reconcile_import` — signed in as you through
Claude Desktop's connection. The script itself never calls CFOKit: a credential never passes
through an agent or a model (`IAM-10`). The reconciliation reads like this:

```
posted 5553, replayed 0, skipped 3
reconciled 25 of 27 accounts exactly
  DIVERGES Accounts Receivable (A/R): ours 25469.0000000000 theirs 0
  DIVERGES Services: ours -2518417.0400000000 theirs -2492948.04
profit_and_loss: 44 agree, 1 diverge (theirs cash, ours accrual)
balance_sheet: 10 agree, 1 diverge (theirs cash, ours accrual)
```

**Those two divergences are the same figure**, 25,469.00, appearing as the receivable and as the
income not yet recognized against it. The journal is accrual and the reports were run on a cash
basis, so they differ by exactly what is unsettled — ADR-0037 predicts it. To compare like with
like, set QuickBooks' accounting method to Accrual and re-export.

**Run it again and it is safe.** Each entry's key is derived from the file and the row, so an
import that died partway resumes: `replayed` rises and `posted` stays at zero. A *re-export* is a
different file and therefore a second import — use a fresh entity for one.

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

**Three statements, one divergence, appearing twice.** On a real set of books the trial balance
agreed on 25 of 27 accounts, the profit and loss on 44 of 45, and the balance sheet on 10 of 11
— and every disagreement was the same figure: receivables outstanding, once as the receivable
and once as the revenue not yet recognized against it.

That is the difference between an accrual ledger and cash-basis statements, which ADR-0037
predicts. `expect_obligation_accounts_to_differ` says so before you look. **The prediction is
what makes a different figure a defect** rather than something to explain away.

**Skipped rows are refusals decided before anything was posted.** A transaction with one line
records no movement of value; one whose debits and credits differ cannot balance. They are named
in the report with the reference they came in under.

**Accounts the source states no type for** are created as assets, which is inert for a trial
balance, and listed so the choice is visible rather than discovered in a statement later.
