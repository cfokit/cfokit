---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-14
decision-makers: [Geoff]
---

# ADR-0073: A principal's roles in an entity are a set, added and removed one at a time

**Requirements served:** `IAM-01`, `IAM-03`, `IAM-04`, `IAM-13`, `IAM-15`.

## Context and Problem Statement

`IAM-01` says an identity "may hold more than one role in an entity and its capability is the union
of them". Someone who administers a company and is also given a narrower role, such as one for
receivables, gains nothing from the second: everything it carries, the first already did.

How a principal comes to hold several roles, and how they come to hold fewer, is not written down.
The API offers two acts on a grant, granting and revoking, and nothing stops a grant of a role the
principal already holds, which leaves two identical grants in force. Removing one of them changes
nothing the principal can do, while a screen showing one grant per principal reports the role as
gone. ADR-0066 § 6 raises its `agent_allowed` notice for each grant to an agent and answers it when
any one is revoked, so with two grants the administrators are told twice and the notice closes
while the agent can still act.

`IAM-03` and `IAM-13` speak of "changing a role assignment" and "role change". Whether that is an
act of its own decides the API, the audit trail and every screen that shows roles.

`IAM-15` requires that reducing access takes effect immediately. Products that carry roles in the
session ask a user to sign out and in again after a change; QuickBooks Online's help says to do
exactly that after editing a user's role. A person who changes an agent's role here should not have
to reconnect it.

Nothing about these requirements is particular to bookkeeping, so the answer should be the
established one.

## Decision Drivers

* Follow a published model of role-based access control, not a local invention.
* `IAM-01`: several roles at once, and the union of their privileges.
* What a person sees on a screen matches what the principal can do.
* Every change is one recorded act with who and when (`IAM-13`), and the last owner cannot be
  removed (`IAM-04`).
* A change takes effect on the next request, for people and agents alike, with no new sign-in
  (`IAM-15`).
* A retried request does no harm.

## Considered Options

* A set of roles per principal, added and removed one at a time, a duplicate refused
* One role per principal, changed in place
* The higher of the roles held wins
* A set of roles, with a duplicate accepted as a no-op
* A set of roles, with an atomic act that replaces one role by another

## Decision Outcome

Chosen option: "a set of roles per principal, added and removed one at a time, a duplicate
refused", because it is core role-based access control as ANSI INCITS 359-2004 defines it, and the
model Azure role-based access control follows.

> A principal's roles in an entity are a set, and its privileges are the union of the roles in
> force. The only acts are adding a role and removing one. Adding a role the principal already
> holds in force is refused with `role_already_held`, naming the grant that holds it.

**The acts.** Adding a role is `POST /entities/{id}/grants`, and removing one is
`DELETE /entities/{id}/grants/{grant_id}`, each one act with one audit row (`IAM-13`). There is no
act that changes a role. Moving someone from one role to another is adding the new one and removing
the old one, in either order. Between the two they hold both, which under a union is an ordinary
state and grants nothing either role does not. The last-owner check applies to removing as it does
today (`IAM-04`).

**A duplicate.** One grant per principal and role is in force at a time. Adding one already in
force is refused with `role_already_held`, HTTP 409, carrying the existing `grant_id`, as ANSI
INCITS 359-2004 makes "not already assigned" a precondition of `AssignUser` and Azure returns
`RoleAssignmentExists` with the existing assignment's ID. A caller that retries after a lost
response reads the ID and has what it asked for. Changing when a grant lapses (`IAM-09`) is
removing it and adding it again with the new date. The check runs inside the entity's locked
transaction, so two concurrent adds cannot both pass it (ADR-0011).

**Taking effect.** Roles are never carried in a token. Every request reads the principal's grants
in its own transaction, which already makes a removal immediate (`IAM-15`); the same read makes an
addition immediate. Neither a person nor an agent signs in again or reconnects after a change.

**On screen.** Wherever the web client shows a principal's access, it shows every role they hold,
each with its own Remove, and offers to add only roles they do not hold. An agent's page lists both
of its roles when it holds both.

**An agent's notice follows its standing, not its grants.** This amends ADR-0066 § 6. `agent_allowed`
is raised when an agent goes from holding no role in the company to holding one, and is answered
when its last role in force there is removed. Adding a second role to an agent already allowed
raises nothing.

### Consequences

* Good, because the model is the standard one, so anyone who has administered access elsewhere
  reads it correctly.
* Good, because the roster can no longer hold two grants that look like two things and are one.
* Good, because a role change reaches an agent mid-session, with nothing for the person to redo.
* Good, because every change is a single act with a single audit row, so the trail reads as what
  happened.
* Bad, because moving someone between roles is two acts, where a product with one role per member
  offers one dropdown.
* Bad, because a caller that sends the same grant twice now gets 409 where it got 201, and must
  read the existing `grant_id` from the refusal.
* Neutral, because the union was already how authorization computes privileges; the decision
  writes it down and makes the rest of the system agree with it.

### Confirmation

* An integration test shows a principal holding `owner` and `reader` with exactly `owner`'s
  privileges, and keeping them when `reader` is removed.
* An integration test shows adding a role already held refused with `role_already_held` and the
  existing `grant_id`, and adding it again once removed or lapsed accepted.
* An integration test shows an agent's role changed while it holds a session, and its next call
  served or refused under the new role with no new token.
* An integration test shows `agent_allowed` raised once when an agent is first allowed, not again
  for a second role, and answered only when its last role is removed.
* A web client test shows an agent page with both roles listed, each removable, and no offer to add
  a role already held.

## Pros and Cons of the Options

### A set of roles per principal, added and removed one at a time, a duplicate refused

* Good, because it is ANSI INCITS 359-2004's core model, with `AssignUser` and `DeassignUser` as
  its only acts and "not already assigned" as a precondition of the first.
* Good, because Azure role-based access control works the same way: assignments are additive, and a
  duplicate is refused with the existing assignment's ID.
* Good, because it is what `IAM-01` already states.
* Bad, because a change between roles is two acts.

### One role per principal, changed in place

The common model in small-business software. QuickBooks Online gives each user one role and
changes it from a dropdown.

* Good, because one act changes someone's access, and a screen has one value per person to show.
* Good, because it is conventional too, and familiar to the owners CFOKit is for.
* Bad, because `IAM-01` requires several roles at once. Giving an administrator a receivables role
  as well would need a third role defined as their sum, and the catalog would grow with every
  combination anyone needs (ADR-0039).

### The higher of the roles held wins

* Good, because it reads simply when roles nest, as reader, bookkeeper and owner do.
* Bad, because roles do not always nest. A receivables role and a reporting role each carry
  something the other lacks, so neither is higher, and the rule has no answer.
* Bad, because where roles do nest it gives the same result as the union, so it adds a rule and
  decides nothing.

### A set of roles, with a duplicate accepted as a no-op

* Good, because a repeated request succeeds without the caller handling a refusal.
* Bad, because it departs from the standard's precondition, and from Azure.
* Bad, because a person who adds a role they did not realize was already held is told it was added
  when nothing changed. The refusal tells them it was already there.
* Bad, because the refusal already carries the existing `grant_id`, so a retrying caller gets what a
  no-op would give it.

### A set of roles, with an atomic act that replaces one role by another

* Good, because a move between roles is one act and one audit row.
* Bad, because it brings back the one-role model's "change" inside a model where roles add up. A
  principal holding three roles has no single role to change.
* Bad, because the moment it removes, holding both roles, is harmless under a union, so it is
  atomicity with nothing to protect.
* Bad, because it is a third act on grants, which the standard does not have and `IAM-03` does not
  require.

## More Information

ADR-0066 § 6 is amended in place: the notice is raised and answered by the agent's standing in the
company, as above.

ADR-0039 holds the role catalog; this record holds how a principal comes to hold roles from it.
Neither changes the other.

**Reversal cost.** Low. The refusal is one check in `grant_role`, and the notice rule is a
condition on two calls. Moving to one role per principal would be a schema change and a migration
of every principal holding several, which nobody does yet.

## Revisit when

* A role is defined that removes privileges, rather than adding them. A union cannot express a
  denial, and the model would need one.
* Someone needs the same role held twice at once, for example with two different lapse dates
  (`IAM-09`), which one grant per role cannot express.
