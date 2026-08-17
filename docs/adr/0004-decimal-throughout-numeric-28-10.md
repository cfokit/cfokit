# ADR-0004: `Decimal` in the application, `NUMERIC(28,10)` in the database, floats nowhere

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

## Context

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

## Decision

- **`decimal.Decimal` everywhere in the application.** Never `float`, including in tests and
  fixtures.
- **`NUMERIC(28,10)` for every decimal column.**
- `Decimal` is constructed from `str` or `int`, never from `float`.
- **CI gate 4** enforces both halves: no float storage types in the schema, and no `float` in
  package code. It is implemented and unit-tested, and it has been observed to fail when
  deliberately violated.

Ten decimal places accommodate FX rates and unit prices, not just currency minor units. Eighteen
integer digits is far beyond any plausible balance, and the cost of over-provisioning is
negligible next to the cost of discovering the limit in production.

**Test fixtures are explicitly in scope.** A `float` in a fixture teaches the next contributor
that floats are acceptable here, and it eventually walks into production code.

## Alternatives rejected

### `float` / `double precision`

Fast, native, and the default everywhere. For most software it is correct.

Rejected because binary floating point cannot exactly represent most decimal fractions, so cents
are lost on arithmetic and the error accumulates under summation — which is the dominant operation
in accounting. This is not a tuning problem or a rounding-strategy problem; the representation
cannot hold the values. For a system whose value proposition is correct books it is disqualifying,
and there is no configuration that makes it acceptable.

### Integer minor units (store cents as `BIGINT`)

The strongest alternative, and genuinely common in payments systems — exact, fast, compact, and
immune to the whole class of floating-point error.

Rejected on three grounds.

1. **Currencies do not share an exponent.** JPY has zero minor units, most have two, and some have
   three. "Cents" is not a universal scale, so the integer's meaning depends on the currency of the
   row — an implicit coupling that every read and write must honour.
2. **Not everything monetary is a currency amount.** FX rates and unit prices routinely need more
   precision than two decimal places, so they would need a different representation, and mixed
   representations are where conversion bugs live.
3. **Every boundary becomes a scaling operation.** Reads and writes multiply and divide by a
   power of ten, and a missed scaling is a factor-of-100 error that is silent in code review and
   loud in the books.

The exactness benefit is fully retained by `NUMERIC`, which the database also computes on exactly.

### `NUMERIC` without an explicit precision and scale

Postgres permits unconstrained `NUMERIC`, which stores whatever it is given.

Rejected because it leaves rounding behaviour to whatever each write happens to supply, so two
columns can disagree about how many decimal places they hold and comparisons quietly fail. A
declared scale makes rounding an explicit, uniform decision at the schema level.

### `Decimal` in the application, `float` in the database

Sometimes proposed as a performance compromise, since aggregation happens in the database.

Rejected because the persistence boundary is where precision is lost, so this preserves the
appearance of exactness while discarding the substance. It is strictly worse than using floats
throughout, because the application's `Decimal` types imply a guarantee the storage does not keep.

### Application-level checking only, without a CI gate

Rely on review and on `mypy` to keep floats out.

Rejected because `mypy` has no notion of "this number is money" — `float` is a perfectly valid type
and nothing about it is an error in general. The rule is domain-specific, so it needs a
domain-specific check. Hence CI gate 4, which scans the schema for float storage types and package
code for `float` usage, with a `not-money` escape hatch for the genuinely non-monetary case.

## Consequences

**Accepted costs.**
- `Decimal` arithmetic is slower than native floats. Irrelevant at this workload, and stated here
  so performance is not later mistaken for a reason to revisit.
- `NUMERIC(28,10)` uses more storage than a `BIGINT` of minor units.
- Contributors must construct `Decimal("0.10")` rather than `Decimal(0.10)`, and the latter is a
  subtle bug that looks fine.
- The `float` ban in package code will occasionally catch a legitimate non-monetary value — a
  timeout, a ratio — which is what the `not-money` marker is for.

**Follow-on obligations.**
- CI gate 4, scanning schema and source. **Already implemented** in `scripts/check_money.py`, with
  unit tests proving it catches `REAL`, `MONEY`, `DOUBLE PRECISION`, float annotations, float
  casts, and floats inside generics — and proving it does not flag prose, comments, or identifiers
  that merely contain the word.
- Every decimal column in every migration is `NUMERIC(28,10)`.
- The rounding strategy for display and for allocation remains to be decided; this record fixes
  representation, not rounding policy.
- The Postgres driver, when chosen, must return `NUMERIC` as `Decimal` rather than `float`. This is
  a selection criterion, not a configuration detail.

**Reversal cost. Very high.** Changing representation later means migrating every monetary column
and every value that passed through the application, with no way to recover precision already
lost. This is a one-way door, which is why it is decided before the schema exists.

## Revisit when

- A jurisdiction or instrument requires more than ten decimal places, at which point the scale
  changes — a migration, not a redesign.
- Measured aggregation performance becomes a real bottleneck **and** profiling attributes it to
  `NUMERIC`. The remedy would then be materialised aggregates, not floats.

Nothing about developer convenience or storage cost is a revisit trigger.
