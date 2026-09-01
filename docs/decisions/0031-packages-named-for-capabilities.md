---
status: "draft"
kind: "substrate"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0031: Packages are named for the capability they provide

## Context and Problem Statement

The repository map inherited from `CLAUDE.md` named a package `packages/plaid-sync`, and the
successor name chosen for it was `packages/connectors`. Both are wrong, in related ways, and the
second is instructive because it looks reasonable.

**`plaid-sync` names a vendor.** ADR-0004 requires provider-specific code to sit behind a protocol
with a local default needing no cloud account. A package named for one provider makes that provider
structural, and the vision anticipates contributors adding others ("I built the CFOKit Stripe
integration"). A vendor name in a package name is a prediction that the vendor is permanent.

**`connectors` names a mechanism.** It says the package integrates with things, which answers neither
"connectors to what?" nor "providing what?". On the current trajectory it will be asked to cover bank
feeds, payment processors, and transactional email — which are not one capability, and conflating them
is exactly what a mechanism-name invites.

A package name is read far more often than it is chosen, and it is the first thing that tells a
contributor what a boundary is for. Getting it wrong is cheap to fix while nothing is built and
expensive afterwards, because import paths appear in user code.

## Decision Drivers

* A name is the cheapest available documentation of a boundary.
* Provider independence is a requirement (ADR-0004), so the layout must not contradict it.
* A name that admits unrelated things will accumulate unrelated things.
* Renaming after publication changes import paths in user code.

## Considered Options

* Name each package for the capability it provides in this system
* Name packages for the vendor they integrate with
* Name packages for the mechanism they use
* Defer naming until each domain exists

## Decision Outcome

Chosen option: "Name each package for the capability it provides in this system", because the
capability is the one property that is stable across vendors, mechanisms, and implementations — which
is precisely the set of things that change.

> Name a package for the capability it provides — not for the vendor it talks to, and not for the
> mechanism by which it does so.

Distributions are `cfokit-<capability>`, importing as `cfokit.<capability>` through PEP 420 implicit
namespace packages.

Applying the rule to the package that prompted it: **`connectors` is renamed before implementation
begins**, and probably split, since bank feeds, payment processing, and transactional email are three
capabilities rather than one. The rename is deferred rather than done now, because doing it twice is
worse than doing it once, and what it splits into depends on decisions not yet made (ADR-0022 § 5).

### Consequences

* Good, because a boundary announces its purpose in the one string every contributor reads first.
* Good, because provider independence is visible in the layout rather than only in a rule.
* Good, because a capability name resists accumulating unrelated things, since the mismatch is
  obvious.
* Bad, because `cfokit-connectors` is vaguer than `plaid-sync` and says less about what exists today.
  It is also a name known to be wrong, carried deliberately until the rename.
* Bad, because "what capability is this?" is occasionally a genuinely hard question, and the rule
  gives no help when the answer is unclear.

### Confirmation

Not gated, and it could not usefully be: no check can tell a capability name from a mechanism name.
This is enforced by review, and by `CLAUDE.md` carrying the rule where an agent proposing a package
will read it.

The one mechanical part is that `packages/` holds distributions only, which `uv sync` enforces
(ADR-0020).

## Pros and Cons of the Options

### Name each package for the capability it provides

* Good, because the capability outlives the vendor and the mechanism.
* Good, because it makes a wrongly-scoped package visibly wrongly-scoped.
* Bad, because it produces vaguer names than a vendor name would, especially early.

### Name packages for the vendor they integrate with

* Good, because it is maximally concrete and honest about what the first version actually does.
* Bad, because it makes the provider structural, contradicting ADR-0004's requirement that
  provider-specific code sit behind a protocol.
* Bad, because it makes each provider a distribution with its own release cadence, and the shared
  protocol then has nowhere to live that does not become a further package.

### Name packages for the mechanism they use

* Good, because the mechanism is usually obvious and easy to agree on, so the name is easy to choose.
* Bad, because it describes how rather than what, so it admits anything using that mechanism. This is
  how `connectors` ends up holding bank feeds, payment processing, and email — three capabilities in
  one package because all three connect to something.

### Defer naming until each domain exists

* Good, because a name chosen with the domain in front of you is a better name.
* Bad, because a package needs a name the moment it is created, so deferring means shipping a
  placeholder — which is what `connectors` already is, and it has not improved with age.

## More Information

**Follow-on obligations.**

- `connectors` renamed, and probably split, before implementation begins.
- `CLAUDE.md`'s repository map carries the rule where an agent proposing a package will read it.

**Reversal cost.** Low now, moderate once anything is published to an index, because import paths
appear in user code.

Related: [ADR-0020](0020-repository-layout-artifact-kinds.md) fixes where packages live;
[ADR-0022](0022-tiny-ledger-modules-and-components.md) § 4 applies this rule to the module and
component taxonomy.

## Revisit when

- A capability genuinely has no name that is not a mechanism, which would mean the boundary is drawn
  around a mechanism rather than a capability.
- A second provider exists, which is the first real test of whether the connector protocol abstracts
  anything.
