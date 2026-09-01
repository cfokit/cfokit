---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0013: Two dates per transaction, and bitemporality for free

**Requirements served:** `LED-09`, `RPT-11`.

## Context and Problem Statement

Backdating is recording a transaction dated earlier than today, often earlier than a period already
reported on. It is routine and legitimate:

- A receipt surfaces weeks late.
- An accountant posts year-end adjusting entries in February, dated 31 December.
- A feed delivers a settlement date that differs from the posting date.
- An error found in April relates to a February transaction.

Refusing it is not an option — that would forbid adjusting entries, which is standard accrual
practice (`LED-17`, `RPT-19`). So a transaction has two dates that can differ, and `RPT-11` obliges
any report to be reproducible as the books stood at an earlier moment.

The question this record answers is how those two dates are represented and how "as we knew it then"
is queried. What happens when a backdated write lands in a *closed* period is a different question,
answered in [ADR-0030](0030-closed-period-reopen.md).

Two facts make this much smaller than it appears. **Lot tracking is deferred** (`LED-18`, `LED-19`),
so a backdated entry moves period totals and nothing cascades — the severe case of a backdated
acquisition landing earlier in a FIFO queue does not currently exist. And **records are append-only
from posting** (ADR-0007), so nothing is ever overwritten.

## Decision Drivers

* Reproducing a historical report must be a query, not a reconstruction project.
* Reporting correctness must not depend on audit-log retention (`PLT-20`).
* No derived state may be duplicated where the ledger can already answer the question.
* Whatever is chosen must ship in the first migration or it can never be true of historical rows.

## Considered Options

* Two dated columns, with `recorded_at` server-assigned and bitemporality derived from append-only
* A single date, with backdating inferred from an audit-log timestamp
* Snapshot each issued statement rather than reconstructing it
* Version transactions in place, mutating a "current" row

## Decision Outcome

Chosen option: "Two dated columns, with `recorded_at` server-assigned and bitemporality derived from
append-only", because the append-only ledger already *is* the history mechanism, so the bitemporal
property costs one indexed column and no machinery at all.

`LED-09` obliges every transaction to carry both the date the event occurred and the date it was
recorded. `RPT-11` obliges any report to be reproducible as the books stood at an earlier moment.
This record does not restate them; it decides how they are met.

**Bitemporality is free, so nothing is built for it.** Because nothing is ever mutated (ADR-0007),
"the books as we knew them on 15 April" is `WHERE recorded_at <= '2026-04-15'`. No history tables, no
snapshots, no temporal machinery.

That is the whole architectural content of `RPT-11`, and it is why an issued statement records a
`recorded_at` watermark rather than a copy of its own figures. A snapshot would duplicate derivable
state and could disagree with the ledger, with nobody able to say which was authoritative.

`recorded_at` is server-assigned and can never be supplied by a caller. It ships in the first
migration, because a column added later has an unknown value for every existing row and the
bitemporal property could not be reconstructed.

**There is no hard floor.** No date before which writes are refused. A floor would forbid legitimate
late adjustments and would be worked around; making entry into a *closed* period visible is the
property actually wanted, and ADR-0030 provides it.

### Consequences

* Good, because a historical report is a `WHERE` clause rather than a subsystem.
* Good, because "show every entry backdated into a closed period" is a comparison of two columns on
  the row itself.
* Good, because an issued statement references ledger state instead of copying it, so the two can
  never disagree.
* Bad, because there is a second date column on every transaction, indexed for the "as known at"
  query.
* Bad, because every report must accept an optional "as known at" watermark, which is a parameter on
  a surface that would otherwise not need one.
* Neutral, because "statement affected by later activity" needs a representation, which depends on
  the issued-report decision that is still open (`RPT-13`, `RPT-17`).

### Confirmation

`recorded_at` is `NOT NULL` and server-assigned in the first migration, so the property is a schema
constraint rather than a convention — a caller cannot supply it because no write path accepts it.

Reproducibility itself is confirmed by test: the same report over the same watermark returns the same
figures, and two runs differ by exactly the postings recorded between them, which is `RPT-11`'s
stated acceptance.

## Pros and Cons of the Options

### Two dated columns, with `recorded_at` server-assigned

* Good, because the history dimension comes free from a property the ledger already has.
* Good, because it costs one indexed column and no new mechanism.
* Bad, because the column must exist from the first migration, before any query needs it.

### A single date, with backdating inferred from an audit-log timestamp

Avoids a second column: the audit trail already records when the row was written.

* Good, because it stores the fact once, in the place that already exists for it.
* Bad, because it makes a routine property expensive to query. "Show every entry backdated into a
  closed period" becomes a join against the audit log for every report.
* Bad, because it couples reporting correctness to audit-log retention (`PLT-20`), and a retention
  policy should never be able to change what a report says.

### Snapshot each issued statement rather than reconstructing it

Store the rendered figures at issue time, so the historical answer is recorded rather than derived.

* Good, because the historical answer is then certain and cheap, with no dependence on the ledger
  staying reconstructible.
* Bad, because append-only already makes reconstruction exact and free, so snapshots duplicate
  derivable state — with the usual risk that the snapshot and the ledger disagree and nobody knows
  which is authoritative.

### Version transactions in place, mutating a "current" row

The conventional bitemporal design: a current row plus history rows.

* Good, because it is the textbook pattern, and querying the current state needs no watermark.
* Bad, because mutating a current row is precisely what append-only forbids (ADR-0007), and the
  append-only ledger already provides the history dimension without a second mechanism.

## More Information

**Follow-on obligations.**

- `transaction_date` and `recorded_at` on every transaction from the first schema version.
  `recorded_at` is server-assigned and must never be settable by a caller.
- Every report accepts an optional "as known at" watermark; omitted means now.
- An issued statement records a `recorded_at` watermark rather than a copy of its figures.

**Reversal cost. High.** Adding `recorded_at` later would mean every existing row has an unknown
recording time, and the bitemporal property could never be reconstructed for historical data — so the
column ships from the first migration whether or not the queries exist yet.

Related: [ADR-0030](0030-closed-period-reopen.md) decides what happens when a backdated write meets a
closed period.

## Revisit when

- **Lot tracking activates** (`LED-18`). Reintroducing lots reintroduces the cascade: a backdated
  acquisition would need downstream basis recalculation, which is the `rebook` operation currently
  deferred.
- The issued-report decision (`RPT-13`, `RPT-17`) settles, which fixes how "statement affected by
  later activity" is represented.
