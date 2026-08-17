# CFOKit

**Every business needs a CFO. Now every business can have one.**

The open source CFO toolkit — AI agents that handle the work a CFO would do:
bookkeeping, tax preparation, cash flow monitoring, compliance tracking, and financial
reporting.

> **Status: pre-implementation.** The repository is being set up; there is nothing to
> install yet. This README is a placeholder — the product introduction will be derived
> from [`docs/product/vision.md`](docs/product/vision.md).

## Start here

| If you want to | Read |
|---|---|
| Understand what CFOKit is for and who it serves | [`docs/product/vision.md`](docs/product/vision.md) |
| Know what it must do | [`docs/product/requirements.md`](docs/product/requirements.md) |
| Understand what it does to your numbers | [`docs/product/accounting-policy.md`](docs/product/accounting-policy.md) |
| See what is being built next | [`docs/roadmap.md`](docs/roadmap.md) |
| Understand why the architecture is the way it is | [`docs/adr/README.md`](docs/adr/README.md) |
| Contribute code | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Work on this repo with an AI agent | [`CLAUDE.md`](CLAUDE.md) |

## Repository layout

```
packages/    Python distributions (uv workspace)
skills/      Shipped agent skills (SKILL.md bundles)
infra/       OpenTofu for the one maintained cloud target
specs/       Feature specifications — what we will build
docs/        Vision, requirements, roadmap, and decision records
```

## License

MIT. No copyleft component ships in the distributed artifact — see
[ADR-0019](docs/adr/0019-identity-provider-conformance-contract.md).
