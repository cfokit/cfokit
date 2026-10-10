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
```

Then open **https://localhost:8080/app/**, create your account, and follow getting started: your
QuickBooks export, your company, the import, connecting Claude, and a first question.
[Run CFOKit on your computer](docs/tutorials/run-cfokit-on-your-computer.md) walks through every
step, including trusting the local certificate authority.

[![Getting started, from creating an account to the first question](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/onboarding.gif)](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/onboarding.mp4)

<sub>Recorded by CI from `main`, against this stack, on every push.</sub>

## Start here

| If you want to | Read |
|---|---|
| Understand what CFOKit is for and who it serves | [`docs/product/vision.md`](docs/product/vision.md) |
| Know what it must do | [`docs/product/requirements.md`](docs/product/requirements.md) |
| Understand why the architecture is the way it is | [`docs/decisions/README.md`](docs/decisions/README.md) |
| Run it on your computer, from nothing to your first question | [`docs/tutorials/run-cfokit-on-your-computer.md`](docs/tutorials/run-cfokit-on-your-computer.md) |
| Connect Claude, hosted or on your computer | [`docs/how-to/connect-claude.md`](docs/how-to/connect-claude.md) |
| Understand what an import's comparison with QuickBooks means | [`docs/explanation/reading-an-import.md`](docs/explanation/reading-an-import.md) |
| Contribute code | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Work on this repo with an AI agent | [`CLAUDE.md`](CLAUDE.md) |

## Repository layout

```
src/cfokit/  The Python distribution; one package per capability
skills/      Shipped Agent Skills (SKILL.md bundles)
infra/       OpenTofu for the one maintained cloud target
docs/        User guides, vision, requirements, and decision records
```

## License

Apache License 2.0. It carries an explicit patent grant, makes contributions
inbound-equals-outbound without a separate CLA, and reserves the project's name — see
[ADR-0026](docs/decisions/0026-apache-2-0-as-the-project-license.md). No copyleft component
ships in the distributed artifact ([ADR-0019](docs/decisions/0019-identity-provider-conformance-contract.md)).
