---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0030: A closed period is reopened, never overridden

**Requirements served:** `LED-11`, `SOC1-17`.

## Context and Problem Statement

Backdating is routine and permitted (ADR-0013). Backdating into a period someone has already reported
on is the mechanism by which a figure a lender or a board has relied on changes underneath them.

`LED-11` obliges a closed period to admit no posting except through a recorded reopening. `SOC1-17`
states the same rule in the register an examiner reads: a closed period *"admits nothing from any
actor over any interface, agents included, and reopening it requires an administrative role, is
recorded, and captures the reason. There is no privileged path around either."*

The residual question is what the boundary actually does when a write meets it — refuse, warn, or
require something — and who is allowed to cross it.

The constraint that makes this sharper than it looks: **most CFOKit entities will have one person.**
Segregation of duties is then impossible, and `IAM-17` says the system must not raise it. So the
control that matters is not person against person. It is person against agent.

## Decision Drivers

* A control that cannot be evidenced does not count as implemented (`NFR-18`), so the boundary must
  produce evidence rather than a log line.
* The single-operator case is the common case, so the control must survive having no second person.
* `NFR-19` requires a non-accountant to complete a month-end close unaided, so ceremony has a budget.
* Prior reported figures should stand by default; restatement is a deliberate act.

## Considered Options

* A closed period is hard-locked; entering it is a recorded reopen, and reopening is a human-only
  capability
* Forbid backdating entirely
* Permit it freely, with no distinction for closed periods
* Advisory close, with an acknowledgement parameter on the write

## Decision Outcome

Chosen option: "A closed period is hard-locked; entering it is a recorded reopen, and reopening is a
human-only capability", because a capability an agent does not hold cannot be auto-acknowledged,
which is the only version of this control that survives a single-operator entity.

### 1. Entering a closed period is a reopen, not a flag

A closed period is reopened, or it is not written to. The reopen is a distinct event carrying who did
it, when, and why, and the period is closed again when the work is done.

The enterprise ledgers settled here long ago. NetSuite's closed state admits no
general-ledger-impacting change from any user, administrators included, and reopening records a
justification. Sage Intacct refuses any posting dated at or before a closed period end and requires
the books to be reopened, with access restricted to the controller. Auditing standards point the same
way: journal-entry testing is mandatory in every audit precisely because entries at and after period
end are the management-override fraud vector.

### 2. The reopen is a human capability, never a skill's

**This is the load-bearing rule, and it is the one that survives having a single user.**

`SOC1-17` requires an administrative role to reopen and forbids a privileged path around it. A
skill's principal never holds that capability. The agent can draft, it can post into an open period,
and when it meets a closed one it must ask.

An acknowledgement parameter on the write could not do this: an agent that auto-acknowledges defeats
the rule, and nothing about a parameter stops it. A capability the agent does not hold cannot be
auto-acknowledged.

### 3. One gesture, not a workflow

`LED-11` requires a recorded reopening. It does not require ceremony, and `NFR-19` requires a
non-accountant to complete a month-end close unaided.

So the operator sees one question — *that receipt is dated 14 March, which you closed; reopen March to
post it?* — and one confirmation. Behind it the system records the reopen, the posting, and an
automatic re-close. The period is never left silently open, which is the state an operator would
otherwise have to understand in order to manage.

Copying enterprise ceremony wholesale would import the cost without the control: Intacct restricts
reopening to the controller, and for a sole operator that is the same person as the bookkeeper.

### 4. Reversal dating follows the period state

- Original period **open** → the reversal takes the original transaction date. The period is
  restated, which is correct because nothing has been reported yet.
- Original period **closed** → the reversal defaults to the **current open period**, so prior reported
  figures stand and the correction appears where it was discovered. Restating the original period
  instead is available, and is a reopen under rule 1.

This is the prospective-versus-restatement choice accounting makes routinely, with the default set to
the less surprising option.

### Consequences

* Good, because the control survives a single-operator entity, which is the common case and the one
  segregation of duties cannot reach.
* Good, because "what changed in a closed period, and on whose authority" is a query rather than an
  investigation.
* Good, because prior reported figures stand by default, so a lender's statement does not silently
  change.
* Bad, because reopening is a capability the tool contract and the REST API both expose, and it is
  withheld from skill principals (ADR-0014). A skill meeting a closed period must ask a person.
* Bad, because an operator posting a late receipt into a closed period pays one confirmation. That is
  more than no ceremony and less than the enterprise workflow, and it is the compromise this record
  makes.
* Bad, because the reversal-dating default will occasionally be wrong for a user's intent, so it must
  be overridable — and overriding it is itself a close-crossing.

### Confirmation

The capability is enforced in the **grant model**, not asserted in a skill's instructions (`IAM-11`),
which is what makes "an agent cannot reopen" a property rather than a request. Entity grants are
validated server-side regardless of token contents (ADR-0011), so the same check covers both
adapters.

Period close and reopen are built: `0005-period-close.sql` holds the schema,
`cfokit.ledger.service.periods` the write path, and `tests/integration/test_period_close.py`
exercises both. A posting into a closed period is refused with `period_closed`, which is distinct
from `not_authorised` so a caller is told to reopen rather than sent to ask for a capability that
would not help.

A reopen writes an `audit_log` row carrying the actor, the period, and the stated reason; the matching
re-close writes another. That is the evidence `NFR-18` requires, and its absence on a state change is
a bug by the rule in `CLAUDE.md`.

**Not yet gated:** nothing detects a period left open by an abandoned correction. That is a condition
to surface rather than a state to tolerate, and it needs a check.

## Pros and Cons of the Options

### Hard-locked close, with a recorded reopen as a human-only capability

* Good, because the control is a capability an agent does not hold, which no amount of agent
  behavior can defeat.
* Good, because it matches what NetSuite and Intacct settled on, so it will not surprise an
  accountant or an examiner.
* Bad, because it costs the operator a confirmation on every late entry into a closed period.
* Bad, because it introduces a state — period reopened and not yet re-closed — that must be surfaced.

### Forbid backdating entirely

Simplest rule, and it makes every period final the moment it closes.

* Good, because there is no boundary to police, no reopen, and no evidence to keep.
* Bad, because it forbids standard accounting practice. Year-end adjusting entries are dated to the
  year they adjust and posted afterwards; that is how accrual accounting works, and CFOKit will need
  accrual (`LED-17`, `RPT-19`). A ledger that cannot express an adjusting entry is not a ledger.

### Permit it freely, with no distinction for closed periods

What QuickBooks does by default, since its closing date is opt-in.

* Good, because it never blocks a legitimate write and needs no operator interaction at all.
* Bad, because a statement already given to a lender can change with nothing recorded about the fact.
  The write itself is legitimate; the silence is not.

### Advisory close, with an acknowledgement parameter on the write

Close marks the period as reviewed, and a caller may still post by passing an explicit
acknowledgement. Attractive because it keeps append-only as the sole guarantee and adds no new
capability.

* Good, because it costs one parameter, needs no grant model change, and never blocks an operator.
* Bad, because an agent that auto-acknowledges defeats the rule entirely, and a parameter cannot stop
  it. Under a single-operator entity there is no second person to notice.
* Bad, because append-only and a hard close answer different questions. Append-only guarantees that
  nothing is destroyed; it says nothing about whether entering a closed period is a deliberate,
  evidenced act, and that is the question an examiner asks. Under `NFR-18` a control that cannot be
  evidenced does not count as implemented, and a parameter on a write is not evidence of a control.

## More Information

**Follow-on obligations.**

- A reopen writes an `audit_log` row carrying the actor, the period, and the stated reason, and the
  matching re-close writes another.
- A stable error `code` for a write refused because its period is closed (ADR-0015), distinguishing it
  from an authorisation failure, so a skill can surface the right question.
- The reopen capability is never granted to a skill principal, enforced in the grant model
  (`IAM-11`).
- A reopen not followed by a re-close leaves the period open, which must be visible.
- Reopening scope is settled in ADR-0027: a reopen touches one period, and a year-end close that a
  later posting makes stale is reversed and re-run.

**Reversal cost. Low.** These are service-layer behavior and a grant-model entry. Unlike the two-date
model in ADR-0013, nothing here is baked into the schema's history.

Related: [ADR-0013](0013-two-dates-bitemporality.md) makes the crossing visible; this record decides
what happens at it. ADR-0007 makes records immutable from posting, which is a different guarantee.

## Revisit when

- **Lot tracking activates** (`LED-18`). A backdated acquisition would then need downstream basis
  recalculation, and rule 1 alone will not be sufficient.
- Reopens become routine rather than exceptional, which would mean the signal has been trained away
  and the ceremony needs to increase rather than the rule to relax.
- A jurisdiction requires restatement disclosure that rule 4's default does not satisfy.
