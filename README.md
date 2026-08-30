# CFOKit

**The open source CFO toolkit.**

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

> **Status: pre-implementation.** The repository holds decisions, requirements, and the test
> gates that enforce them. There is nothing to install yet. Positioning here is derived from
> [`docs/product/vision.md`](docs/product/vision.md); change it there first.

## Start here

| If you want to | Read |
|---|---|
| Understand what CFOKit is for and who it serves | [`docs/product/vision.md`](docs/product/vision.md) |
| Know what it must do | [`docs/product/requirements.md`](docs/product/requirements.md) |
| Understand why the architecture is the way it is | [`docs/decisions/README.md`](docs/decisions/README.md) |
| Contribute code | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Work on this repo with an AI agent | [`CLAUDE.md`](CLAUDE.md) |

## Repository layout

```
packages/    Python distributions (uv workspace)
skills/      Shipped Agent Skills (SKILL.md bundles)
infra/       OpenTofu for the one maintained cloud target
docs/        Vision, requirements, and decision records
```

## License

MIT. No copyleft component ships in the distributed artifact — see
[ADR-0020](docs/decisions/0020-identity-provider-conformance-contract.md).
