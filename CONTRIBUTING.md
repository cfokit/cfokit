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

## Setting up

You need [`uv`](https://docs.astral.sh/uv/) (not pip, not poetry) and Docker. The code targets
Python 3.14, which `uv` installs for you. Only the scripts under `skills/` run on 3.11.

```bash
uv sync              # install everything
uv run task --list   # every command, and what it does
```

**Nothing to install locally?** Open the repository in a Claude Code cloud session.
`.claude/hooks/session-start.sh` provisions `uv`, Python 3.14 and 3.11, the locked dependencies
and a Docker daemon, so lint, the full suite and the compose stack all run there. The stack
lives inside the session's container, so it can be exercised from the session but not reached
from your own machine.

### Running the stack

```bash
uv run task dev                                    # compose.yaml plus compose.dev.yaml
docker compose --profile migrate run --rm migrate  # create the schema
```

`uv run task dev` applies the development overlay: Postgres is published on `:5432` and logs
every statement. Plain `docker compose up` runs the same stack without it, which is what a
user gets and what CI proves. Migrations are an explicit command and never run on startup.

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

- Work on a branch. Never commit to `main`.
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
