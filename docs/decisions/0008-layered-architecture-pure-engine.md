---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0008: Four layers, with a pure booking engine at the bottom

**Requirements served:** `NFR-01`, `RPT-08`.

## Context and Problem Statement

CFOKit's claim is that the books are correct, and the evidence for that claim is a differential
comparison against an independent implementation (ADR-0010).

**That evidence is only affordable if booking semantics are testable without infrastructure.** If
booking logic can only run with a database attached, every oracle comparison needs fixtures, a live
Postgres, and transaction management — which makes the comparison slow, flaky, and therefore run
rarely. Property-based testing of booking rules becomes impractical for the same reason. A
correctness gate that is expensive to run is a correctness gate that stops running.

Against this, the service has ordinary needs — orchestration, audit logging, entity locking, grant
validation, and two protocol adapters (ADR-0009) — which have to live somewhere that is neither the
pure logic nor the SQL.

The question this record answers is what the vertical stack looks like and what may import what.
Whether the persistence layer uses an ORM is a separate decision, held in
[ADR-0028](0028-hand-written-sql-no-orm.md).

## Decision Drivers

* Booking logic must be evaluable with no database attached, or the differential oracle (ADR-0010)
  becomes too slow to run often.
* Purity is all-or-nothing: a booking function that reads a clock once is no longer differentially
  testable.
* Every write must pass through audit logging, entity locking, and grant validation, with no route
  around them.
* The guarantee must be static and enforced, not a convention review protects.

## Considered Options

* Four layers, with a pure engine at the bottom and dependencies pointing strictly downward
* Three layers, folding the engine into the service
* Active Record, or models that persist themselves
* Hexagonal architecture with dependency injection throughout

## Decision Outcome

Chosen option: "Four layers, with a pure engine at the bottom and dependencies pointing strictly
downward", because it is the only arrangement that holds engine purity, and purity is what makes the
correctness evidence cheap enough to run continuously.

```
api | mcp     protocol adapters — siblings, must not import each other
service       orchestration, audit logging, entity locking, grant validation
repository    persistence
engine        pure booking logic
```

- **`engine` is pure.** No I/O, no configuration, no database, no clock, no environment. Every input
  arrives as an argument; every output is a return value.
- **No layer may be skipped.** An adapter reaching into `repository` has bypassed audit logging,
  entity locking, and grant validation in a single move.
- **Adapters are siblings and must not import each other.** ADR-0009 makes both thin wrappers over
  the service; a dependency between them would make one adapter's behaviour depend on the other's.

### Consequences

* Good, because booking logic is differentially testable against Beancount with no infrastructure
  (ADR-0010).
* Good, because there is exactly one route to a write, so the service-layer obligations cannot be
  bypassed by construction.
* Good, because the boundary is statically enforceable at lint time rather than by review.
* Bad, because the layering adds indirection for operations that would otherwise be a single
  function.
* Bad, because engine purity means the current date is a parameter at every call site that needs it,
  which is more verbose than reading a clock.

### Confirmation

`import-linter` contracts in `pyproject.toml` encode the layering and the purity of `engine`, so a
violation fails `uv run task lint` rather than depending on review. **Already in place**, and each
contract has been observed to fail when deliberately violated.

`scripts/check_async.py` additionally keeps async constructs out of every ledger layer except the MCP
adapter (ADR-0024), which is what stops an `await` appearing mid-transaction.

## Pros and Cons of the Options

### Four layers, with a pure engine at the bottom

* Good, because purity is all-or-nothing and this is the only arrangement that holds it.
* Good, because the constraint is statically enforceable at lint time.
* Bad, because it is the most verbose option, in indirection and in threaded-through parameters.

### Three layers, folding the engine into the service

Simpler, and the boundary between "pure booking logic" and "orchestration" takes real discipline to
hold.

* Good, because it removes a layer and the indirection that comes with it.
* Bad, because the service layer necessarily touches configuration, the database, and the clock.
  Anything sharing a module with it inherits those dependencies, and the purity property is
  all-or-nothing — a booking function that reads the current date once is no longer differentially
  testable.

### Active Record, or models that persist themselves

* Good, because it is the least code for simple cases, and familiar from other ecosystems.
* Bad, because it makes the pure engine impossible by construction: booking logic and persistence
  become the same object, so booking cannot be evaluated without a database. That forfeits the
  differential oracle, which is the strongest correctness evidence CFOKit has.

### Hexagonal architecture with dependency injection throughout

The full ports-and-adapters treatment, with protocols and injected implementations at every seam.

* Good, because it is the most thorough expression of the same separation, and would make the engine
  testable against in-memory adapters.
* Bad, because it is ceremony disproportionate to the problem. The guarantee wanted here is "these
  modules cannot import those modules", and `import-linter` provides exactly that, statically, at
  lint time. Constructor injection everywhere would add indirection to obtain a weaker, runtime-only
  version of the same property.

## More Information

**Follow-on obligations.**

- `import-linter` contracts encoding the layering and the purity of `engine`. **Already in place.**
- The engine takes the current date as a parameter, never reading a clock.
- Adapters stay thin. Logic in an adapter is a defect, because it is then present in one protocol and
  absent from the other.
- Allocation lives in the engine, which is what makes it property-testable (ADR-0025).

**Reversal cost. Moderate.** Collapsing layers is mechanical, but it forfeits the differential
oracle, which is the correctness evidence the whole project rests on.

Related: [ADR-0028](0028-hand-written-sql-no-orm.md) decides what `repository` is written in.

## Revisit when

- A capability genuinely cannot be expressed without the engine reaching for I/O, which would mean
  the layer boundary is drawn in the wrong place rather than that purity should be relaxed.
- The differential oracle is retired, which would remove the main reason purity is worth its cost.

Neither developer familiarity nor lines of code is a revisit trigger.
