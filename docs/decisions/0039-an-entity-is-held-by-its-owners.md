---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-02
decision-makers: [Geoff]
---

# ADR-0039: An entity is held by one or more mutually equivalent owners

**Requirements served:** `IAM-21`, `IAM-04`, `IAM-05`.

## Context and Problem Statement

`IAM-03` made suspending, granting, revoking and deleting one capability. `PLT-12` says
suspension *"alters no data, revokes no role, and is fully reversible"*; `PLT-13` says deletion
*"destroys that entity's data, is irreversible"*. `IAM-08` makes the advisor working across
many entities the ordinary case, so the bookkeeper engaged for a quarter needs to administer
the entity and, in acquiring that, acquires the ability to destroy the books and to revoke the
founder who engaged them. `IAM-04` guaranteed only that *an* administrator remained.

Which privileges a role carries is a mapping and changes freely. Two things about ownership are
not mapping, because no assignment of flags expresses them, and they are what this record
decides: **how many identities hold an entity**, and **whether they can revoke each other**.

## Decision Drivers

* A person who holds an entity alone is a single point of failure on the only privileges that
  can delete it. The ordinary remedy — naming someone you trust as an equal — is what a founder
  does as soon as there is someone to name.
* An owner who leaves must be removable. That case is likelier than betrayal and worse when it
  has no answer.
* A permission model must not be asked to solve what it cannot. Abuse by a peer deliberately
  made your equal is a personnel matter.
* `IAM-09`'s lapse happens "without anyone acting", which must never leave an entity unheld.

## Considered Options

* One or more owners, mutually equivalent and mutually revocable
* Exactly one owner, with an explicit transfer operation
* One or more owners who cannot revoke each other

## Decision Outcome

Chosen option: "one or more owners, mutually equivalent and mutually revocable".

> An entity is held by one or more owners. Any owner may grant or revoke ownership, including
> another owner's. At least one must remain, and ownership cannot be time-bounded.

The cardinality rule and the no-lapse rule are the parts a privilege table cannot hold: one is
a count checked at revocation, the other is a refusal to accept `lapses_at` on a grant.

### Consequences

* Good, because a founder can name a second owner as soon as there is someone to name, and the
  entity survives losing one of them without an out-of-band recovery.
* Good, because an owner who leaves is removable by the remaining owners, with no ceremony.
* Bad, because an owner can revoke a peer owner. Declined rather than missed: ownership is
  conferred knowingly as an equivalence, and preventing it would forbid the departure case.
* Bad, because an entity whose owners all leave without granting ownership onward can never be
  deleted and its grants never revoked. Recovery is database access when self-hosted, and the
  break-glass path `SOC1-27` and `SOC2-23` already require when hosted.
* Neutral, because it says nothing about billing. A commercial service's billing is outside the
  product's boundary, so a hosted operator's payer is a fact in its billing system.

### Confirmation

The last-owner count runs inside the entity's locked transaction, as `IAM-04`'s check does
now, so two concurrent revocations cannot each see the other's owner and leave the entity
unheld (ADR-0011). Tests assert that an owner may revoke a peer owner, that the last one cannot
be revoked whoever attempts it, and that a grant of ownership carrying `lapses_at` is refused.

## Pros and Cons of the Options

### One or more owners, mutually equivalent and mutually revocable

* Good, because redundancy and departure both work with no operation beyond the grant that
  already exists.
* Bad, because it does not prevent an owner revoking an owner — the case it declines to solve.

### Exactly one owner, with an explicit transfer operation

* Good, because who holds the entity is never ambiguous and abuse between owners is impossible.
* Bad, because it is a bus factor of one: a holder who dies or leaves without transferring
  leaves an entity nobody can delete and a grant nobody can revoke.
* Bad, because the product's answer to "I want a backup" would be that there isn't one.
* Bad, because transfer exists only to work around the single-holder constraint.

### One or more owners who cannot revoke each other

* Good, because it gives redundancy while removing the betrayal case entirely.
* Bad, because an owner who leaves the company can never be removed, which is the likelier
  problem. The set of owners could then only grow.

## More Information

**Follow-on obligations.** `PLT-13` deletion is unbuilt; this fixes who may ask for it, not
what it does. `IAM-07` invitations are unbuilt, and an invitation to ownership needs the same
no-lapse treatment. Succession — an owner that is an estate or a trustee — is not addressed.

**Reversal cost. Moderate.** Grants are append-only, so ownership once granted stays visible in
`IAM-14` whatever the model becomes.

## Revisit when

* Deletion is built, since the privilege and the act should be reviewed together.
* An entity needs a holder that is not a person.
* Two owners deadlock in practice rather than in theory.
