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

Anything that needs your GitHub credentials you run yourself, in your own terminal. Claude Code
never sees them. Claude Code does the rest.

Before you begin, have `git` and the [`gh`](https://cli.github.com/) CLI installed. Claude Code
checks and installs the rest (`uv`, Docker).

1. **Fork and clone** with `gh`. This forks `cfokit/cfokit`, clones your fork and adds
   `upstream` for you:

   ```bash
   gh auth login                              # once, if you have not already
   gh repo fork cfokit/cfokit --clone --remote
   cd cfokit
   ```

2. **Run [Claude Code](https://claude.com/claude-code)** in that directory.
3. **Paste this prompt:**

````text
Set me up to contribute to CFOKit. Do not use any GitHub credentials, and do not commit,
push or open pull requests.

1. Read CLAUDE.md and CONTRIBUTING.md.
2. Check that the prerequisites are installed (uv, Docker with a running daemon), install any
   that are missing or tell me exactly how to, and run `uv sync --locked`.
3. Build and run the stack as CONTRIBUTING.md describes: build the images, run the
   migrations, bring the stack up, and confirm /healthz and /readyz respond.
4. Run `uv run task lint` and `uv run task test`.
5. If I use Claude Desktop, follow docs/connect-claude-desktop.md: trust the local CA,
   register the OAuth client, and add the `cfokit` server to claude_desktop_config.json.
   Then build the skill zip it describes (bookkeeper.zip) and tell me where it is.
6. Stop and give me the steps for "Create your account" in CONTRIBUTING.md. When I say I'm
   done, check what I created: query the running stack for my entity and its imported
   transactions, and report counts, not amounts.
7. Report each step's result, and anything you could not do, with the error output.
````

4. **Create your account** in a browser, because it involves signing in. See below.

### Create your account

Signing up, creating your company and importing your books are meant to be one onboarding flow
in the web client, at <http://localhost:8080/app/> once the stack is up. A person creates an
account and signs in with no administrator involved (`IAM-22`), through the identity provider
and never through an agent (`IAM-10`). The flow is specified in
[the design brief](docs/product/design-brief.md) (sign up, create your company, import), and
the client carries onboarding and import (`PLT-24`, `IMP-09`,
[ADR-0051](docs/decisions/0051-books-are-imported-through-the-web-client.md)). When it is done,
come back to Claude Code and say so. It checks the entity and the import against the stack.

**The web client does not have those screens yet.** It has the design-system components and a
heading ([ADR-0049](docs/decisions/0049-cfokit-has-a-web-client.md)), and the realm has no
self-registration. Until the flow lands, use the interim path, which needs Claude Desktop
connected (step 5 of the prompt):

1. **Install the skill.** Quit and reopen Claude Desktop, then **Customize → Skills → `+` →
   Create skill** and upload the `bookkeeper.zip` Claude Code built.
2. **Create your sign-in user.** Open <https://keycloak.localhost:8443>, sign in with the local
   `admin` / `admin` account, and follow
   [step 2 of the Claude Desktop guide](docs/connect-claude-desktop.md#2-create-a-user-to-sign-in-as)
   with the defaults.
3. **Create your company.** In Claude Desktop, sign in as that user when the browser opens, then
   ask it to create an entity. The guide has a sample sentence. Creating the entity makes you its
   owner.
4. **Import books.** Attach a QuickBooks export to the chat and ask the bookkeeper to import it.
   The repo ships no sample export, so use your own or a QuickBooks sample company's.
5. **Go back to Claude Code** and say you're done.

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
Python 3.14, which `uv` installs for you. Only the scripts under `skills/` run on 3.11.

```bash
uv sync              # install everything
uv run task --list   # every command, and what it does
```

**Using Claude Code?** Any Claude Code environment with outbound network access works, cloud or
local, and the agent can run everything below except the steps that need your GitHub
credentials. A cloud session is provisioned automatically by `.claude/hooks/session-start.sh` (`uv`, Python 3.14 and 3.11, Node 24 and pnpm
for the web client, the locked dependencies and a Docker daemon). That hook does nothing locally, so a local session needs `uv`
and Docker installed first. A stack in a cloud session lives inside its container, so you can
exercise it from the session but not from your own machine.

**Hosts it needs to reach** (from the `Dockerfile`, `compose.yaml` and the session hook):

| For | Host |
|---|---|
| `uv` binary and the Python 3.14 and 3.11 downloads | `github.com` and its release-asset hosts (`*.githubusercontent.com`) |
| Node, at the version `web/.nvmrc` pins, for the web client | `nodejs.org` |
| Python packages (`uv sync`, image builds) | `pypi.org`, `files.pythonhosted.org` |
| `python` and `postgres` images | Docker Hub: `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com` |
| the `uv` image used in builds | `ghcr.io` |
| the Keycloak image | `quay.io` and its CDN hosts (`*.quay.io`) |
| pnpm (fetched by corepack), the web client's packages, and `mcp-remote` in the Claude Desktop guide (`npx`) | `registry.npmjs.org` |

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
uv run task lint
uv run task test
```

CI runs these and more on every pull request.
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) is the authority on what has to pass.

**`uv run task test` on its own skips the integration suite**, which is most of it. The whole
suite needs Docker and runs inside the compose network:

```bash
docker compose --profile test run --rm test
```

`CLAUDE.md` explains why it runs there rather than against the stack from the host.

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
