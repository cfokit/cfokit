# CFOKit

**Open source books your agent keeps.**

A CFO owns capital, cash, and the plan. Producing the books they work from is a bookkeeper's
job and a controller's job. CFOKit does that part, as a kit of Agent Skills running against a
double-entry ledger you own.

Transactions arrive from bank, card, and payment-processor feeds and are assigned by stored
rules you approve, so every posting traces back to the rule that produced it. Periods close on
a schedule. Corrections are reversing entries rather than edits, so the history is complete by
construction. The books are queryable over MCP and a documented HTTP API, which means the
questions do not have to be anticipated in advance.

It runs on a laptop with no cloud account. The hosted service is the same software, operated
under third-party audit.

## Run it locally

Needs [Docker](https://docs.docker.com/get-docker/) and nothing else — no cloud account.

```bash
docker compose up -d --wait                       # the stack: Postgres, identity provider, REST, MCP
docker compose --profile migrate run --rm migrate # create the schema; never runs on startup
curl -s http://localhost:8080/readyz              # "ready" once the database is reachable and migrated
```

The REST API listens on `:8080` and the MCP endpoint on `:8081`. This is the real thing, not a
demo: data lives in a named volume, and `docker compose down -v` destroys it.

To connect Claude Desktop, create a user and install the bookkeeper skill, continue with
[`docs/connect-claude-desktop.md`](docs/connect-claude-desktop.md). Working on the code instead?
See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Start here

| If you want to | Read |
|---|---|
| Understand what CFOKit is for and who it serves | [`docs/product/vision.md`](docs/product/vision.md) |
| Know what it must do | [`docs/product/requirements.md`](docs/product/requirements.md) |
| Understand why the architecture is the way it is | [`docs/decisions/README.md`](docs/decisions/README.md) |
| Run it locally and connect Claude Desktop | [`docs/connect-claude-desktop.md`](docs/connect-claude-desktop.md) |
| Contribute code | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Work on this repo with an AI agent | [`CLAUDE.md`](CLAUDE.md) |

## Repository layout

```
src/cfokit/  The Python distribution; one package per capability
skills/      Shipped Agent Skills (SKILL.md bundles)
infra/       OpenTofu for the one maintained cloud target
docs/        Vision, requirements, and decision records
```

## License

Apache License 2.0. It carries an explicit patent grant, makes contributions
inbound-equals-outbound without a separate CLA, and reserves the project's name — see
[ADR-0026](docs/decisions/0026-apache-2-0-as-the-project-license.md). No copyleft component
ships in the distributed artifact ([ADR-0019](docs/decisions/0019-identity-provider-conformance-contract.md)).
