# Contributing to CFOKit

Thanks for your interest. Bug reports, documentation fixes and code are all welcome.

This file covers the **process** of contributing, and deliberately holds no project rules.
Those live in [`CLAUDE.md`](CLAUDE.md) and the [decision records](docs/decisions/README.md);
restating them here would give them a second home to drift from, which is the failure
`CLAUDE.md` names when it says a second rules document becomes a second source of truth.

## Before you start

Read [`CLAUDE.md`](CLAUDE.md). It is the project's constitution, and every rule in it cites
the decision record holding its reasoning. If a task appears to require breaking a rule, ask
rather than working around it.

## Reporting a bug

Open an issue. Include what you did, what you expected, what happened instead, and the
versions of CFOKit, Python and Postgres you were running.

**Do not open a public issue for a security vulnerability.** Contact the maintainers
privately.

## Suggesting a change

Open an issue before writing code for anything larger than a fix, so the approach can be
agreed before you spend time on it.

A decision that future work should be bound by belongs in a decision record rather than a
code comment. [`docs/decisions/README.md`](docs/decisions/README.md) explains the format and
[`adr-template.md`](docs/decisions/adr-template.md) is the starting point.

## Getting started

Four steps. You do the ones that involve credentials or installing software yourself, in your
own terminal, and Claude Code never sees your GitHub credentials. Claude Code does the rest, and
the app walks you through getting started.

1. **Fork** [`cfokit/cfokit`](https://github.com/cfokit/cfokit) and clone your fork. This needs
   `git` and the [`gh`](https://cli.github.com/) CLI, signed in:

   ```bash
   gh auth login                              # once, if you have not already
   gh repo fork cfokit/cfokit --clone --remote
   cd cfokit
   ```

2. **Install the dependencies:**
   - [`uv`](https://docs.astral.sh/uv/) (not pip, not poetry)
   - Docker, with the daemon running
   - [Claude Code](https://claude.com/claude-code)
   - [Claude Desktop](https://claude.com/download), if you want to talk to your books

   A cloud Claude Code session provisions `uv` and Docker for you
   ([Setting up](#setting-up)). Anything that needs your credentials or a login, such as `gh`,
   Claude Code and Claude Desktop, is yours to do either way.

3. **Run Claude Code** in the clone.
4. **Paste this prompt:**

````text
Set me up to contribute to CFOKit. Do not use any GitHub credentials, and do not commit, push or
open pull requests. Go one step at a time, and wait for me where a step needs me.

1. Read CLAUDE.md and CONTRIBUTING.md.
2. Verify the prerequisites (uv, Docker with a running daemon). Tell me exactly what is
   missing; do not work around it. Then run `uv sync --locked`.
3. Build and run the stack as CONTRIBUTING.md describes: run the migrations, bring the
   stack up, and confirm /healthz and /readyz respond.
4. Run `uv run task lint` and `uv run task test`.
5. Trust the local certificate authority as docs/tutorials/run-cfokit-on-your-computer.md
   says, then tell me to open https://localhost:8080/app/ and go through getting started.
   Wait until I say I am done.
6. Report each step's result, and anything you could not do, with the error output.
````

### Getting started in the app

Open <https://localhost:8080/app/>, create your account, and follow the pages to your first
question in Claude. [Run CFOKit on your computer](docs/tutorials/run-cfokit-on-your-computer.md)
describes each step. Then go back to Claude Code and say you're done.

When you have a change ready, ask Claude Code to commit it on a branch, then push and open the
pull request yourself from your terminal
([Opening a pull request](#opening-a-pull-request)):

```bash
git push -u origin <branch>
gh pr create --repo cfokit/cfokit
```

## Setting up

The prompt above does this for you. This is the reference for what it installs and why, and for
doing it by hand.

You need [`uv`](https://docs.astral.sh/uv/) (not pip, not poetry) and Docker. The code targets
Python 3.14, which `uv` installs for you.

```bash
uv sync              # install everything
uv run task --list   # every command, and what it does
```

**Using Claude Code?** Any Claude Code environment with outbound network access works, cloud or
local, and the agent can run everything below except the steps that need your GitHub
credentials. A cloud session is provisioned automatically by `.claude/hooks/session-start.sh`
(`uv`, Python 3.14, Node 24 and pnpm for the web client, the locked dependencies and a Docker
daemon). That hook does nothing locally, so a local session needs `uv` and Docker installed
first. A stack in a cloud session lives inside its container, so you can
exercise it from the session but not from your own machine.

**Hosts it needs to reach** (from the `Dockerfile`, `compose.yaml` and the session hook):

| For | Host |
|---|---|
| `uv` binary and the Python 3.14 download | `github.com` and its release-asset hosts (`*.githubusercontent.com`) |
| Node, at the version `web/.nvmrc` pins, for the web client | `nodejs.org` |
| Python packages (`uv sync`, image builds) | `pypi.org`, `files.pythonhosted.org` |
| `python` and `postgres` images | Docker Hub: `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com` |
| the `uv` image used in builds | `ghcr.io` |
| the Keycloak image | `quay.io` and its CDN hosts (`*.quay.io`) |
| pnpm (fetched by corepack), the web client's packages, and `mcp-remote` when connecting Claude Desktop locally (`npx`) | `registry.npmjs.org` |
| Chromium for the end-to-end test (`playwright install`) | `cdn.playwright.dev`, `playwright.download.prss.microsoft.com` |

To paste into a cloud environment's allowed domains, one per line:

```
github.com
*.githubusercontent.com
nodejs.org
pypi.org
files.pythonhosted.org
registry-1.docker.io
auth.docker.io
production.cloudflare.docker.com
ghcr.io
quay.io
*.quay.io
registry.npmjs.org
cdn.playwright.dev
playwright.download.prss.microsoft.com
```

Registries redirect image layers to CDN hosts, so allow-list by domain rather than by the
names above alone. If a pull or build fails, the blocked host is in the error.

### Running the stack

```bash
docker compose --profile migrate run --rm migrate  # 1. create the schema (starts Postgres)
uv run task dev                                    # 2. compose.yaml plus compose.dev.yaml
```

Migrate first. `uv run task dev` stays in the foreground, so run it last or in a second shell.
It applies the development overlay: Postgres is published on `:5432` and logs
every statement. Plain `docker compose up` runs the same stack without it, which is what a
user gets and what CI proves. Migrations are an explicit command and never run on startup.

`docker compose build` does not build the `migrate` image, because that service sits behind a
profile. `migrate run` builds it on first use, or build it explicitly with
`docker compose --profile migrate build migrate`.

**Behind a TLS-intercepting proxy?** Image builds need the proxy's CA certificate. Set
`BUILD_CA_FILE` to the path of the CA bundle before building. Cloud sessions set it for you.

Once it is up, `/healthz` and `/readyz` should both respond.

**Every service copies the source into its image rather than mounting it.** After editing code,
rebuild before you run, or you are running the previous copy:

```bash
docker compose build <service>
docker compose --profile test build test   # before running the test suite
```

`docker compose down -v` destroys the database volume.

## Running the checks

```bash
uv run task check
```

That runs every gate CI runs on the host, cheapest first, and stops at the first failure: format,
lint, types, import contracts, the async boundary, the money and decision gates, the published
interfaces, and the unit and documentation tests. It adds the web client's checks when your
branch changes `web/`, `docs/contracts/` or `docs/design/`. `uv run task lint` and
`uv run task test` run parts of it on their own.

To run it before every push, install the hook once per clone (`git push --no-verify` skips it):

```bash
git config core.hooksPath scripts/hooks
```

CI runs these and more on every pull request.
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) is the authority on what has to pass.

**`uv run task test` on its own skips the integration suite**, which is most of it. The whole
suite needs Docker and runs inside the compose network:

```bash
docker compose --profile test run --rm test
```

`CLAUDE.md` explains why it runs there rather than against the stack from the host.

## The synthetic QuickBooks fixture

`tests/fixtures/quickbooks/` holds a synthetic company's QuickBooks Online exports, written by
`scripts/synthetic_books/` from business events we generate. Nothing in it is real books, and
nothing in it was produced by QuickBooks.
[ADR-0078](docs/decisions/0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md) says
why. `catalog.toml` lists the cases it must contain.

After changing the generator or the catalog, regenerate and commit what changed:

```bash
PYTHONPATH=scripts uv run python -m synthetic_books           # rewrite the fixture
PYTHONPATH=scripts uv run python -m synthetic_books --check   # what CI's drift test checks
```

### Validating it against a QuickBooks sandbox

The archives are our belief about what QuickBooks writes. Checking that belief means posting the
same events to a sandbox company and comparing. CI never does this, because it holds no
credentials and calls no third party. A person does it after a change to the generator. Until
it is done, `tests/test_quickbooks_sandbox.py` skips its validation check and says why.

**Before the first run:**

- **Your own Intuit developer account** and an app, at
  [developer.intuit.com](https://developer.intuit.com). The project holds no account and no
  credentials; whoever runs the tool does so under their own account and their own acceptance of
  Intuit's terms. The app gives you a **client ID** and a **client secret**.
- **An empty sandbox company.** A new sandbox company comes with Intuit's sample data, which
  must not end up in the comparison (ADR-0044). Empty it from the developer portal's Sandboxes
  list ("Clear data and reset", or "Delete all data"). What stays is QuickBooks' default chart
  of accounts and two items, which every new company has.
- **Intuit's Developer Terms read** by whoever accepts them, § 3.1 in particular.

**Four values, from Intuit's OAuth 2.0 Playground** (Tools, then OAuth 2.0 Playground). Select
your app, tick the `com.intuit.quickbooks.accounting` scope, choose **Get authorization code**,
sign in and pick the sandbox company, then choose **Get tokens**.

| Variable | What it is |
|---|---|
| `QBO_CLIENT_ID` | your app's client ID |
| `QBO_CLIENT_SECRET` | your app's client secret |
| `QBO_REFRESH_TOKEN` | the refresh token *Get tokens* shows. It lasts about 100 days, and the tool turns it into hour-long access tokens itself |
| `QBO_REALM_ID` | the sandbox company's id, which Intuit also calls the Company ID |

On your own machine, `export` them in the shell. In a **Claude Code cloud environment**, add them
in the environment's settings (the environment menu in the session's title bar, then **Edit**),
under Network secrets where that is offered, or as environment variables. A new session picks
them up. **Never paste them into a chat.** The tool reads them only from the environment and
never prints them.

**Two hosts, allowed in the environment's network access** if it does not allow everything:

```
oauth.platform.intuit.com
sandbox-quickbooks.api.intuit.com
```

**Then:**

```bash
PYTHONPATH=scripts uv run python -m synthetic_books.sandbox post       # resumable
PYTHONPATH=scripts uv run python -m synthetic_books.sandbox validate
```

A payload QuickBooks rejects means an event was modeled wrong, so fix the generator, not the
post. So does one it accepts but keeps differently, which `post` checks for. A payload changed
after it was posted stops `post`, because the company holds the old one: empty the company,
delete `.local/qbo-sandbox/`, and post again.

**Some settings only a person can make.** The API accepts the fiscal year, account numbers and
"Automatically apply credits" and ignores them. `post` checks them first and names any that
need changing; make them in the sandbox company under Settings, Account and settings,
Advanced. The calendar-year rendering needs the fiscal year changed too, so `validate` compares
the renderings the current settings allow, remembers those that agreed, and names the setting
the next one needs. Run it again after the change, and change it back when it is done.

Differences that `validate` finds are written under `.local/qbo-sandbox/`, which git ignores,
and are fixed in the writer. When every rendering agrees, `validate` writes
`tests/fixtures/quickbooks/validation.json`; commit that. **Never commit anything QuickBooks
returned.** Intuit's terms do not permit it, and nothing under `.local/` can reach a commit.

The layout of the reports cannot be seen through the API. After a change to the writer's
layout, download Export Data from the sandbox company (Settings, then Export data): its reports
over all dates, with the fiscal year starting in July and account numbers off, as the accrual
archive is written. Compare it, leaving the download outside the repository; the company's name
and the time each report was run differ by nature, and are not compared:

```bash
PYTHONPATH=scripts uv run python -m synthetic_books.sandbox compare-export ~/Downloads/export.zip
```

## Opening a pull request

- Work on a branch of your fork. Never commit to `main`.
- Open the pull request from your fork against `cfokit/cfokit`.
- One logical change per commit, with an imperative subject line.
- Cite the requirement or `ADR-` id when a change implements or follows one. Requirement ids
  are defined in [`requirements.md`](docs/product/requirements.md).
- Say which checks you ran locally, and flag anything you could not verify. A red suite
  belongs in the pull request description, not in the reviewer's discovery.
- If part of the work is incomplete or blocked, say so. Scaling work down is a maintainer's
  call rather than something to do quietly.

## Review

A maintainer will review. Expect as many questions about reasoning as about code — this is an
accounting system, and *why is this correct?* is the substance of the review.

## Licensing

CFOKit is [Apache 2.0](LICENSE). Contributions are accepted under the same license, which
Apache 2.0 § 5 makes the default. There is no separate CLA to sign.
