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

1. **Fork** [`cfokit/cfokit`](https://github.com/cfokit/cfokit) on GitHub.
2. **Run [Claude Code](https://claude.com/claude-code)** in an empty directory, cloud or local.
3. **Paste this prompt** (replace `<you>` with your GitHub username):

````text
I forked cfokit/cfokit to github.com/<you>/cfokit. Set me up to contribute:

1. Clone my fork, add cfokit/cfokit as the `upstream` remote, and cd into it.
2. Read CLAUDE.md and CONTRIBUTING.md.
3. Check that the prerequisites are installed (git, uv, Docker with a running daemon),
   install any that are missing or tell me exactly how to, and run `uv sync --locked`.
4. Build and run the stack as CONTRIBUTING.md describes: build the images, run the
   migrations, bring the stack up, and confirm /healthz and /readyz respond.
5. Run `uv run task lint` and `uv run task test`.
6. Report each step's result, and anything you could not do, with the error output.

Do not commit or push anything.
````

Claude Code then does the rest. After that, ask it to make your change on a branch of your fork,
and to open the pull request against `cfokit/cfokit` when you are ready
([Opening a pull request](#opening-a-pull-request)). A local session needs `git` and, for the
fork-aware steps, the [`gh`](https://cli.github.com/) CLI or a GitHub connector; a cloud session
is provisioned for you (see [Setting up](#setting-up)).

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
local, and the agent can run everything below for you. A cloud session is provisioned
automatically by `.claude/hooks/session-start.sh` (`uv`, Python 3.14 and 3.11, Node 24 and pnpm
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
