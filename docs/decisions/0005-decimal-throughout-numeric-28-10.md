---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0005: `Decimal` in the application, `NUMERIC(28,10)` in the database, floats nowhere

**Requirements served:** `LED-04`, `LED-06`.

## Context and Problem Statement

CFOKit's claim is that the books are correct. Monetary representation is where that claim is
either true or quietly false, and the failure is silent: binary floating point cannot represent
`0.1`, so `0.1 + 0.2` is not `0.3`, and the error compounds through exactly the aggregation that
produces a trial balance. Nothing crashes. The books are simply wrong by amounts too small to
notice until they are not.

Two properties make this worth deciding once, hard:

- **It is invisible in review.** `amount: float` looks like every other annotation.
- **It is unrecoverable after the fact.** Once amounts are stored with lost precision, the
  original values are gone.

A related question is precision. Money is not the only value needing exactness — foreign exchange
rates, unit prices, and allocation percentages all participate in monetary arithmetic, and each
wants more decimal places than currency does.

## Decision Drivers

* Exactness under summation, which is the dominant operation in accounting.
* A representation that covers FX rates and unit prices, not only currency minor units.
* Detectability: the rule is domain-specific, so it needs a domain-specific check rather than
  reliance on review.
* Irreversibility — precision lost at the persistence boundary cannot be recovered, so this must
  be decided before the schema exists.

## Considered Options

* `decimal.Decimal` in the application, `NUMERIC(28,10)` in the database
* `float` / `double precision`
* Integer minor units (store cents as `BIGINT`)
* `NUMERIC` without an explicit precision and scale
* `Decimal` in the application, `float` in the database
* Application-level checking only, without a CI gate

## Decision Outcome

`LED-04` obliges exact amounts and `LED-06` obliges a display scale per commodity. This record
chooses the representation that delivers them.

Chosen option: **`decimal.Decimal` everywhere in the application, `NUMERIC(28,10)` for every
decimal column, floats nowhere.**

- Never `float`, including in tests and fixtures.
- `Decimal` is constructed from `str` or `int`, never from `float`.

Ten decimal places accommodate FX rates and unit prices, not just currency minor units. Eighteen
integer digits is far beyond any plausible balance, and the cost of over-provisioning is
negligible next to the cost of discovering the limit in production.

**Test fixtures are explicitly in scope.** A `float` in a fixture teaches the next contributor
that floats are acceptable here, and it eventually walks into production code.

### Consequences

* Good, because exactness is preserved on both sides of the persistence boundary, and the database
  computes on `NUMERIC` exactly.
* Good, because one representation covers currency, FX rates, unit prices and percentages, so no
  conversion between representations exists to get wrong.
* Bad, because `Decimal` arithmetic is slower than native floats. Irrelevant at this workload, and
  stated here so performance is not later mistaken for a reason to revisit.
* Bad, because `NUMERIC(28,10)` uses more storage than a `BIGINT` of minor units.
* Bad, because contributors must construct `Decimal("0.10")` rather than `Decimal(0.10)`, and the
  latter is a subtle bug that looks fine.
* Bad, because the `float` ban in package code will occasionally catch a legitimate non-monetary
  value — a timeout, a ratio — which is what the `not-money` marker is for.

### Confirmation

**CI gate 4** enforces both halves: no float storage types in the schema, and no `float` in package
code. Implemented in `scripts/check_money.py`, unit-tested, and observed to fail when deliberately
violated. Its tests prove it catches `REAL`, `MONEY`, `DOUBLE PRECISION`, float annotations, float
casts, and floats inside generics — and prove it does not flag prose, comments, or identifiers that
merely contain the word.

## Pros and Cons of the Options

### `Decimal` in the application, `NUMERIC(28,10)` in the database

* Good, because both sides of the boundary hold exact decimal values.
* Good, because a declared scale makes rounding an explicit, uniform decision at the schema level.
* Bad, because it is slower and larger than the alternatives, on both counts irrelevantly so at
  this workload.

### `float` / `double precision`

Fast, native, and the default everywhere. For most software it is correct.

* Good, because it is the fastest and most widely supported option.
* Bad, because binary floating point cannot exactly represent most decimal fractions, so cents are
  lost on arithmetic and the error accumulates under summation — the dominant operation in
  accounting. This is not a tuning problem or a rounding-strategy problem; the representation
  cannot hold the values. For a system whose value proposition is correct books it is
  disqualifying, and there is no configuration that makes it acceptable.

### Integer minor units (store cents as `BIGINT`)

The strongest alternative, and genuinely common in payments systems.

* Good, because it is exact, fast, compact, and immune to the whole class of floating-point error.
* Bad, because **currencies do not share an exponent.** JPY has zero minor units, most have two,
  and some have three. "Cents" is not a universal scale, so the integer's meaning depends on the
  currency of the row — an implicit coupling that every read and write must honor.
* Bad, because **not everything monetary is a currency amount.** FX rates and unit prices routinely
  need more precision than two decimal places, so they would need a different representation, and
  mixed representations are where conversion bugs live.
* Bad, because **every boundary becomes a scaling operation.** Reads and writes multiply and divide
  by a power of ten, and a missed scaling is a factor-of-100 error that is silent in code review and
  loud in the books.
* Neutral, because its exactness benefit is fully retained by `NUMERIC`.

### `NUMERIC` without an explicit precision and scale

Postgres permits unconstrained `NUMERIC`, which stores whatever it is given.

* Good, because it never truncates.
* Bad, because it leaves rounding behavior to whatever each write happens to supply, so two
  columns can disagree about how many decimal places they hold and comparisons quietly fail.

### `Decimal` in the application, `float` in the database

Sometimes proposed as a performance compromise, since aggregation happens in the database.

* Good, because aggregation is fast.
* Bad, because the persistence boundary is where precision is lost, so this preserves the
  appearance of exactness while discarding the substance. It is strictly worse than using floats
  throughout, because the application's `Decimal` types imply a guarantee the storage does not keep.

### Application-level checking only, without a CI gate

Rely on review and on `mypy` to keep floats out.

* Good, because it adds no tooling.
* Bad, because `mypy` has no notion of "this number is money" — `float` is a perfectly valid type
  and nothing about it is an error in general. The rule is domain-specific, so it needs a
  domain-specific check.

## More Information

**Follow-on obligations.**

- CI gate 4, scanning schema and source. **Already implemented** in `scripts/check_money.py`.
- Every decimal column in every migration is `NUMERIC(28,10)`.
- Rounding and allocation policy is a separate question, settled in ADR-0025. This record fixes
  representation and says nothing about when a figure is rounded.
- The Postgres driver must return `NUMERIC` as `Decimal` rather than `float`. This was a selection
  criterion rather than a configuration detail, and `psycopg` was chosen partly on it (ADR-0024).

**Reversal cost. Very high.** Changing representation later means migrating every monetary column
and every value that passed through the application, with no way to recover precision already lost.
This is a one-way door, which is why it is decided before the schema exists.

## Revisit when

- A jurisdiction or instrument requires more than ten decimal places, at which point the scale
  changes — a migration, not a redesign.
- Measured aggregation performance becomes a real bottleneck **and** profiling attributes it to
  `NUMERIC`. The remedy would then be materialized aggregates, not floats.

Nothing about developer convenience or storage cost is a revisit trigger.
