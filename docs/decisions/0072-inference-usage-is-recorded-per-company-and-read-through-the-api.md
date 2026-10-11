---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0072: Inference usage is recorded per company and read through the published API

**Requirements served:** `PLT-25`, `SOC1-06`, `NFR-17`.

## Context and Problem Statement

Who pays for inference depends on who runs the model. With the hosted backend or a self-hosted one,
the organization's own agent does, and the organization carries its token cost (the vision's cost
structure). CFOKit sees the agent's tool calls, not its tokens. With managed bookkeeping, CFOKit's own
runtime does (ADR-0034), and so would any model call CFOKit makes itself in unattended work. That
inference is CFOKit's cost, and it moves with how much each company uses.

A sold deployment therefore prices usage on top of the subscription: credits included in a plan,
overage charged beyond them. Pricing is the commercial service's (ADR-0069), and the product must not
presume one exists. Yet only the product knows what a company used.

Facts that shape the answer:

* **Every model call CFOKit makes is already captured for evidence.** `SOC1-06` persists the model
  and the context against each entry the agent produced, and a provider's response states the tokens
  it consumed.
* **Payment processors and billing services meter usage.** Stripe's meters and credit grants, and
  billing services such as Orb, Metronome and Lago, each take usage reported to them and turn it into
  charges against included credits.
* **Owners rarely look at their books.** Work stopped because credits ran out goes unnoticed until
  something is wrong.
* **A self-hoster supplies their own inference credential** (ADR-0034) and pays their provider
  directly; what they want is to see what they spend.

## Decision Drivers

* **The product knows no price.** Credits, rates and plans are the commercial service's.
* **Usage is exact and auditable**: derived from what the provider reported, never estimated.
* **Any billing service can read it**, through the interface every client uses.
* **Unattended work is not stopped by a commercial event** the owner is unlikely to see.
* **Every deployment has it** (`NFR-17`): a self-hoster sees their own spend.

## Considered Options

* CFOKit records usage per company; any client permitted reads it through the published API
* CFOKit reports usage to the payment processor itself
* CFOKit converts usage to credits and enforces a balance
* No usage record; the commercial service estimates from activity

## Decision Outcome

Chosen option: "CFOKit records usage per company; any client permitted reads it through the published
API", because it keeps every price outside the product and lets any billing service meter the same
record.

> Each model call CFOKit makes for a company records one usage row: when, the provider, the model and
> version, and the tokens the provider reported, by kind. Rows are append-only and read by period
> through the published API, by the company's owners and by a client holding the privilege to read
> usage. CFOKit never converts usage to money or credits.

### 1. What is recorded

One row per model call CFOKit makes on a company's behalf: the time, the provider, the model
identifier and version, and the tokens the provider's response reports, by kind (input, output,
cached input), with the run or entry it served. The figures are the provider's own, not counted by
CFOKit. A call whose response reports no usage records the call with no figures, which is visible.

The organization's own agent's inference is not recorded, because CFOKit does not make it and cannot
see it.

### 2. Who reads it

The company's owners read their company's usage by period, in the web client and through the API, so
a self-hoster sees their own spend. The `commercial` role gains one more privilege, reading usage, and
still reads no books (ADR-0069). A commercial service reads each company's usage for the period it
bills and reports it to its processor's meter, where credits and overage are priced.

### 3. Running out of credits stops nothing

The product holds no balance and refuses no work for lack of one. A service that charges overage
needs nothing more from the product. A service that wants to stop spending has suspension
(ADR-0070), which stops unattended work and, with it, the inference it would use.

### Consequences

* Good, because any billing service meters the same record through the same
  call.
* Good, because the figures are the provider's own, so a bill can be traced to the calls behind it.
* Good, because a self-hoster sees what their own model provider will charge them.
* Bad, because usage is read after the fact, so a service metering it lags the calls by however often
  it reads.
* Bad, because a hard spending cap is only as fine as suspension, which stops all unattended work, not
  only the work that uses a model.
* Neutral, because the hosted backend records nothing here unless CFOKit itself calls a model.

### Confirmation

* Tests: a model call records one row with the provider's reported tokens; a row cannot be changed or
  deleted outside disposal; reading usage by period returns exactly the rows in it.
* Tests: the `commercial` role reads usage and nothing else; an owner reads their company's usage and
  not another's.

## Pros and Cons of the Options

### CFOKit records usage per company; any client permitted reads it through the published API

* Good, because it meets every driver.
* Bad, because the commercial service must read it on a schedule.

### CFOKit reports usage to the payment processor itself

* Good, because metering is immediate.
* Bad, because the product would call a payment processor and hold its credential, which ADR-0069
  keeps out of the process that holds the books.
* Bad, because a self-hosted deployment, or one using another billing service, gets an integration it
  does not use.

### CFOKit converts usage to credits and enforces a balance

* Good, because a company could never spend past what it bought.
* Bad, because credits and their rates are prices, which the product does not hold.
* Bad, because work stopping when a balance reaches zero is a commercial step in the middle of the
  books, unnoticed by an owner who rarely looks.

### No usage record; the commercial service estimates from activity

* Good, because it needs nothing from the product.
* Bad, because an estimate is not auditable, and a bill that cannot be traced to the calls behind it
  invites disputes.

## More Information

**Follow-on obligations.**

* The usage record, append-only, and its read by period in the published API.
* The privilege to read usage, carried by `commercial` (ADR-0039's catalog).
* Usage on the company's page in the web client.

**Reversal cost.** Low. The record is additive, and a service that stops reading it changes nothing in
the product.

Related: ADR-0033 (provenance at the tool boundary), ADR-0034 (the runtime and who supplies
inference), ADR-0069 (the commercial service), ADR-0070 (suspension holds).

[Stripe: usage-based billing](https://docs.stripe.com/billing/subscriptions/usage-based)

## Revisit when

* A customer needs a spending cap finer than suspension, such as stopping only the work that uses a
  model.
* CFOKit prices something other than inference by usage, such as bank feeds, which would make the
  record about usage in general.
