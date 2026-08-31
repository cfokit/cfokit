---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0013: Every transaction carries two dates; backdating is permitted but never silent

**Requirements served:** `LED-09`, `RPT-11`.

## Context

Backdating is recording a transaction dated earlier than today, often earlier than a period already
reported on. It is routine and legitimate:

- A receipt surfaces weeks late.
- An accountant posts year-end adjusting entries in February, dated 31 December.
- A feed delivers a settlement date that differs from the posting date.
- An error found in April relates to a February transaction.

It is also the mechanism by which a figure someone has already relied on changes underneath them.

**Two things have made this decision much smaller than it was when the backlog was written.**

First, **lot tracking is deferred** (LED-18, LED-19). The severe case was a backdated *acquisition* landing
earlier in the FIFO queue and retroactively changing which lot every later disposal consumed —
invalidating every subsequent gain calculation, which is what ADR-0003 meant by "backdated entries
can invalidate the cost basis of every later disposal". With no lots, nothing cascades. A backdated
entry moves period totals and stops there.

Second, **records are append-only from posting** (ADR-0007). Nothing is ever overwritten, which
turns out to make the hard part of this problem nearly free — see below.

The residual question is not whether to permit backdating. Refusing it would forbid adjusting
entries, which is standard accounting practice. It is: **how does a reader tell that it happened,
and what happens to figures already reported?**

## Decision

### 1. Two dates, always

Every transaction records both:

| Date | Meaning |
|---|---|
| **Transaction date** | When it economically occurred. What reports are periodised by. |
| **Recorded at** | When it entered the books. System-assigned, never caller-supplied. |

Backdating is simply these diverging. Because both are stored, **every backdated entry is
self-identifying** — no separate flag, no heuristic, no way to record one without it being evident.

The danger was never backdating. It was *undetectable* backdating.

### 2. Bitemporal reporting, which append-only gives us almost free

Any report can be rendered along either axis: **as of** a transaction date, and **as known at** a
recording time.

This is the part worth noticing. Because nothing is ever mutated (ADR-0007), "the books as we knew
them on 15 April" is just `WHERE recorded_at <= '2026-04-15'`. No history tables, no snapshots, no
temporal machinery — append-only *is* the mechanism. It costs one indexed column.

It also answers, precisely, the question that started this: *what did we tell the bank in March*
versus *what do we now believe about March*.

### 3. Backdating is permitted, but crossing a close is never silent

- Into an **open** period: permitted freely, no ceremony. This is ordinary bookkeeping.
- Into a **closed** period: permitted, but requires explicit acknowledgement from the caller, writes
  an `audit_log` row marked as crossing a close, and **flags any previously-issued statement
  covering that period as affected**.

Period close stays advisory (ADR-0007). It does not block the write; it determines whether the write
is remarkable.

### 4. Reversal dating follows the period state

When a posted entry is reversed:

- Original period **open** → the reversal takes the original transaction date. The period is
  restated, which is correct because nothing has been reported yet.
- Original period **closed** → the reversal defaults to the **current open period**, so prior
  reported figures stand and the correction appears where it was discovered. Restating the original
  period instead is available, and is a close-crossing under rule 3.

This is the prospective-versus-restatement choice that accounting makes routinely, with the default
set to the less surprising option.

### 5. No hard floor

There is no date before which writes are refused. A floor would forbid legitimate late adjustments
and would be worked around. Rule 3 makes crossings visible, which is the property actually wanted.

## Alternatives rejected

### Forbid backdating entirely

Simplest rule, and it makes every period final the moment it closes.

Rejected because it forbids standard accounting practice. Year-end adjusting entries are dated to
the year they adjust and posted afterwards; that is how accrual accounting works, and CFOKit will
need accrual (LED-17, RPT-19). A ledger that cannot express an adjusting entry is not a ledger.

### Permit it freely, with no distinction for closed periods

What QuickBooks does by default, since its closing date is opt-in.

Rejected because it means a statement already given to a lender can change with nothing recorded
about the fact. The write itself is legitimate; the silence is not. Rule 3 costs one acknowledgement
and an audit row.

### Hard-lock closed periods, requiring an explicit reopen

Sage Intacct's model, and defensible: reopening is deliberate, audited, and rare.

Rejected because ADR-0007 already made close advisory on the grounds that append-only posting — not
the lock — is what guarantees auditability. Adding a hard lock now would either duplicate that
guarantee or contradict the reasoning for making close soft. It remains the obvious upgrade if
acknowledgements turn out to be routinely clicked through.

### A single date, with backdating inferred from an audit-log timestamp

Avoids a second column: the audit trail already records when the row was written.

Rejected because it makes a routine property expensive to query. "Show every entry backdated into a
closed period" becomes a join against the audit log for every report, rather than a comparison of
two columns on the row itself. It also couples reporting correctness to audit-log retention
(PLT-20), and a retention policy should never be able to change what a report says.

### Snapshot each issued statement rather than reconstructing it

Store the rendered figures at issue time, so the historical answer is recorded rather than derived.

Rejected because append-only already makes reconstruction exact and free, so snapshots would
duplicate derivable state — with the usual risk that the snapshot and the ledger disagree and
nobody knows which is authoritative. Storing a *reference* to the ledger state (a `recorded_at`
watermark) achieves the same end without that risk, and is what an issued statement records.

### Version transactions in place, mutating a "current" row

The conventional bitemporal design: a current row plus history rows.

Rejected on ADR-0007 grounds. Mutating a current row is precisely what append-only forbids, and the
append-only ledger already provides the history dimension without a second mechanism.

## Consequences

**Accepted costs.**
- A second date column on every transaction, indexed for the "as known at" query.
- Callers must acknowledge close-crossing writes, so the tool contract and the REST API both grow a
  parameter (ADR-0014).
- The reversal-dating default will occasionally be wrong for a user's intent, so it must be
  overridable — and overriding it is itself a close-crossing.
- "Statement affected by later activity" needs a representation, which depends on the issued-report
  decision that is still open (RPT-13, RPT-17).

**Follow-on obligations.**
- `transaction_date` and `recorded_at` on every transaction from the first schema version.
  `recorded_at` is server-assigned and must never be settable by a caller.
- Every report accepts an optional "as known at" watermark; omitted means now.
- Close-crossing writes carry a distinguishable `audit_log` marker, so "what changed in a closed
  period" is a query rather than an investigation.
- A stable error `code` for a close-crossing attempted without acknowledgement (ADR-0015).
- The bookkeeper skill surfaces close-crossings to the user rather than acknowledging on their
  behalf. An agent that auto-acknowledges defeats the rule (BKP-12).
- **Revisit this record when lot tracking activates** (LED-18). Reintroducing lots reintroduces the
  cascade, and rule 3 alone will not be sufficient — a backdated acquisition would then need
  downstream basis recalculation, which is the `rebook` operation currently deferred.

**Reversal cost. Low for the policy, high for the two-date model.** Rules 3 to 5 are service-layer
behaviour and can change. Adding `recorded_at` later would mean every existing row has an unknown
recording time, and the bitemporal property could never be reconstructed for historical data — so
the column ships from the first migration whether or not the queries exist yet.

## Revisit when

- **Lot tracking activates.** Named above; this is the concrete trigger.
- Close-crossing acknowledgements become routine rather than exceptional, which would mean the
  signal has been trained away and a hard lock is warranted after all.
- A jurisdiction requires restatement disclosure that rule 4's default does not satisfy.
