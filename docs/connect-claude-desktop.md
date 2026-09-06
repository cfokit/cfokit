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

Then, **from the repository root, and with both files named every time**:

```
docker compose -f compose.yaml -f compose.imports.yaml up -d --wait mcp
```

`compose.yaml` pins `name: cfokit`, so this attaches to the stack already running rather than
starting a second one. But naming only `compose.yaml` **recreates the container without the
overlay**, and the import tools then disappear — they are registered only when `IMPORT_ROOT` is
set, so `tools/list` quietly returns sixteen tools instead of eighteen rather than failing.

There is deliberately no `docker-compose.override.yml` and no `COMPOSE_FILE` default, for the
reason `compose.yaml` already gives: an overlay that applies itself hands you bind mounts you
did not ask for. Explicit beats idiomatic here (ADR-0018).

**Read-only on the exports, and a separate writable directory for reports.** The tools write
their detail — the figures a reconciliation names — to `IMPORT_REPORTS`, never beside the
source. Mount the directory the export is in, not your home directory: whatever is mounted is
what the tools can read.

## Keeping one stack straight

Everything runs under the compose project `cfokit`, from the repository root. Two things follow.

**A development database accumulates.** The integration suite creates an entity per test and
removes none, and every import run leaves the books it imported. That is harmless — entities are
isolated from each other by row-level security — but it means picking the entity id you meant
rather than the most recent one. Create a fresh entity for a run you care about.

**`docker compose down -v` destroys the volume**, and with it every set of books in it. The
warning at the top of `compose.yaml` is not decorative.

## 3. Nothing, and why there is a step here at all

The issuer answers on one hostname and redirects everything else to it. That is deliberate:
`KC_HOSTNAME` is authoritative and a token's `iss` is validated against it, so an issuer
reachable under two names would issue tokens the application rejects.

The name is **`keycloak.localhost`**, chosen so that both sides get it for free. `*.localhost`
resolves to the loopback address without a hosts entry (RFC 6761), so a browser reaches the
published port; inside the compose network the same name is an alias on the service. One name,
both sides, nothing to configure.

So `http://localhost:8180` is still not a way in — it answers with a redirect:

```
GET http://localhost:8180/  ->  302  Location: http://keycloak.localhost:8180/admin/
```

but that is now a redirect your browser can follow.

**If `*.localhost` does not resolve on your platform** — Windows historically does not implement
it — add the name to your hosts file instead:

```
127.0.0.1 keycloak.localhost
```

A deployment reachable by more than this machine sets `KC_HOSTNAME` and `AUTH_ISSUER_URL` to a
public hostname, which is the condition `PUBLIC_BASE_URL` already carries (ADR-0004, ADR-0018).

## 4. Create a user to sign in as

The realm ships with no users. That is deliberate — a realm carrying a known password would be
a credential in the repository — so this is the one step with no way to skip it.

**1. Open http://keycloak.localhost:8180** — the name from step 3, not `localhost` — and sign
in with `admin` / `admin`.

You will see a yellow banner: *"You are logged in as a temporary admin user."* That is
Keycloak telling you to replace the bootstrap administrator before this is reachable by
anything but your laptop. It does not block anything here.

**2. Switch realms.** Top left, under the Keycloak logo, is a box reading **master**. Click it
and choose **CFOKit** (`cfokit`). Everything below happens in that realm — a user created in
`master` administers Keycloak and cannot sign in to CFOKit.

**3. Left menu → `Users` → `Create new user`.** Under **Manage**, not **Configure**. On a realm
with no users yet the list is empty and offers the same button in the middle of the page.

**4. Fill in `Username` and click `Create`.** It is the only field marked required — the
asterisk is on `Username` alone. Email, first and last name are optional and nothing here needs
them.

**5. Open the `Credentials` tab and click `Set password`.** This is the step people miss: the
create form has no password field, so a user created and left alone has no way to sign in. The
tab sits beside **Details** on the user's page.

**6. In the dialog, enter the password twice and turn `Temporary` OFF.**

**It defaults to On**, and On means Keycloak demands a new password at first sign-in. That
prompt appears inside the browser window `mcp-remote` opened mid-authorisation, which is an
unwelcome place to meet it.

There are no password rules. The realm sets no `passwordPolicy`, so anything non-empty is
accepted — a single character is taken. That is Keycloak's default rather than a choice made
here: a realm shipping opinions about password strength would be deciding for every deployment,
and this one has not been decided.

**7. Click `Save`.** The user's own `ID` on the **Details** tab is the `sub` a token will carry,
if you ever need to match a principal to a person.

Change the admin password before this is reachable by anything but your laptop. `Realm settings`
in the same menu is where brute-force protection lives, and it is off.

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
browser window opens for the sign-in from step 4. `mcp-remote` registers itself as a client
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

## 7. Create your books

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
