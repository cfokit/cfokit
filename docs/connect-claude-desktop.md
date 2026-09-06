# Connecting Claude Desktop to a local CFOKit

Every command here was run against a local stack; the figures shown are real output. The one
step that cannot be scripted — signing in through a browser — is marked as such.

## What connects to what, and why it is not obvious

Claude Desktop reaches an MCP server two ways, and neither is "point it at localhost":

| | Custom connector | Local server |
|---|---|---|
| Who connects | Anthropic's cloud | your machine |
| Transport | streamable HTTP | **stdio** |
| Can reach `localhost` | no | yes |

CFOKit speaks streamable HTTP (ADR-0012, ADR-0017), so a custom connector would need the stack
published on a public hostname. For a local stack the answer is a **local server** entry that
runs `mcp-remote`, a stdio-to-HTTP proxy that also performs the OAuth flow. It runs on your
machine, so it can reach `localhost:8081`.

## 1. Start the stack

```
docker compose up -d --wait
```

The identity provider needs its own database, created by `infra/postgres/init-app-role.sh` on
an empty data directory. An existing volume needs it once:

```
docker compose exec postgres psql -U cfokit -d postgres -c \
  "CREATE DATABASE keycloak OWNER cfokit"
```

## 2. Mount the exports, read-only

`IMPORT_ROOT` is unset by default, and without it the import tools are not registered at all —
a tool taking a path is a file-read primitive, and one any holder of a token can reach should
not exist unless a deployment asked for it (ADR-0040).

Create `compose.imports.yaml` beside `compose.yaml`:

```yaml
services:
  mcp:
    environment:
      IMPORT_ROOT: /imports
      IMPORT_REPORTS: /reports
    volumes:
      - /path/to/your/exports:/imports:ro
      - /path/to/a/reports/directory:/reports
```

Then `docker compose -f compose.yaml -f compose.imports.yaml up -d --wait mcp`.

**Read-only on the exports, and a separate writable directory for reports.** The tools write
their detail — the figures a reconciliation names — to `IMPORT_REPORTS`, never beside the
source. Mount the directory the export is in, not your home directory: whatever is mounted is
what the tools can read.

## 3. Create a user to sign in as

The realm ships with no users; a realm carrying a known password would be a credential in the
repository. Open the admin console at **http://localhost:8180**, sign in with `admin` / `admin`,
switch to the **cfokit** realm, and add a user with a password.

Change the admin password before this is reachable by anything but your laptop.

## 4. Let the browser reach the issuer

The ledger tells a client where the issuer is, and that address has to mean the same thing from
inside the compose network and from your browser. Add one line to `/etc/hosts`:

```
127.0.0.1 keycloak
```

Without it the sign-in page will not load: the client is sent to `http://keycloak:8180`, which
resolves inside the network and nowhere else.

## 5. Configure Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cfokit": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8081/mcp"]
    }
  }
}
```

Quit Claude Desktop fully and reopen it — closing the window is not enough. On first use a
browser window opens for the sign-in from step 3. `mcp-remote` registers itself as a client
through RFC 7591; the realm's registration policy admits it because its redirect URI is on
`localhost`.

**Not verified end to end here.** Everything either side of it is: the tools, the tokens, the
imports and the reports below were all run against this stack. What was not exercised is
Claude Desktop launching the proxy and a person clicking through the sign-in.

## 6. Install the skill

```
mkdir -p ~/.claude/skills
cp -r skills/bookkeeper ~/.claude/skills/
```

The skill talks to the ledger over the published tool surface and by no other route (ADR-0014).
It knows the import flow: `plan_import` is its call to make, `apply_import` is yours.

## 7. Give yourself the books

Creating an entity needs an authenticated identity and no prior role (`IAM-06`), and the
creator becomes its owner. A client registers itself, takes a token, and creates the entity:

```bash
KC=http://localhost:8180/realms/cfokit
R=$(curl -s -X POST "$KC/clients-registrations/openid-connect" \
  -H 'content-type: application/json' \
  -d '{"client_name":"bootstrap","grant_types":["client_credentials"],
       "response_types":["token"],"token_endpoint_auth_method":"client_secret_post",
       "redirect_uris":["http://localhost/cb"]}')
CID=$(echo "$R" | python3 -c 'import json,sys; print(json.load(sys.stdin)["client_id"])')
SEC=$(echo "$R" | python3 -c 'import json,sys; print(json.load(sys.stdin)["client_secret"])')

TOK=$(curl -s -X POST "$KC/protocol/openid-connect/token" \
  -d grant_type=client_credentials -d "client_id=$CID" -d "client_secret=$SEC" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://localhost:8080/entities \
  -H "authorization: Bearer $TOK" -H 'content-type: application/json' \
  -d '{"slug":"my-company","name":"My Company","accounting_basis":"accrual",
       "fiscal_year_end_month":12,"fiscal_year_end_day":31,
       "functional_currency":"USD","time_zone":"UTC"}'
```

That returns an `entity_id`, owned by the bootstrap client. Grant your own user the same role,
using the `sub` shown on their user page in the admin console:

```bash
curl -s -X POST "http://localhost:8080/entities/<entity-id>/grants" \
  -H "authorization: Bearer $TOK" -H 'content-type: application/json' \
  -d '{"to_principal":"<your-user-sub>","role":"owner"}'
```

## 8. Import, reconcile, compare

In Claude Desktop, with the skill loaded:

> Plan an import of `Growth Science LLC Sep 5, 2026.zip` into entity `<entity-id>`.

```json
{"ok": true, "system": "QuickBooks Online",
 "transactions": 5553, "postings": 11577, "accounts_to_create": 62,
 "covering": {"earliest": "2018-04-11", "latest": "2026-09-01"},
 "rows_to_skip": 3, "can_apply": true,
 "expect_obligation_accounts_to_differ": true}
```

`apply_import` is a person's act — a delegated agent session is refused with `not_a_person`
(ADR-0007). Run it yourself, or from a session holding your own token:

```json
{"ok": true, "accounts_created": 62, "transactions_posted": 5553, "rows_skipped": 3,
 "reconciliation": {"agreed": 25, "compared": 27, "divergences": 2}}
```

Then `compare_statements` puts the profit and loss and balance sheet CFOKit produces against
the ones the export printed:

```json
{"report": "profit_and_loss", "agreed": 44, "compared": 45, "divergences": 1,
 "their_basis": "cash", "our_basis": "accrual"}
{"report": "balance_sheet",   "agreed": 10, "compared": 11, "divergences": 1,
 "their_basis": "cash", "our_basis": "accrual"}
```

## Reading the result

**Three statements, one divergence, appearing twice.** On a real set of books the trial balance
agreed on 25 of 27 accounts, the profit and loss on 44 of 45, and the balance sheet on 10 of 11
— and every disagreement was the same figure: receivables outstanding, once as the receivable
and once as the revenue not yet recognised against it.

That is the difference between an accrual ledger and cash-basis statements, which ADR-0037
predicts. `expect_obligation_accounts_to_differ` says so before you look. **The prediction is
what makes a different figure a defect** rather than something to explain away.

**Skipped rows are refusals decided before anything was posted.** A transaction with one line
records no movement of value; one whose debits and credits differ cannot balance. They are named
in the report with the reference they came in under.

**Accounts the source states no type for** are created as assets, which is inert for a trial
balance, and listed so the choice is visible rather than discovered in a statement later.
