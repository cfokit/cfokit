---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0028: Hand-written SQL in the repository layer, rather than an ORM

**Requirements served:** `RPT-08`, `PLT-16`.

## Context and Problem Statement

[ADR-0008](0008-layered-architecture-pure-engine.md) establishes a `repository` layer between the
service and the database. It does not say what that layer is written in, and the Python default —
SQLAlchemy — is strong enough that the absence of a decision would be read as an oversight.

**The SQL that touches the books must be readable.** This is an auditability requirement, not a
preference. `RPT-08` obliges any figure on a statement to resolve to the postings that produced it,
and `PLT-16` obliges an entity to retrieve a complete record of every change to its books. When
someone asks what statement moved money, the answer has to be a file they can read, not a query a
library composed at runtime from session state.

There is a second constraint that is easy to miss until it bites. The ledger depends on two Postgres
mechanisms that require precise control of transaction and statement boundaries: a deferred
constraint trigger checked at `COMMIT` (ADR-0006), and `pg_advisory_xact_lock` taken per entity
(ADR-0011). Both are hostile to an abstraction whose purpose is to manage those boundaries on your
behalf.

## Decision Drivers

* An auditor, or an engineer answering an auditor, must be able to read the statement that ran.
* Precise control of transaction and statement boundaries, which the deferred trigger (ADR-0006) and
  advisory locking (ADR-0011) both require.
* Reporting is aggregation over postings across arbitrary date ranges, which is SQL regardless of
  what sits above it.
* Whatever is chosen must not quietly become a second definition of behaviour.

## Considered Options

* Hand-written SQL in the repository layer
* SQLAlchemy or SQLModel as an ORM
* A query builder only, without the ORM layer

## Decision Outcome

Chosen option: "Hand-written SQL in the repository layer", because the auditability claim depends on
the executed statement being the statement someone can read, and every abstraction over it weakens
that claim without removing the SQL.

> `repository` contains hand-written SQL. No ORM, no query builder.

Migrations are hand-written SQL too, applied by an explicit command and never at startup (ADR-0004).

### Consequences

* Good, because the SQL that moves money is a file someone can read, which is what makes the
  auditability claim true rather than argued.
* Good, because the deferred trigger and advisory-lock patterns are expressed directly, with no
  escape hatch through an abstraction that exists to hide them.
* Good, because reporting SQL — trial balance, P&L, journal views — is written once, in the place it
  would have ended up anyway.
* Bad, because row-to-object mapping is written by hand, and it is tedious.
* Bad, because there is no migration autogeneration.
* Bad, because contributors who expect an ORM will propose one. That is what this record is for.

### Confirmation

`import-linter` keeps SQL confined to `repository` by keeping every other layer from importing the
driver, and that runs inside `uv run task lint` (ADR-0008). CI gate 4 (`uv run task check-money`)
additionally reads the schema directly, which is only possible because the schema is hand-written
DDL rather than generated (ADR-0005).

**Nothing gates the absence of an ORM.** Adding SQLAlchemy to `pyproject.toml` would fail no check —
it is caught by review, and by the rule in `CLAUDE.md` that every runtime dependency is a decision.

## Pros and Cons of the Options

### Hand-written SQL in the repository layer

* Good, because the artifact a reviewer reads is the statement Postgres executes.
* Good, because it imposes no constraints on transaction and statement boundaries.
* Bad, because mapping and migrations are both manual, which is the accepted price.

### SQLAlchemy or SQLModel as an ORM

The default choice in Python, and genuinely attractive.

* Good, because it means less mapping code, mature migration tooling via Alembic, relationship
  loading, and a large hiring pool that already knows it.
* Bad, because of **auditability**. The executed SQL is composed at runtime and varies with session
  state, identity-map contents, and lazy-loading configuration. "Read the repository module to see
  what runs against the books" stops being true, and that sentence is load-bearing for this project.
* Bad, because **it fights the specific patterns this system depends on.** A deferred constraint
  trigger (ADR-0006) and `pg_advisory_xact_lock` per entity (ADR-0011) both require precise control
  of transaction and statement boundaries. The unit-of-work pattern exists to take that control
  away, so every such site becomes an escape hatch into raw SQL anyway — leaving the ORM's cost
  without its benefit.
* Bad, because of **reporting**. Trial balance and P&L are aggregations over postings across
  arbitrary date ranges. These are written as SQL regardless; an ORM contributes nothing and invites
  accidental N+1 patterns in the journal views.

### A query builder only, without the ORM layer

The apparent middle ground — SQLAlchemy Core, or something like PyPika.

* Good, because it keeps composability and parameter safety without the session machinery, and does
  not fight transaction control the way the full ORM does.
* Bad, because it retains the objection that mattered while dropping the compensations. There is
  still an indirection between the artifact a reviewer reads and the statement Postgres executes.
* Bad, because parameterisation, the real safety benefit, is available directly from the driver.

## More Information

**Follow-on obligations.**

- Reporting SQL lives in `repository` even when it is aggregate-only and touches no domain object.
- Migrations are hand-written SQL, applied by an explicit command (ADR-0004).
- Parameterisation is always via the driver. String interpolation into SQL is never acceptable, and
  `ruff`'s bandit rules are configured to catch it.

**Reversal cost. Very high.** Introducing an ORM later means rewriting the repository layer and
abandoning the auditability claim that motivates it.

Related: [ADR-0008](0008-layered-architecture-pure-engine.md) establishes the layer this record fills
in; ADR-0003 fixes Postgres as the only backend, which is what makes hand-written SQL portable enough
to be practical.

## Revisit when

- The hand-written mapping code becomes a measured source of defects, as opposed to merely verbose.
  Verbosity is the accepted price and is not a revisit trigger.
- Postgres gains a feature that makes the deferred trigger and advisory-lock patterns expressible
  through an ORM without escape hatches.

Neither developer familiarity nor lines of code is a revisit trigger.
