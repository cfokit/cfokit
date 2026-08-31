---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0009: Four layers with a pure booking engine, and hand-written SQL rather than an ORM

**Requirements served:** `NFR-01`, `RPT-08`, `PLT-16`.

## Context and Problem Statement

CFOKit's claim is that the books are correct. Two consequences follow for internal structure.

**Booking semantics must be testable without infrastructure.** The correctness of double-entry
booking is verified differentially against an independent implementation (ADR-0011). If booking
logic can only run with a database attached, every oracle comparison needs fixtures, a live
Postgres, and transaction management — which makes the comparison slow, flaky, and therefore
run rarely. Property-based testing of booking rules becomes impractical for the same reason.

**The SQL that touches the books must be readable.** This is an auditability requirement, not a
preference. When someone asks what statement moved money, the answer has to be a file they can
read, not a query that a library composed at runtime from session state.

Against this, the service has ordinary needs — orchestration, audit logging, entity locking,
grant validation, and two protocol adapters (ADR-0010) — which have to live somewhere that is
neither the pure logic nor the SQL.

## Decision Drivers

* Booking logic must be evaluable with no database attached, or the differential oracle
  (ADR-0011) becomes too slow to run often.
* The statement that touches the books must be readable in a file, for audit.
* Precise control of transaction and statement boundaries, which the deferred trigger (ADR-0006)
  and advisory locking (ADR-0012) both require.
* The guarantee must be static and enforced, not a convention review protects.

## Considered Options

* Four layers with a pure engine and hand-written SQL
* SQLAlchemy or SQLModel as an ORM
* A query builder only, without the ORM layer
* Active Record, or models that persist themselves
* Three layers, folding the engine into the service
* Hexagonal architecture with dependency injection throughout

## Decision Outcome

Chosen option: **four layers, with dependencies pointing strictly downward.**

```
api | mcp     protocol adapters — siblings, must not import each other
service       orchestration, audit logging, entity locking, grant validation
repository    hand-written SQL
engine        pure booking logic
```

- **`engine` is pure.** No I/O, no configuration, no database, no clock, no environment. Every
  input arrives as an argument; every output is a return value.
- **`repository` contains hand-written SQL.** No ORM, no query builder.
- **No layer may be skipped.** An adapter reaching into `repository` has bypassed audit logging,
  entity locking, and grant validation in a single move.

### Consequences

* Good, because booking logic is differentially testable against Beancount with no infrastructure
  (ADR-0011).
* Good, because the SQL that moves money is a file someone can read.
* Bad, because row-to-object mapping is written by hand, and it is tedious.
* Bad, because there is no migration autogeneration. Migrations are hand-written SQL, applied by
  an explicit command (ADR-0004).
* Bad, because contributors who expect an ORM will propose one. That is what this record is for.
* Bad, because the layering adds indirection for operations that would otherwise be a single
  function.

### Confirmation

`import-linter` contracts in `pyproject.toml` encode the layering and the purity of `engine`, so a
violation fails `uv run task lint` rather than depending on review. **Already in place**, and each
contract has been observed to fail when deliberately violated.

## Pros and Cons of the Options

### Four layers with a pure engine and hand-written SQL

* Good, because purity is all-or-nothing and this is the only arrangement that holds it.
* Good, because the constraint is statically enforceable at lint time.
* Bad, because it is the most verbose option, in both mapping code and indirection.

### SQLAlchemy or SQLModel as an ORM

The default choice in Python, and genuinely attractive.

* Good, because it means less mapping code, mature migration tooling via Alembic, relationship
  loading, and a large hiring pool that already knows it.
* Bad, because of **auditability**. The executed SQL is composed at runtime and varies with
  session state, identity-map contents, and lazy-loading configuration. "Read the repository
  module to see what runs against the books" stops being true, and that sentence is load-bearing
  for this project.
* Bad, because **it fights the specific patterns this system depends on.** A deferred constraint
  trigger (ADR-0006) and `pg_advisory_xact_lock` per entity (ADR-0012) both require precise
  control of transaction and statement boundaries. The unit-of-work pattern exists to take that
  control away, so every such site becomes an escape hatch into raw SQL anyway — leaving the ORM's
  cost without its benefit.
* Bad, because of **reporting**. Trial balance and P&L are aggregations over postings across
  arbitrary date ranges. These are written as SQL regardless; an ORM contributes nothing and
  invites accidental N+1 patterns in the journal views.

### A query builder only, without the ORM layer

The apparent middle ground — SQLAlchemy Core, or something like PyPika.

* Good, because it keeps composability and parameter safety without the session machinery.
* Bad, because it retains the objection that mattered while dropping the compensations. There is
  still an indirection between the artifact a reviewer reads and the statement Postgres executes.
* Bad, because parameterisation, the real safety benefit, is available directly from the driver.

### Active Record, or models that persist themselves

* Good, because it is the least code for simple cases, and familiar from other ecosystems.
* Bad, because it makes the pure engine impossible by construction: booking logic and persistence
  become the same object, so booking cannot be evaluated without a database. That forfeits the
  differential oracle, which is the strongest correctness evidence CFOKit has.

### Three layers, folding the engine into the service

Simpler, and the boundary between "pure booking logic" and "orchestration" takes real discipline
to hold.

* Good, because it removes a layer and the indirection that comes with it.
* Bad, because the service layer necessarily touches configuration, the database, and the clock.
  Anything sharing a module with it inherits those dependencies, and the purity property is
  all-or-nothing — a booking function that reads the current date once is no longer differentially
  testable.

### Hexagonal architecture with dependency injection throughout

The full ports-and-adapters treatment, with protocols and injected implementations at every seam.

* Good, because it is the most thorough expression of the same separation.
* Bad, because it is ceremony disproportionate to the problem. The guarantee wanted here is "these
  modules cannot import those modules", and `import-linter` provides exactly that, statically, at
  lint time. Constructor injection everywhere would add indirection to obtain a weaker,
  runtime-only version of the same property.

## More Information

**Follow-on obligations.**

- `import-linter` contracts encoding the layering and the purity of `engine`. **Already in place.**
- The engine takes the current date as a parameter, never reading a clock.
- Adapters stay thin. Logic in an adapter is a defect, because it is then present in one protocol
  and absent from the other.
- Reporting SQL lives in `repository` even when it is aggregate-only and touches no domain object.

**Reversal cost. Very high for the no-ORM half.** Introducing an ORM later means rewriting the
repository layer and abandoning the auditability claim that motivates it. Moderate for the
layering: collapsing layers is mechanical, but it forfeits the differential oracle.

## Revisit when

- The hand-written mapping code becomes a measured source of defects, as opposed to merely
  verbose. Verbosity is the accepted price and is not a revisit trigger.
- Postgres gains a feature that makes the deferred trigger and advisory-lock patterns expressible
  through an ORM without escape hatches.

Neither developer familiarity nor lines of code is a revisit trigger.
