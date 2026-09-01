# Contributing to CFOKit

CFOKit keeps books. A bug here does not degrade an experience — it misstates someone's
financial position. The rules below exist for that reason.

## Before you write code

Read [`CLAUDE.md`](CLAUDE.md). It is the project's constitution and it is binding for
humans and agents alike. Each rule cites the [ADR](docs/decisions/README.md) holding its
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

`CLAUDE.md` plus the decision records are the constitution. A second rules document becomes a
second source of truth.

Requirements carry stable domain-prefixed ids ([`docs/product/requirements.md`](docs/product/requirements.md)).
Cite them in commit messages. Derivation runs vision → requirements → decision records → the
rules in `CLAUDE.md`; requirements never cite a decision record.

There is no roadmap file and no specifications directory. Work sequencing lives in GitHub
Milestones and Projects. Whether the project adopts a specification workflow is undecided
([ADR-0001](docs/decisions/0001-documentation-structure.md)).

## What "done" means

These are CI gates, not guidelines. Do not write code that assumes an environment they
forbid.

1. `uv run task lint` clean — ruff, `mypy --strict`, import-linter layer contracts.
2. Full suite green against `compose.yaml` **without** the dev overlay and **with no cloud
   credentials present**.
3. **Deferred, not running.** The Beancount differential oracle activates with `LED-18`
   ([ADR-0010](docs/decisions/0010-beancount-as-test-oracle.md)); until then correctness rests
   on the layers below.
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

## Adding a provider

Bank feeds, payment processors and delivery channels are the most contribution-friendly surface
in the project, deliberately — `NFR-12` makes third-party contribution a requirement rather than
a courtesy.

**The package that will hold them does not exist yet.** There was a `connectors` package
containing no code, and it was removed rather than renamed: "connectors" names a mechanism rather
than a capability, and bank feeds, payment processing and transactional email are not one
capability (ADR-0031). What they split into is decided when the first is built.

Two rules will apply whatever the package is called. Import provider SDKs inside the function that
needs them, never at module scope, so the package stays importable without credentials present. And
do not make your provider structural — if adding it requires changing the protocol, say so in the PR
and expect a discussion.

## Architecture decisions

If you make a decision future work should be bound by, propose an ADR rather than burying it
in a code comment. Copy [`docs/decisions/adr-template.md`](docs/decisions/adr-template.md) to the next
free number.

The **Pros and Cons of the Options** section is mandatory and is the most important part of
the file. MADR marks it optional; here it is not. An ADR that names alternatives without
refuting each one does not prevent re-litigation, which is the main thing an ADR is for.
"Didn't feel right" is not a rejection reason; cite specifics.

**One decision per record.** A record may state a decision in several clauses when they stand
or fall together. The test: could one clause be superseded without reopening the others? If it
could, they are two decisions — write two records. A title containing "and" is a signal to
apply the test, not a violation by itself.

`uv run task check-decisions` checks the mechanical parts — frontmatter, mandatory sections,
requirement ids, and index agreement — before CI does. Run it after writing a record.

ADRs are immutable once accepted. Fix typos; never rewrite reasoning. A changed mind is a
new ADR that supersedes the old one.

## Commits and pull requests

- One logical change per commit; imperative subject line.
- Cite the requirement or `ADR-` id when the change implements or follows one.
- State in the PR which CI gates you ran locally, and flag anything you could not verify.
- If part of the work is incomplete or blocked, say so explicitly. Scaling work down is a
  maintainer's call.
