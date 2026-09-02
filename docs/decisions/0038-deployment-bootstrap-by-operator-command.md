---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-01
decision-makers: [Geoff]
---

# ADR-0038: A deployment is bootstrapped by an explicit operator command, never over the API

**Requirements served:** `IAM-06`, `IAM-18`, `IAM-13`, `IAM-05`.

## Context and Problem Statement

`IAM-06` states the problem exactly: *"A deployment is brought into service by establishing its
first deployment-scoped administrator, from whom every other role in it descends. **This is the
only privileged act that does not require a prior role.**"*

Every other authority in the system is derived. An entity grant is issued by someone holding
`administrator` in that entity (`IAM-03`); an entity's first administrator is assigned when the
entity is created (`IAM-05`); creating an entity is a deployment-scoped capability, because
`IAM-18` makes the two scopes independent and an entity role cannot confer one. Follow the chain
back and it terminates at a principal who holds a role nobody granted.

That terminal act cannot be authorised by the mechanism that authorises everything else, so it
has to be authorised by something outside it. What that something is, is the decision — and it
is the highest-value target in the system, because whoever performs it can reach every entity
the deployment will ever hold.

A ledger with no way to create an entity is not usable, so this cannot be deferred: it is the
first thing a new deployment does.

## Decision Drivers

* The act must be unrepeatable. A path that establishes an administrator once is a bootstrap; a
  path that can do it again is a standing backdoor.
* It must be evidenced like everything else (`IAM-13`), and `IAM-14` must be able to report who
  it was and when, for any date afterwards.
* It must need no prior role, without that being expressible as "no authentication required" on
  a network surface.
* Self-hosting is a product promise (ADR-0004), so it must work on a laptop with no cloud
  account and no operator console.
* The identity provider issues credentials; CFOKit never does (`IAM-10`). The bootstrap names a
  principal, it does not create one.

## Considered Options

* An explicit operator command, run where the database is reachable
* An API endpoint that works only while no administrator exists
* An environment variable naming the first administrator
* A single-use bootstrap token, minted at deploy time
* Trust on first use: the first authenticated caller becomes the administrator

## Decision Outcome

Chosen option: "An explicit operator command", because the authority to perform it is possession
of the deployment's database credentials, which is a capability the operator already has and
which no network caller can obtain by any request.

> The first deployment-scoped administrator is established by `python -m cfokit.ledger.bootstrap`,
> run against the database. It refuses if a deployment administrator already exists. There is no
> API path that establishes one.

This makes the terminal authority the same one that applies migrations (ADR-0004) — an operator
with the DSN, acting deliberately, out of band. It is the shape the system already has for acts
that precede the service being able to serve.

Deployment-scoped roles live in their own table, independent of entity grants, because `IAM-18`
requires the two scopes to confer nothing on each other. The bootstrap writes an `audit_log` row
like any other state change, so `IAM-13` holds from the first act onward rather than from the
second.

### Consequences

* Good, because the act cannot be reached from the network at all, rather than being reachable
  and guarded.
* Good, because it needs no new credential, no token store, and no distribution step — the
  operator already holds the only thing required.
* Good, because it composes with the existing deployment story: the same operator, the same DSN,
  the same explicit-command shape as migrations.
* Good, because refusing when an administrator already exists makes it a bootstrap rather than a
  recovery path, and the absence of a recovery path is deliberate — see below.
* Bad, because losing every deployment administrator requires database access to recover from,
  and there is no in-product path back. That is the cost of having no standing backdoor, and it
  is the right side of the trade for a system whose value is that the books are correct.
* Bad, because it cannot be performed by a hosted customer without CFOKit acting for them, which
  makes onboarding an operational step in the hosted topology rather than a self-service one.
* Neutral, because it says nothing about how subsequent deployment-scoped capabilities are
  assigned. `IAM-19` requires them enumerable and individually assignable, and that is a separate
  question this record does not answer.

### Confirmation

The command refuses when a deployment administrator already exists, and a test asserts that
running it twice establishes one administrator rather than two. A second test asserts the first
run writes an `audit_log` row naming the principal established and the operator that ran it, so
`IAM-13` has no gap at the origin.

**No test can prove the absence of an API bootstrap path**, and none is claimed. What exists is
the generated OpenAPI document, which CI gate 5 diffs on every change (ADR-0015): a route that
established an administrator would appear there as a contract change and would be visible in
review. That is weaker than a gate and is stated as such.

## Pros and Cons of the Options

### An explicit operator command, run where the database is reachable

* Good, because the required capability — the database credential — cannot be obtained by any
  network request, so the act is unreachable rather than guarded.
* Good, because it reuses the operator relationship and the entrypoint shape that migrations
  already established (ADR-0004, ADR-0023).
* Bad, because it requires database access, which in a hosted topology only CFOKit has.
* Bad, because it is invisible to a customer: nothing in the product shows that the act is
  available or has been performed, beyond the audit row it writes.

### An API endpoint that works only while no administrator exists

The obvious answer, and the one most systems ship.

* Good, because it needs no operator access and works identically in every topology.
* Bad, because it is an unauthenticated write path on a financial system, and its safety rests
  entirely on a race: between deployment and the first legitimate call, anyone who can reach the
  service can claim the deployment. The window is small and it is not zero, and the consequence
  is total.
* Bad, because the guard is a query result rather than a property. A bug, a restored backup, or
  a second database that has not been bootstrapped re-opens it, and nothing about the endpoint's
  existence changes to signal that.

### An environment variable naming the first administrator

* Good, because it needs no command, no endpoint and no token, and it fits the env-vars-only
  configuration contract exactly (ADR-0004).
* Good, because it is declarative: the deployment states who the administrator is.
* Bad, because it makes the administrator a property of the running configuration rather than a
  recorded act, so `IAM-13`'s "who made it and when" has no answer and `IAM-14` cannot report the
  origin. Changing the variable would silently change who holds the deployment.
* Bad, because it would make the variable authoritative at every startup, which is a standing
  grant mechanism rather than a bootstrap.

### A single-use bootstrap token, minted at deploy time

* Good, because it works over the network without an unauthenticated window, and it can be
  scoped and expired.
* Bad, because it introduces a credential CFOKit mints, which `IAM-10` excludes: "CFOKit never
  issues credentials, stores passwords, or operates a login flow".
* Bad, because a token must be generated, transported and destroyed, and each of those is a place
  it can be captured or retained. The operator command needs none of them.

### Trust on first use: the first authenticated caller becomes the administrator

* Good, because it requires no separate act at all, and the caller is at least authenticated by
  the issuer.
* Bad, because it grants the deployment to whoever arrives first, and nothing establishes that
  they should have it. In a deployment reachable by an organisation's whole workforce, that is a
  race the wrong person can win by accident.
* Bad, because it is indistinguishable, in the records, from a deliberate act. The audit row would
  say who, and never that nobody chose them.

## More Information

**Follow-on obligations.**

* Deployment-scoped capabilities must become enumerable and individually assignable (`IAM-19`).
  This record establishes the first holder and says nothing about the rest.
* A second deployment administrator should be establishable by the first, through the API, so the
  command is needed exactly once. Until that exists, the command is the only path and the
  single-administrator failure mode is real.
* `SOC1-27` and `SOC2-23` require break-glass operator access to be time-bounded, individually
  authorised and visible to the customer. The bootstrap is not break-glass — it precedes the
  deployment being in service — but the two meet if the command is ever used on a live
  deployment, and that boundary needs stating before it is.

**Reversal cost. Moderate.** The command and the table are small. What is expensive to reverse is
the absence of a network path: adding one later is a new attack surface argued on its merits,
which is the argument this record makes rather than forecloses.

## Revisit when

* The hosted topology needs customer self-service onboarding, which is the case this option
  serves worst.
* `IAM-19`'s enumerable deployment capabilities are designed, since the first holder and the set
  they hold are the same question asked twice.
* A deployment loses every administrator in practice rather than in theory, which would show
  whether "recover via the database" is a cost or a defect.
