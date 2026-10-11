---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0069: A commercial service is outside the product, and reaches it through general hooks

**Requirements served:** `IAM-03`, `IAM-06`, `IAM-13`, `PLT-09`, `PLT-10`, `PLT-11`, `PLT-12`, `NFR-11`,
`NFR-13`, `NFR-17`.

## Context and Problem Statement

CFOKit's hosted offering is sold. A company subscribes, pays after a free trial, manages its card and
invoices, and is cut off from unattended work when it stops paying. A self-hosted deployment does none
of this: it runs on one machine with no signup (`NFR-11`), and its commercial operator, if any, is
whoever runs it.

The requirements put the commercial service outside the product: its pricing, billing and
subscriptions are business decisions, and the product must not presume an operator exists. Yet a sold
deployment needs the product to cooperate in three places:

* **Before a company exists.** The plan and the card come before the company, in both ways a person
  arrives: on the web, and from Claude's directory, where a person registers while connecting and
  then asks their agent to create the company (ADR-0058).
* **While it runs.** A company that stops paying stops getting unattended work. Suspension
  (`PLT-09`, `PLT-10`) already means exactly that: feeds, outbound messages, scheduled work and
  alerting stop, reading and export continue (`PLT-11`), and nothing is lost (`PLT-12`). Suspending
  is an administrative capability (`IAM-03`).
* **In Settings.** A person with authority over the company manages its subscription.

Facts that shape the answer:

* **The subscription is per company.** The company is what is kept, its invoice belongs in its own
  books, and a second company is a second subscription.
* **A trial takes a card.** Card-required trials convert to paid at roughly two to three times the
  rate of trials without one (industry benchmarks; the hosted funnel will say where it sits). Stripe
  Checkout collects a card for a trial by default and offers Link, which fills a returning payer's
  details in one step, and Stripe sends a reminder before the trial ends.
* **No commercial step after the plan.** Nothing in getting started or in later configuration asks
  for payment or withholds a feature until paid.
* **A payment processor's credential can charge and refund cards.** The mail relay's can only send
  mail (ADR-0052 § 4), and a feed's access is sealed (ADR-0062 § 6).
* **The billing lifecycle is not accounting.** Checkout, the trial, the customer portal, failed
  payments, cancellation and coming back are the same for any subscription business, and so is
  carrying a visitor's identity from the landing page to revenue. None of it reads a ledger.
* **What can suspend companies is inside the deployment's boundary.** In the hosted deployment, a
  credential that can suspend every company is in scope for the same SOC 2 controls as the
  deployment itself, wherever it runs.

## Decision Drivers

* **One switch.** A deployment that sets nothing has nothing commercial anywhere (`NFR-11`).
* **No credential that can charge cards in the process that holds the books.**
* **The product knows no commercial concept.** No plan, price, processor or subscription is stored or
  named in it. What it offers is general: an allowance to create a company, a suspension hold, a link.
* **No capability withheld from any build** (`NFR-17`).
* **No commercial step after the plan**, in either way a person arrives.
* **A self-hoster selling their own deployment gets the same hooks** the hosted offering uses.

## Considered Options

* A commercial service outside the product, reaching it through general hooks
* A subscriptions component in this repository, shipped in the one image
* A billing module in CFOKit's own process, like email and the feed provider
* Charging when a feature is turned on
* A trial without a card, paused when it ends
* New companies created suspended until a subscription is bound

## Decision Outcome

Chosen option: "A commercial service outside the product, reaching it through general hooks", because
the product then holds no commercial concept and no card credential, and the hooks it offers are ones
any operator can use.

> A deployment may name a commercial service. It is a client of the published API, its code is not in
> this repository, and it reaches companies through three hooks: an allowance to create one, a
> suspension hold of its own, and a link from Settings. A deployment that names none has no
> commercial step anywhere.

### 1. One switch

A deployment names the commercial service's public address, or does not. Named, the web client shows
the plan step and the Settings link, and creating a company takes an allowance (§ 2). Not named, none
of that exists: a self-hosted deployment registers, creates companies and keeps books with no
commercial step anywhere. The address is the one setting; the service's own secrets are its own.

### 2. An allowance to create a company

Where a commercial service is named, an identity creates a company only with an allowance, granted to
it at deployment scope. An allowance creates exactly one company, and creating it is the act that
consumes it. Without a commercial service, creating a company needs no allowance (`IAM-06`).

The service grants allowances through the published API, as an OAuth client (ADR-0032) holding one
deployment-scope privilege: granting an allowance. It holds no other privilege at deployment scope.
The allowance names the client that is to hold the `commercial` role in the company it creates.
Consuming the allowance, creating the company, making the person its owner and granting the
`commercial` role are one transaction: the creating act's audit row names the allowance it consumed
and the roles it granted (`IAM-13`), and a creation that fails consumes nothing, so a retry finds the
allowance unspent.

A person gets an allowance by choosing a plan on the service, which takes the card, signs them in
through the deployment's issuer (registration, for a new person), grants the allowance to that
identity, and returns them to where they came from: the web client's company step, or a page telling
them to go back to their agent. How it does those steps is the service's business.

In conversation, `create_entity` without an allowance is refused with `allowance_required`, and the
refusal carries the service's address, which the skill gives the person.

### 3. A suspension hold of its own

The `commercial` role carries one privilege: placing and lifting its own suspension hold on the company
(ADR-0070). That makes it an administrative role in `IAM-03`'s sense, held by a client and conferring
nothing else: it reads no books and posts nothing. It can see the company's state, so the service can
tell an active company from a deleted one. An owner's own hold and the service's are independent: an
owner cannot lift the service's, and paying does not lift the owner's.

The company's owners cannot revoke the `commercial` role, or revoking it would lift a suspension for
non-payment by another route. The client relinquishes it itself, and when it does, its holds end with
it (ADR-0070). A person who wants to stop paying cancels the subscription, and the company stays
readable and exportable (`PLT-11`), or they delete it (`PLT-13`).

Suspension then works as for any company (`PLT-10`, `PLT-11`, `PLT-12`).

### 4. Managing the subscription

Settings links to the service for anyone holding a company's ownership, naming the company. The
service signs them in, confirms through the published API, with their own token, that they hold the
company, and takes them to wherever it manages subscriptions.

### 5. The product keeps no commercial record

The allowance, its consumption, and the hold are the product's only record that a commercial service
acted, each with its audit row. Plans, prices, payments and the processor's identifiers are in the
service and the operator's billing system (ADR-0038).

A processor's webhooks reach the service, not CFOKit. The service reaches a company only through the
published API with its own token and role, so it is not a new way into an entity's data.

### 6. Where it runs in the maintained deployment

In the maintained GCP deployment (ADR-0060), the commercial service runs in the same project, on Cloud
Run, with its secrets in Secret Manager as containers populated out of band (ADR-0016). The credential
that can suspend companies stays inside the deployment's boundary and its controls.

### Consequences

* Good, because a self-hosted deployment has no commercial step and no processor account, and the
  product carries no commercial concept and no processor code.
* Good, because a credential that can charge cards is never in the process that holds the books, nor
  in this repository's dependency graph.
* Good, because a company that stops paying keeps its books readable and exportable.
* Good, because a person sees one commercial step, the plan, before setting anything up.
* Good, because a self-hoster selling their own deployment uses the same hooks with a service of their
  own choosing.
* Bad, because an allowance and a narrow administrative role are new authorization concepts, built for
  one kind of client.
* Bad, because a role the company's owners cannot revoke is an exception to `IAM-03`'s ordinary
  reading, limited to a role that reads no books and posts nothing.
* Bad, because a service retired without relinquishing its roles leaves its holds in place. Retiring
  a commercial service means lifting its holds first.
* Bad, because the service is released apart from the product, so it depends on the published API's
  compatibility obligations (`NFR-13`, ADR-0015) rather than shipping with it.
* Bad, because the Claude door has a hand-off to a web page for the plan before the first company.
* Bad, because a company deleted while subscribed keeps its subscription until the service notices.
  It checks the company's state before each renewal, and cancels a deleted company's subscription.
* Neutral, because pricing, trial length and plans are configured in the service and the processor,
  not in CFOKit.

### Confirmation

* Tests, with no commercial service named: no plan step or Settings link, and creating a company needs
  no allowance.
* Tests, with one named: creating a company without an allowance is refused with
  `allowance_required`; an allowance creates exactly one; the `commercial` role can read the company's
  state and place and lift its own hold, and is refused everything else.
* A client holding the allowance privilege can grant allowances and nothing else at deployment scope.
* `check-decisions`, and the contract gate (CI gate 5): the allowance, the hold and the role are in
  the published API, so a change to them is a reviewed contract change.

## Pros and Cons of the Options

### A commercial service outside the product, reaching it through general hooks

* Good, because it meets every driver.
* Bad, because it adds an allowance and a role to the authorization model, and the service's version
  moves apart from the product's.

### A subscriptions component in this repository, shipped in the one image

Separate by ADR-0022 § 3, because it holds a credential that can charge cards and is driven by the
processor's webhooks; built and released with the product (ADR-0023).

* Good, because its version always matches the API's, and a self-hoster gets it with the image.
* Bad, because everything it does but three API calls is the billing lifecycle, which is the same for
  any subscription business and is not accounting. The repository would carry a processor integration
  and an operator's business process, which the requirements place outside the product.
* Bad, because the conversion step would sit apart from the funnel that brings the visitor and
  measures what they become.
* Bad, because the version match it buys is what `NFR-13` already requires of the published API for
  every client.

### A billing module in CFOKit's own process, like email and the feed provider

The pattern already used twice: a provider configured or absent, no extra process.

* Good, because it needs no allowance and no role: the module could gate creation and suspend
  directly.
* Bad, because the process that holds every company's books would hold a credential that can charge
  and refund cards. ADR-0052 kept the mail relay in-process because its credential can only send.
* Bad, because the product would contain billing, which the requirements place outside it.

### Charging when a feature is turned on

* Good, because a person sees value before paying.
* Bad, because it is a commercial step in the middle of configuration.
* Bad, because a person who never turns on a chargeable feature never converts.

### A trial without a card, paused when it ends

* Good, because more people start a trial.
* Bad, because trials without a card convert at a third to a half the rate, so it relies on people
  coming back to pay.

### New companies created suspended until a subscription is bound

* Good, because it reuses suspension and needs no allowance.
* Bad, because suspension does not stop importing or posting, so it gates nothing until the person
  connects a feed.
* Bad, because a suspended company refuses new integrations (`PLT-10`), which is a commercial step in
  the middle of configuration.

## More Information

**Follow-on obligations.**

* The allowance at deployment scope, the privilege to grant it, and the refusal `allowance_required`.
* The `commercial` role and its one privilege, in the catalog (ADR-0039).
* The plan step and the Settings link in the web client, shown only when a service is named.
* The service's address in the deployment contract, its name in `infra/README.md`.
* The service's Cloud Run service and its secret containers in `infra/gcp/`.

**Reversal cost.** Low for the service, which can be replaced without touching the product. Moderate
for the allowance and the role, which become part of the authorization model, the published API and
the audit history.

Related: ADR-0015 (published interfaces), ADR-0016 (secrets as containers), ADR-0022 (modules and
components), ADR-0032 (component authentication), ADR-0038 (the payer is in the operator's billing
system), ADR-0058 (getting started), ADR-0060 (the maintained deployment), ADR-0070 (suspension holds).

[Stripe: free trials in Checkout](https://docs.stripe.com/payments/checkout/free-trials) ·
[Stripe: customer portal](https://docs.stripe.com/customer-management)

## Revisit when

* The hosted funnel shows a card-required trial costing more starts than its higher conversion
  returns.
* Another kind of client needs a narrow administrative role, which would make the role a pattern
  rather than an exception.
* A commercial service needs to read something the hooks do not give it, which is the test of whether
  the hooks are general enough.
