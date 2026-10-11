---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0070: Suspension is a set of holds, each lifted only by whoever placed it

**Requirements served:** `PLT-09`, `PLT-10`, `PLT-11`, `PLT-12`, `IAM-03`, `IAM-13`.

## Context and Problem Statement

`PLT-09` puts an entity in one of three states, active, suspended or deleted. `PLT-10` to `PLT-12` say
what suspension halts, what it leaves alone and that it is fully reversible. `IAM-03` makes suspending
an administrative capability.

More than one party has reason to suspend the same company, independently:

* **Its owners**, to stop unattended work for a while: a business paused for the season, or books
  frozen while something is investigated.
* **A commercial service**, when the company stops paying (ADR-0069).

Each needs its suspension to hold until it lifts it. An owner who paused the company does not want a
payment to restart its feeds and reminders; a service that suspended for non-payment cannot have an
owner resume a company they have not paid for. With suspension as one state, whoever resumes last
wins, and each party can undo the other.

Owners are mutually equivalent (ADR-0038), so a suspension one owner placed must be one another can
lift, or an owner who leaves strands it.

## Decision Drivers

* **Neither party can undo the other's suspension.**
* **`PLT-09` stays as written.** The entity is in one of three states, and every transition is
  recorded.
* **An owner who leaves strands nothing.**
* **The owner can see why their company is suspended**, and what lifts it.

## Considered Options

* A set of holds, each lifted only by whoever placed it
* One state, which any holder of the privilege sets or clears
* One state with a reason, cleared only by a role matching the reason
* A commercial service that revokes roles instead of suspending

## Decision Outcome

Chosen option: "A set of holds, each lifted only by whoever placed it", because it is the only option
under which neither party can undo the other and both can suspend at once.

> Suspending a company places a hold on it, and resuming lifts one. A company is suspended while any
> hold remains, and only whoever placed a hold may lift it.

### 1. Holds

A hold records its holder, a reason and when it was placed. Placing and lifting are each a
state-changing act with its own audit row (`IAM-13`).

The holder is one of two kinds:

* **The company.** A hold placed by any identity administering the company through an ordinary role is
  the company's own, and any identity that can administer it may lift it. Owners are equivalent, and
  one who leaves leaves nothing stranded.
* **A client.** A hold placed by a client, through a role a deployment grants for that purpose such as
  `commercial` (ADR-0069), is lifted only by that client.

The reason is a short code the holder chooses, such as `unpaid`, shown to the company's
administrators with who placed the hold. A client's hold also shows the client's address, so the owner
knows where to resolve it.

### 2. The state follows the holds

The entity's state is derived from its holds: suspended while any is in place, active when none is.
The transition is recorded when the first hold is placed and when the last is lifted, as `PLT-09`
requires, and placing a second hold or lifting one of two changes no state.

What suspension halts, leaves alone and backfills is unchanged (`PLT-10` to `PLT-12`, ADR-0061 § 5),
and runs from those two transitions.

### 3. Deletion is unaffected

Holds do not block deletion (`PLT-13`). An owner may delete a suspended company, and deletion ends its
holds with it.

### Consequences

* Good, because an owner's pause and a service's suspension are independent and can overlap.
* Good, because the owner sees each hold, who placed it and why.
* Good, because the three states and what suspension does are unchanged.
* Bad, because "who may resume" depends on who suspended, which an administrator must be told rather
  than assume. The refusal is `hold_not_yours`, naming the holder.
* Neutral, because a company with no client holder behaves exactly as single-state suspension would.

### Confirmation

* Tests: two holds from different holders keep the company suspended until both are lifted; the
  company's hold is lifted by any owner; a client's hold is refused to an owner with `hold_not_yours`,
  and the company's to the client.
* Tests: the state transition is recorded once on the first hold and once on the last lift, and
  placing or lifting a hold writes one audit row each.
* Tests: deleting a suspended company succeeds.

## Pros and Cons of the Options

### A set of holds, each lifted only by whoever placed it

* Good, because it meets every driver.
* Bad, because it adds a holder to every suspension, and a refusal an administrator may not expect.

### One state, which any holder of the privilege sets or clears

* Good, because it is the simplest reading of `PLT-09`.
* Bad, because an owner can resume a company suspended for non-payment, and a payment resumes a
  company its owner paused.

### One state with a reason, cleared only by a role matching the reason

* Good, because it stops either party clearing the other's suspension.
* Bad, because it holds one reason at a time. When the owner pauses a company already suspended for
  non-payment, one reason overwrites the other, and lifting it resumes a company that should stay
  suspended.

### A commercial service that revokes roles instead of suspending

* Good, because it needs no new mechanism.
* Bad, because it removes reading and export, which `PLT-11` keeps through suspension, and it alters
  roles, which `PLT-12` forbids.

## More Information

**Follow-on obligations.**

* Suspension and resumption through the published interface, as placing and lifting holds.
* The hold's holder, reason and placement time, readable by the company's administrators.
* The refusal `hold_not_yours`.

**Reversal cost.** Moderate. Holds become part of the published API and the audit history, though a
company with only its own holds behaves as single-state suspension would.

Related: ADR-0038 (owners are equivalent), ADR-0061 (what suspension stops), ADR-0069 (a commercial
service's hold).

## Revisit when

* The deployment's operator needs to suspend a company itself, under its terms of service, which would
  be a third kind of holder.
* A company accumulates holds its owners cannot account for, which would show the reason codes or the
  display are not enough.
