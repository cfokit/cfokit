---
status: "draft"
kind: "requirement-driven"
date: 2026-09-01
decision-makers: [Geoff]
---

# ADR-0035: CFOKit holds the inference relationship for the attested runtime

**Requirements served:** `SOC2-09`, `SOC2-10`, `SOC2-18`.

## Context and Problem Statement

[ADR-0034](0034-cfokit-operated-agent-runtime.md) ships a CFOKit-operated agent runtime and draws the
SOC 1 boundary at it. It deliberately left one question open: something has to supply the inference
credential that runtime calls with, and it did not say what.

That record judged the two arrangements equivalent on **evidence** grounds, and they are. Pinning a
model identifier and recording what was called happens inside the runtime we operate, whoever pays for
the tokens (`SOC1-06`, `SOC1-35`). If evidence were the only consideration this would stay open.

It is not, because section 8.3 obliges the *system* to enforce things about the provider that can only
be enforced by whoever holds the contract:

- `SOC2-10` — a provider that does not contractually offer zero data retention and no training on
  submitted data **cannot be configured** to receive customer data, and this is "a constraint the
  system enforces on configuration, not a procurement preference."
- `SOC2-18` — deleting an entity destroys "any representation held by a provider under SOC2-10."
- `SOC2-12` — where residency is committed to, routing respects it and a request that cannot be routed
  compliantly fails rather than falling back.

Against a credential the customer supplies, CFOKit can enforce none of these. It cannot read the terms
on someone else's provider account, cannot tell whether training is enabled on it, cannot compel
deletion at a provider it has no agreement with, and cannot control that account's routing.

`A-5` currently assumes inference cost sits with the runtime the user already operates. That
assumption was written before a CFOKit-operated runtime existed and describes the default path
correctly.

## Decision Drivers

* `SOC2-10` is a constraint on **configuration**, enforced by the system. Terms on an account CFOKit
  does not hold cannot be validated by anything.
* `SOC2-18` requires deletion to reach provider-held representations, which needs an agreement that
  obliges the provider to delete.
* A control that stops operating because a customer's API key lapsed or hit a rate limit is a Type 2
  finding, not a support ticket.
* Model version stability (`SOC1-35`) is far easier to hold across one account we control than across
  every customer's.
* `A-5` and the vision's cost argument: token cost sitting with the user is what keeps margin off
  token prices, and that is worth preserving where it can be.

## Considered Options

* CFOKit holds the inference relationship for the attested runtime; the default path is unchanged
* The customer supplies an inference credential to the CFOKit-operated runtime
* Either, at the customer's choice
* CFOKit operates its own inference infrastructure

## Decision Outcome

Chosen option: "CFOKit holds the inference relationship for the attested runtime; the default path is
unchanged", because three `Must` requirements in section 8.3 oblige the system to enforce properties of
the provider relationship, and only the party holding that relationship can enforce them.

> Where CFOKit operates the runtime, CFOKit holds the provider agreement and supplies the inference.
> Everywhere else the skill installs into a runtime the organisation operates, that runtime supplies
> its own inference, and CFOKit needs no inference account of its own (`PLT-02`).

### 1. The default path does not change

`PLT-02` is untouched. The Apache 2.0 build, the self-hosted deployment, and any third-party MCP client
continue to work exactly as before, with the organisation's own runtime and its own inference. Nothing
is withheld and no capability moves (`NFR-17`).

What changes applies only to the attested tier, where CFOKit is operating the runtime anyway.

### 2. A dependency you invoke but have no contract with is the worst position

This is the argument that decides it, and it is worth stating separately from the requirements.

If a customer supplies the credential, the inference provider is still **inside** CFOKit's system
description — our runtime is the thing calling it, on our infrastructure, producing entries inside the
SOC 1 boundary. But we would have no agreement with it, no ability to monitor it, no way to enforce
terms on it, and no standing to compel deletion.

That is neither a clean carve-out nor a controlled dependency. It is a subservice organization we
cannot monitor, which is strictly worse than either owning the relationship or being outside the
boundary entirely. `ES-4` asks how an inference provider is treated in the examination; this record
answers it for the covered path — carve-out, with the monitoring obligations that carve-out places on
us, which we can only discharge under our own agreement.

### 3. What this costs, stated plainly

For the attested tier, margin moves with token prices. The vision's cost-structure argument — that
CFOKit's costs are Postgres, compute and storage, and pricing is therefore an ordinary SaaS question —
holds for the default path and **does not hold here**. That tier is priced against a variable input
cost, and it should be priced knowing that rather than discovering it.

`A-5` is amended to scope the assumption to the default path rather than the product.

### Consequences

* Good, because `SOC2-10` becomes enforceable as configuration validation rather than aspirational: a
  provider without the required contractual terms is one the system will not let anybody select.
* Good, because `SOC2-18` deletion can actually reach a provider, and `SOC2-12` routing is controllable.
* Good, because model version stability holds across one account we control, which is what makes
  `SOC1-35` answerable rather than best-effort.
* Good, because a lapsed customer credential can no longer become a gap in control operation.
* Good, because volume pricing and prompt caching are available on a single account, which a fleet of
  customer accounts forecloses.
* Bad, because margin for that tier moves with token prices, which is exactly what the vision's cost
  structure was constructed to avoid.
* Bad, because CFOKit becomes a reseller of inference for that tier, with the pricing, quota and
  support burden that implies.
* Bad, because the provider becomes a subservice organization CFOKit must monitor, and that obligation
  is permanent.
* Bad, because there are now two cost models to operate, explain, and price.
* Neutral, because the evidence position is unchanged: ADR-0034 established that either arrangement
  records the model equally well.

### Confirmation

`SOC2-10` is the checkable one, and it is checkable precisely because this record makes CFOKit the
contracting party: a provider absent from the registry, or present without zero-retention and
no-training terms recorded, cannot be selected in configuration. That is a validation rule, not a
review step.

**Neither the registry (`SOC2-09`) nor the validation exists yet**, so today this is a decision about
who holds the contract and nothing enforces the rest of it. The registry is named as a follow-on rather
than implied.

## Pros and Cons of the Options

### CFOKit holds the inference relationship for the attested runtime

* Good, because it is the only arrangement under which section 8.3's provider constraints are
  enforceable by the system.
* Good, because it removes a customer-side failure mode from control operation.
* Bad, because it exposes that tier's margin to token prices.
* Bad, because it makes CFOKit a reseller and a monitor of a subservice organization.

### The customer supplies an inference credential to the CFOKit-operated runtime

The option that preserves the cost structure exactly, and the reason ADR-0034 left this open rather
than assuming.

* Good, because token cost stays with the user, `A-5` needs no amendment, and the vision's pricing
  argument holds unchanged across every tier.
* Good, because the customer keeps a direct relationship with the provider, which some will prefer on
  data-governance grounds.
* Bad, because `SOC2-10` cannot be enforced. CFOKit cannot read the terms on an account it does not
  hold, and a customer key with training enabled would be undetectable.
* Bad, because `SOC2-18` cannot be satisfied: there is no standing to compel deletion at a provider we
  have no agreement with.
* Bad, because a lapsed or rate-limited customer key becomes an interruption in control operation
  inside an attested period.
* Bad, because it leaves a dependency inside the system description that CFOKit cannot monitor (§ 2).

### Either, at the customer's choice

* Good, because it lets a customer with strong data-governance preferences keep their own relationship
  while everyone else takes the simple path.
* Bad, because the attested tier would then have two control environments, one of which fails
  `SOC2-10`. An examination covers a population; a population where the provider constraint holds for
  some members and not others is not one control.
* Bad, because it doubles the operational surface for the tier that can least afford ambiguity.

### CFOKit operates its own inference infrastructure

Running open-weight models on infrastructure CFOKit controls, rather than buying from a provider.

* Good, because it removes the subservice organization entirely, and with it the carve-out, the
  monitoring obligation, and `ES-4`.
* Good, because model version stability becomes absolute — nothing changes underneath us on a vendor's
  schedule, which is the one thing no provider agreement fully guarantees.
* Bad, because it trades a variable token cost for a large fixed one, and at current volume that is
  worse on every axis.
* Bad, because coding accuracy is the product, and frontier-model quality is not currently reproducible
  on self-operated infrastructure at a cost this business supports.
* Bad, because it is a substantial and permanent operational commitment far outside anything else in
  this repository.

## More Information

**Follow-on obligations.**

* The provider registry `SOC2-09` requires, holding each provider's recorded contractual terms, with
  `SOC2-10` enforced as configuration validation against it.
* A provider agreement carrying zero retention, no training on submitted data, a deletion obligation
  reaching `SOC2-18`, and residency terms sufficient for `SOC2-12`.
* `A-5` amended to scope the cost assumption to the default path.
* The vision's *Cost structure* section states two cost models rather than one.
* Changing provider or model version is a control-environment change (`SOC2-13`, `SOC1-35`) and is
  recorded in the change log ADR-0033 requires.
* Behaviour when the provider is unavailable partway through a workflow (`SOC2-29`) — partial
  completion must not leave the books mid-state.

**Reversal cost. Moderate.** Moving to customer-supplied credentials later is a configuration and
billing change, but it would reopen `SOC2-10` and `SOC2-18`, which is the reason it was not chosen.
Moving the other way — from customer-supplied to ours — would require re-establishing the control
environment mid-period, which is worse.

Related: [ADR-0034](0034-cfokit-operated-agent-runtime.md) ships the runtime and deferred this;
[ADR-0033](0033-provenance-captured-at-the-tool-boundary.md) records what was called; `PLT-02` governs
the default path this does not touch.

## Revisit when

* Open-weight models reach parity for coding accuracy at a cost this business supports, which would
  reopen the self-operated option and with it `ES-4`.
* A provider offers contractually enforceable zero-retention terms that a *customer's own* account can
  be verified against by an API, which would remove the `SOC2-10` objection to customer-supplied
  credentials.
* Token cost becomes a material fraction of the attested tier's price, at which point the pricing
  model rather than this decision is what needs revisiting.
* An enterprise customer requires their own provider relationship as a condition of purchase, which is
  the case that would force the split option to be re-argued.
