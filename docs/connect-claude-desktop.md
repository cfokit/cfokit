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

**4. Fill in `Username`, `Email`, `First name` and `Last name`, then click `Create`.**

Only `Username` carries an asterisk, and the other three are required anyway. Keycloak's user
profile marks email and both names required for anyone holding the `user` role, so a user
created with a username alone is sent to an **Update Account Information** form at first
sign-in — which happens mid-authorisation, in the browser window `mcp-remote` opened. Filling
them here costs nothing and skips that.

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

**Register one client first, and keep it.** Dynamic registration is what the conformance
contract asks for and it works — but `mcp-remote` registers a *fresh* client on every launch,
then compares the scopes that client was granted against the ones it had cached, finds them
different, and signs in again. Every launch. That re-authentication is what makes several proxy
instances race for one callback port, and the race is what makes the desktop client cancel the
server before it ever asks for a tool list.

A client that does not change breaks that loop at the start:

```bash
curl -s -X POST \
  http://keycloak.localhost:8180/realms/cfokit/clients-registrations/openid-connect \
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
      "args": ["-y", "mcp-remote", "http://localhost:8081/mcp", "44196",
               "--static-oauth-client-info",
               "{\"client_id\":\"…\",\"client_secret\":\"…\"}"]
    }
  }
}
```

The secret sits in that file in plaintext. On a laptop, against an issuer nothing else can
reach, that is proportionate; anywhere else it is not, and the client should be one an operator
provisions rather than one anybody can register.

Quit Claude Desktop fully and reopen it — closing the window is not enough. On first use a
browser window opens for the sign-in from step 4. `mcp-remote` registers itself as a client
through RFC 7591, with no credential for you to create.

The trailing `44196` pins the callback port. Without it each instance derives its own, and
Claude Desktop starts several — they then race for the sign-in, and the losers report that
"authentication was completed by another instance", find no tokens where they expect them, and
give up unauthenticated. Pinning the port narrows that race; pinning the client above is what
stops it starting.

**Anonymous registration is still open** even though the client above is registered by hand,
because the four Keycloak policies that would restrict it each refuse a standards-conforming
client outright — `infra/keycloak/README.md` says which and why.
On a laptop that costs nothing: whoever can reach the issuer can already reach the ledger. **A
deployment reachable by anything else must close it** and register clients deliberately, which
`mcp-remote --static-oauth-client-info` supports.

`mcp-remote` itself is verified against this stack: it discovers the issuer, registers, and
opens the browser at a valid authorization URL. What is not exercised is Claude Desktop
launching it and a person completing the sign-in.

## 6. Install the skill

**Claude Desktop does not read `~/.claude/skills/`.** That is Claude Code's location, and a
skill copied there is invisible to the desktop app — which then answers bookkeeping questions
out of general knowledge, and what general knowledge suggests is a ledger file in some other
format. A second set of books nobody reconciles is worse than no answer.

Package the folder and upload it:

```
cd skills && zip -r ~/Downloads/bookkeeper.zip bookkeeper
```

Then in Claude Desktop: **Customize → Skills → `+` → Create skill**, and upload that zip.

The skill's own first rule is what makes the failure above impossible: if the CFOKit tools are
not reachable it says so and stops, rather than producing a chart of accounts somewhere else.

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

## When a tool is missing

The skill will say a tool is not there rather than improvise around it. Before assuming the
connection is at fault, ask the deployment what it serves:

```
curl -s http://localhost:8081/readyz | python3 -m json.tool
```

```json
{"status": "ready",
 "tools": {"count": 19, "digest": "3b1309c30f9a", "names": ["account_detail", …]}}
```

Compare that list against `docs/contracts/mcp-tools.json`. **A container built before a tool
was merged serves the surface it was built with**, and nothing in the repository can see that:
CI diffs the generated contract against the committed one, and both are current while the
running thing is not. The symptom is a client truthfully reporting that a tool does not exist.

If they differ, rebuild:

```
docker compose -f compose.yaml -f compose.imports.yaml up -d --build mcp ledger
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
