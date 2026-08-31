---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0013: Two dates per transaction; a closed period is reopened, never overridden

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

`LED-09` obliges every transaction to carry both the date the event occurred and the date it was
recorded, and permits backdating into an open period provided it is never silent. `RPT-11` obliges
any report to be reproducible as the books stood at an earlier moment. `LED-11` obliges a closed
period to admit no posting except through a recorded reopening. This record does not restate those.
It decides how they are met, and settles what happens at the boundary.

### 1. Bitemporality is free, so nothing is built for it

Because nothing is ever mutated (ADR-0007), "the books as we knew them on 15 April" is
`WHERE recorded_at <= '2026-04-15'`. No history tables, no snapshots, no temporal machinery — the
append-only ledger *is* the mechanism, and it costs one indexed column.

This is the whole architectural content of `RPT-11`, and it is why an issued statement records a
`recorded_at` watermark rather than a copy of its own figures. A snapshot would duplicate derivable
state and could disagree with the ledger, with nobody able to say which was authoritative.

`recorded_at` is server-assigned and can never be supplied by a caller. It ships in the first
migration, because a column added later has an unknown value for every existing row and the
bitemporal property could not be reconstructed.

### 2. Entering a closed period is a reopen, not a flag

An earlier version of this record let a caller post into a closed period by passing an
acknowledgement parameter. That was wrong, and the reasoning was circular: it rested on ADR-0007
having made close advisory, while ADR-0007 rested on backdating being surfaced here. Neither
justified the position on its own.

A closed period is reopened, or it is not written to. The reopen is a distinct event carrying who
did it, when, and why, and the period is closed again when the work is done.

The enterprise ledgers settled here long ago. NetSuite's closed state admits no
general-ledger-impacting change from any user, administrators included, and reopening records a
justification. Sage Intacct refuses any posting dated at or before a closed period end and requires
the books to be reopened, with access restricted to the controller. Auditing standards point the
same way: journal-entry testing is mandatory in every audit precisely because entries at and after
period end are the management-override fraud vector.

### 3. The reopen is a human capability, never a skill's

**This is the load-bearing rule, and it is the one that survives having a single user.**

Most CFOKit entities will have one person. Segregation of duties is then impossible and `IAM-17`
says the system must not raise it. So the control that matters is not person against person — it is
person against agent. A skill's principal never holds the capability to reopen a period. The agent
can draft, it can post into an open period, and when it meets a closed one it must ask.

This is what the acknowledgement parameter could not do. Its own follow-on obligation conceded as
much: *"an agent that auto-acknowledges defeats the rule."* A capability the agent does not hold
cannot be auto-acknowledged.

### 4. One gesture, not a workflow

`LED-11` requires a recorded reopening. It does not require ceremony, and `NFR-19` requires a
non-accountant to complete a month-end close unaided.

So the operator sees one question — *that receipt is dated 14 March, which you closed; reopen March
to post it?* — and one confirmation. Behind it the system records the reopen, the posting, and an
automatic re-close. The period is never left silently open, which is the state an operator would
otherwise have to understand in order to manage.

Copying enterprise ceremony wholesale would import the cost without the control: Intacct restricts
reopening to the controller, and for a sole operator that is the same person as the bookkeeper.

### 5. Reversal dating follows the period state

- Original period **open** → the reversal takes the original transaction date. The period is
  restated, which is correct because nothing has been reported yet.
- Original period **closed** → the reversal defaults to the **current open period**, so prior
  reported figures stand and the correction appears where it was discovered. Restating the original
  period instead is available, and is a reopen under rule 2.

This is the prospective-versus-restatement choice accounting makes routinely, with the default set
to the less surprising option.

### 6. No hard floor

There is no date before which writes are refused. A floor would forbid legitimate late adjustments
and would be worked around. Rule 2 makes entry visible, which is the property actually wanted.

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

**This was rejected here and is now the decision.** Kept, because the reason the rejection failed is
worth more than the rejection was.

Sage Intacct's model, and defensible: reopening is deliberate, audited, and rare. It was rejected on
the grounds that ADR-0007 had already made close advisory, since append-only posting rather than the
lock is what guarantees auditability, so a hard lock would either duplicate that guarantee or
contradict the reasoning for making close soft.

The flaw is that the two records leaned on each other. ADR-0007 made close soft partly because
backdating would be surfaced here; this record declined to harden it because ADR-0007 had made it
soft. Neither argument stood alone, and the pair read as settled only because each pointed at the
other.

What the reasoning also missed is that append-only and a hard close answer different questions.
Append-only guarantees that nothing is destroyed. It says nothing about whether entering a closed
period is a deliberate, evidenced act — and that is the question an examiner asks. Under `NFR-18` a
control that cannot be evidenced does not count as implemented, and a parameter on a write is not
evidence of a control; a reopen with an actor, a reason and a re-close is.

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
- Reopening is a capability the tool contract and the REST API both expose, and it is withheld from
  skill principals (ADR-0014). A skill meeting a closed period must ask a person.
- An operator posting a late receipt into a closed period pays one confirmation. That is more than
  no ceremony and less than the enterprise workflow, and it is the compromise this record makes.
- The reversal-dating default will occasionally be wrong for a user's intent, so it must be
  overridable — and overriding it is itself a close-crossing.
- "Statement affected by later activity" needs a representation, which depends on the issued-report
  decision that is still open (RPT-13, RPT-17).

**Follow-on obligations.**
- `transaction_date` and `recorded_at` on every transaction from the first schema version.
  `recorded_at` is server-assigned and must never be settable by a caller.
- Every report accepts an optional "as known at" watermark; omitted means now.
- A reopen writes an `audit_log` row carrying the actor, the period, and the stated reason, and the
  matching re-close writes another. "What changed in a closed period, and on whose authority" is a
  query rather than an investigation.
- A stable error `code` for a write refused because its period is closed (ADR-0015), distinguishing
  it from an authorisation failure, so a skill can surface the right question.
- The reopen capability is never granted to a skill principal. This is enforced in the grant model
  rather than asserted in the skill's instructions (IAM-11).
- A reopen that is not followed by a re-close leaves the period open, which must be visible. An
  entity with a period left open by an abandoned correction is a condition to surface, not a state
  to tolerate.
- **Whether reopening a period reopens the ones after it.** NetSuite cascades, because closing
  entries chain. `LED-12` closes income and expense to retained earnings at year end, so a reopen
  behind a year-end has to reckon with that. Undecided here and needs settling before close ships.
- **Revisit this record when lot tracking activates** (LED-18). Reintroducing lots reintroduces the
  cascade, and rule 3 alone will not be sufficient — a backdated acquisition would then need
  downstream basis recalculation, which is the `rebook` operation currently deferred.

**Reversal cost. Low for the policy, high for the two-date model.** Rules 2 to 6 are service-layer
behaviour and can change. Adding `recorded_at` later would mean every existing row has an unknown
recording time, and the bitemporal property could never be reconstructed for historical data — so
the column ships from the first migration whether or not the queries exist yet.

## Revisit when

- **Lot tracking activates.** Named above; this is the concrete trigger.
- Close-crossing acknowledgements become routine rather than exceptional, which would mean the
  signal has been trained away and a hard lock is warranted after all.
- A jurisdiction requires restatement disclosure that rule 4's default does not satisfy.
