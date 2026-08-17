# Contributing to CFOKit

CFOKit keeps books. A bug here does not degrade an experience — it misstates someone's
financial position. The rules below exist for that reason.

## Before you write code

Read [`CLAUDE.md`](CLAUDE.md). It is the project's constitution and it is binding for
humans and agents alike. Each rule cites the [ADR](docs/adr/README.md) holding its
reasoning; read the cited ADR before proposing a change to a rule.

If a task appears to require breaking a rule, **stop and ask** rather than working around
it. That is not bureaucracy — a workaround in this codebase is how correctness guarantees
quietly stop holding.

## Setup

```bash
uv sync                  # install everything; uv only, not pip or poetry
uv run task lint         # ruff, mypy --strict, import-linter
uv run task test         # full suite
docker compose up        # local production stack, no cloud account needed
uv run task dev          # compose with the development overlay applied
```

## The workflow

Specifications come before implementation. We use
[Spec Kit](https://github.com/github/spec-kit), pinned — see
[`docs/roadmap.md`](docs/roadmap.md) for the version.

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.16.4
```

Then, in your agent: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` →
`/speckit-implement`. Specs land in [`specs/`](specs/).

Two local conventions differ from stock Spec Kit:

1. **We do not use `/speckit-constitution`.** `CLAUDE.md` plus the ADRs are the
   constitution. A second rules document becomes a second source of truth.
2. **Every spec opens with a "Decisions relied on" block** citing ADR numbers. Stock Spec
   Kit starts each feature from empty context and will happily re-argue a settled question;
   this block is what prevents that. Our overridden templates in
   `.specify/templates/overrides/` enforce it.

Requirements carry `REQ-` ids ([`docs/product/requirements.md`](docs/product/requirements.md)).
Cite them in specs and commit messages.

## What "done" means

These are CI gates, not guidelines. Do not write code that assumes an environment they
forbid.

1. `uv run task lint` clean — ruff, `mypy --strict`, import-linter layer contracts.
2. Full suite green against `compose.yaml` **without** the dev overlay and **with no cloud
   credentials present**.
3. Differential test against the Beancount oracle passes, every divergence documented.
4. No float storage types anywhere in the schema.
5. Generated OpenAPI and MCP tool descriptions match what is committed.

Write tests alongside the code, not after. Never report work complete on a red suite.

## Changes that need human review before you proceed

- **Booking semantics** — anything affecting how a transaction is recorded.
- **Authentication** — the issuer contract, audience validation, entity grants.
- **The write path** — locking, idempotency, the audit trail.
- **Adding any runtime dependency.** Runtime dependencies are load-bearing and few; adding
  one is a decision, not a convenience. Ask first.

## Adding a dependency

1. Check the licence, and **verify it currently rather than from memory** — licences change,
   and two of our own ADRs exist because a dependency relicensed.
2. No AGPL, GPL, or other copyleft component may ship in the distributed artifact. Copyleft
   in CI-only tooling is fine.
3. Runtime dependencies need approval before you add them.

## Adding a connector

This is the most contribution-friendly surface in the project, deliberately.

One module per provider under `packages/connectors/src/cfokit/connectors/providers/`, all
behind the same protocol. Import provider SDKs inside the function that needs them, never at
module scope, so the package stays importable without credentials present. Do not make your
provider structural — if adding it requires changing the protocol, say so in the PR and
expect a discussion.

## Architecture decisions

If you make a decision future work should be bound by, propose an ADR rather than burying it
in a code comment. Copy [`docs/adr/0000-template.md`](docs/adr/0000-template.md) to the next
free number.

The **Alternatives rejected** section is mandatory and is the most important part of the
file. An ADR without it does not prevent re-litigation, which is the main thing an ADR is
for. "Didn't feel right" is not a rejection reason; cite specifics.

ADRs are immutable once accepted. Fix typos; never rewrite reasoning. A changed mind is a
new ADR that supersedes the old one.

## Commits and pull requests

- One logical change per commit; imperative subject line.
- Cite the `REQ-` or `ADR-` id when the change implements or follows one.
- State in the PR which CI gates you ran locally, and flag anything you could not verify.
- If part of the work is incomplete or blocked, say so explicitly. Scaling work down is a
  maintainer's call.
