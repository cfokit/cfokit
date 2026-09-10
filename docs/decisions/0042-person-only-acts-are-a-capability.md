---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-10
decision-makers: [Geoff]
---

# ADR-0042: A person-only act is gated by a capability, and `actor_class` describes provenance rather than authority

**Requirements served:** `IAM-02`, `IAM-11`, `LED-11`, `SOC1-04`, `SOC1-15`.

## Context and Problem Statement

Two acts are reserved to a person: reopening a closed period
([ADR-0030](0030-closed-period-reopen.md)) and importing a company's books
([ADR-0041](0041-import-is-parsed-where-the-file-is.md)). Both are enforced the same way —
`principal.actor_class is not ActorClass.PERSON` raises `NotAPerson`.

**That check does not do what it says.** `principal_from_claims` assigns `PERSON` to any token
carrying no RFC 8693 `act` claim, and a client credentials token carries none. So a machine
caller — the shape [ADR-0032](0032-component-authentication-and-configuration.md) added deliberately for
separate components — is classified as a person and passes both gates.

The exposure is bounded and worth stating accurately rather than dramatically. `authorise` still
runs, reading entity grants server-side, so a service account holding no grant is refused before
it reaches anything. What is real is narrower: **a service account an operator has granted
capabilities in an entity can perform the two acts reserved to people**, and an operator who
granted `post` did not thereby intend to grant "reopen a period someone has reported on".

The obvious repair is to require positive evidence that a human authenticated. Measured against
the issuer this deployment ships, that repair does not work: a genuine end-user token carried
**neither `auth_time` nor `amr`**, the two claims RFC 9068 § 2.2 names for exactly this. What
distinguished the two tokens was `sid`, `email` and `name` against `client_id`, `clientAddress`
and `acr` — a session artifact and vendor extensions.

A second question arrives with the first. `ActorClass` has three values, `person`, `rule` and
`agent`, and [ADR-0033](0033-provenance-captured-at-the-tool-boundary.md) § 3 argues the third one hard:
"the rule path is the one to maximise. Making it invisible in the data removes the incentive to."
Nothing assigns `RULE`. The derivation produces two of the three values and always has.

## Decision Drivers

* `IAM-11` makes effective authority the intersection of grants held server-side. A control that
  reads authority out of a token's shape sits outside that model rather than inside it.
* [ADR-0019](0019-identity-provider-conformance-contract.md) forbids issuer-specific code. A claim that one issuer emits
  and another does not is not available as a control.
* A control that fails closed for the people it is meant to admit is worse than the gap it
  closes: an issuer omitting `auth_time` would refuse every genuine import.
* `IAM-02` already requires privileges to distinguish classes of act, and
  [ADR-0039](0039-roles-are-rows-privileges-are-code.md) makes roles rows — so a new distinction is data plus an enum value, not an architecture.
* `SOC1-04` splits autonomous completion from human authorisation **by provenance**, which is
  what `actor_class` is for. Overloading it with authority makes both jobs harder.

## Considered Options

* Gate the reserved acts on a capability; leave `actor_class` describing provenance
* Derive a fourth `actor_class` from claims that evidence end-user authentication
* Add a `service` actor class from the absence of a subject that resolves to a user
* Leave it: a service account is a principal acting on its own behalf, which is a person's shape

## Decision Outcome

Chosen option: "Gate the reserved acts on a capability; leave `actor_class` describing
provenance".

### 1. The reserved acts take a capability no role carries by default

`Capability.ACT_AS_PRINCIPAL` — the flag for an act that must be somebody's own, not something
performed on their behalf or by a component configured to run unattended. Reopening a closed
period and importing a company's books require it. Nothing else does today.

No seeded role carries it, `owner` included. An operator granting it to a service account is then
a deliberate, recorded act rather than a consequence of how their issuer shapes a token — and
because grants are rows, that decision has a grantor, a timestamp and an audit row, which a token
shape has none of.

**This is where the control belongs.** `CLAUDE.md` already says entity grants are validated
server-side regardless of token contents; putting the reservation in the grant model puts it
where every other authority question already is.

### 2. The `act` check stays, as a second condition

A delegated agent is refused even where the person it acts for holds the capability. `IAM-11`
makes an agent's authority the intersection of its own grants and the person's, and [ADR-0007](0007-append-only-from-posting-reversing-corrections.md)'s
"the agent proposes; a person's confirmation posts" is about **who confirms**, not about what they
are permitted to do. Intersection alone would let a skill inherit the reservation from the person
it acts for, which is the failure the reservation exists to prevent.

So both conditions hold: the principal is not acting for another, **and** holds the capability.

### 3. `actor_class` records why a posting was made, and is never an authority check

It answers "what kind of judgement produced this", which is what `SOC1-04` splits on and what an
examiner tests. It does not answer "may this caller do this", which is `authorise`'s question.
The two were conflated because `NotAPerson` was the only mechanism to hand when `ADR-0030` needed
one.

A consequence worth stating plainly: **`person` does not mean a human authenticated.** It means
the token carried no delegation. Renaming it would be honest and is not worth a migration of every
stored posting; the docstring says so instead, and no new code may read authority from it.

### 4. `rule` is assigned at the booking path, never derived from a token

A token cannot tell you that a coding was rule-assigned, because the rule runs after
authentication and the same credential can carry a rule-assigned posting and a judgement in the
same session. `SOC1-04` describes it exactly that way: an agent *completes a transaction assigned
by an approved rule*, so the assignment is a property of the transaction.

`RULE` therefore arrives when the rules engine does — as a value the write path sets on a posting
whose coding a rule determined, not as a branch in `principal_from_claims`. The derivation
producing two of three values is correct rather than incomplete, and the docstring on
`ActorClass` should stop implying otherwise.

**Nothing here builds that engine.** `SOC1-04` is `Proposed`, no rules exist, and a class assigned
by nothing is worth less than a class assigned by something honest about when it will arrive.

### Consequences

* Good, because the reservation becomes visible: "who may reopen a period" is a query against
  grants rather than a property of a credential nobody can inspect after the fact.
* Good, because it needs nothing of the issuer, so it survives the issuer being swapped — which
  the claim-sniffing alternative would not.
* Good, because it fails in the safe direction. A deployment that grants the capability to nobody
  can perform neither act until somebody decides who may, and the refusal names the capability.
* Good, because `actor_class` stops carrying two jobs, so `SOC1-04`'s provenance split and
  `IAM-11`'s authority model can each change without the other.
* Bad, because every existing deployment must grant the capability before anyone can reopen a
  period or import books, and nothing warns an operator in advance. That is a migration note and
  a release note, not a code change.
* Bad, because it does not distinguish a person from a machine, and does not try to. An operator
  who grants the capability to a service account has made that machine able to perform a person's
  act. The decision is that this should be *possible and recorded* rather than impossible and
  unenforceable.
* Bad, because `person` keeps a name that overstates what it knows, in stored data that is
  append-only and therefore permanent.

### Confirmation

Integration tests over both reserved acts: refused for a principal holding every other
capability, permitted for one holding this one, and refused for a delegated agent whose person
holds it — which is the condition intersection alone would let through.

A test asserts no seeded role carries the capability, so a future migration cannot widen it by
accident; `_known` already fails closed on a privilege the enum does not define, and this is the
same property from the other side.

**Not gated:** nothing prevents new code reading `actor_class` as an authority check. It is a
review rule, and a weak one — see [ADR-0036](0036-correctness-is-tested-in-four-layers.md) § 5 on
what the ungated rules in a record are for. The gated control is that `authorise` is the only
thing `import-linter` lets the service layer reach for a permission question.

## Pros and Cons of the Options

### Gate the reserved acts on a capability; leave `actor_class` describing provenance

* Good, because it uses the authority model that already exists rather than adding a second one.
* Good, because the decision is data, so it is auditable, revocable and lapses like any grant
  (`IAM-09`).
* Bad, because it is a breaking change for any deployment already relying on the acts working.
* Bad, because a machine can still be granted a person's act, which reads as a gap to anyone who
  expected the name to be enforced.

### Derive a fourth `actor_class` from claims that evidence end-user authentication

The repair that looks right, and the one measurement rules out.

* Good, because it would make the name true: a person's token would be one a person authenticated
  for.
* Bad, because the claims are not there. The issuer this deployment ships emitted neither
  `auth_time` nor `amr` on a genuine end-user token, and RFC 9068 § 2.2 says SHOULD rather than
  MUST.
* Bad, because the claims that *were* distinguishing — `sid`, `client_id`, `clientAddress` — are a
  session artifact and vendor extensions, so depending on them is issuer coupling ADR-0019
  forbids.
* Bad, because it fails closed for the people it is meant to admit. An issuer omitting the claim
  refuses every genuine import, and the operator has no way to tell that from a bug.

### Add a `service` actor class from the absence of a subject that resolves to a user

* Good, because it names the thing accurately, and the audit trail would then record that a
  component acted.
* Bad, because resolving a subject to a user needs a principal registry the ledger deliberately
  does not have (ADR-0033 § 2), or a directory call per request.
* Bad, because it still answers an authority question with an identity fact, which is the
  conflation this record exists to end.

### Leave it: a service account is a principal acting on its own behalf

* Good, because it is defensible on the letter: the token carries no delegation, and `ADR-0032`
  admits machine callers deliberately.
* Good, because it costs nothing and breaks nothing.
* Bad, because two records say "person" and mean it. `ADR-0030` reserved reopening *because* a
  skill must not reach it, and a service account is closer to a skill than to a person.
* Bad, because the gap is invisible. An operator granting `post` to a component has silently
  granted two acts nobody described to them.

## Revisit when

* The rules engine lands, which is when `RULE` becomes assignable and § 4 stops being a statement
  about the future.
* An issuer in use emits `auth_time` or `amr` dependably, which would make the rejected option
  available — as a defence in depth over the capability, never as a replacement for it.
* A second reserved act appears that is not a person's own act but a component's, which would
  test whether one capability is the right granularity or whether the reservation is per-act.
