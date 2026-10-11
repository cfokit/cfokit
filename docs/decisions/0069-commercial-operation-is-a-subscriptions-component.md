---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0069: Commercial operation is a subscriptions component that a deployment names or leaves out

**Requirements served:** `IAM-03`, `IAM-06`, `IAM-13`, `PLT-09`, `PLT-10`, `PLT-11`, `PLT-12`, `NFR-11`,
`NFR-17`.

## Context and Problem Statement

CFOKit's hosted offering is sold. A company subscribes, pays after a free trial, manages its card and
invoices, and is cut off from unattended work when it stops paying. A self-hosted deployment does none
of this: it runs on one machine with no signup (`NFR-11`), and its commercial operator, if any, is
whoever runs it.

The requirements put the commercial service outside the product: its pricing, billing and
subscriptions are business decisions, and the product must not presume an operator exists. Yet the
hosted offering needs the product to cooperate in three places:

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
  rate of trials without one (industry benchmarks; CFOKit's own funnel will say where it sits).
  Stripe Checkout collects a card for a trial by default and offers Link, which fills a returning
  payer's details in one step, and Stripe sends a reminder before the trial ends.
* **No commercial step after the plan.** Nothing in getting started or in later configuration asks
  for payment or withholds a feature until paid.
* **Stripe's credential can charge and refund cards.** The mail relay's can only send mail
  (ADR-0052 § 4), and a feed's access is sealed (ADR-0062 § 6).
* **Stripe drives the lifecycle by webhook**, signed with HMAC-SHA256 in the `Stripe-Signature`
  header and retried for up to three days.
* **Stripe's customer portal** updates the card, shows and pays invoices, and cancels, on Stripe's
  own page, reached by a session that expires after five minutes unused and cannot be framed.

## Decision Drivers

* **One switch.** A deployment that sets nothing has nothing commercial anywhere (`NFR-11`).
* **No credential that can charge cards in the process that holds the books.**
* **The product knows no commercial concept.** What it offers the commercial service is general:
  suspension, a role, an allowance to create a company.
* **No capability withheld from any build** (`NFR-17`).
* **No commercial step after the plan**, in either way a person arrives.
* **No second store** (ADR-0003).

## Considered Options

* A subscriptions component, named by the deployment or left out
* A billing module in CFOKit's own process, like email and the feed provider
* Billing outside this repository, as the operator's private service
* Charging when a feature is turned on
* A trial without a card, paused when it ends
* New companies created suspended until a subscription is bound

## Decision Outcome

Chosen option: "A subscriptions component, named by the deployment or left out", because it holds
the one credential that can charge cards apart from the books, and leaves the product with general
hooks rather than a commercial concept.

> Commercial operation is the `subscriptions` component. A deployment names it or leaves it out,
> and leaving it out removes every commercial step. The product offers it three general hooks:
> an allowance to create a company, a role that suspends and resumes one, and a link from Settings.

### 1. A component, in the same image

`subscriptions` is a separate component by ADR-0022 § 3: it holds a credential that can charge and
refund cards, it is driven by Stripe's webhooks, and a third party could build it against the
published API. It ships in the one image as its own entrypoint, in the service shape (ADR-0023), and
authenticates as an OAuth client (ADR-0032). It calls the published API and nothing else.

Stripe sits behind a provider protocol, with a replay provider standing in wherever no Stripe account
should be needed, as the feed's does (ADR-0062 § 2). It is reached over HTTPS with the standard
library, and its signatures are checked with `hmac`, so it adds no runtime dependency.

### 2. One switch

A deployment names the component's public address, or does not. Named, the web client shows the plan
step and the Settings link, and creating a company takes an allowance (§ 3). Not named, none of that
exists: a self-hosted deployment registers, creates companies and keeps books with no commercial step
anywhere.

### 3. An allowance to create a company

Where the component is named, an identity creates a company only with an allowance, granted to it at
deployment scope. An allowance creates exactly one company, and creating it is the act that consumes
it. The allowance names the client to receive the `subscriptions` role in that company, and the
creating act grants it, so each grant has its own audit row (`IAM-13`). Without the component,
creating a company needs no allowance (`IAM-06`).

A person gets an allowance by choosing a plan:

1. The plan page sends them to Stripe Checkout, which takes their name, email, phone and card, or
   Link, and starts the trial.
2. Back from Checkout, the component signs them in through the issuer, which is registration for a
   new person, with their email passed as `login_hint`.
3. The component grants the allowance to that identity and records it, and the identity, on the
   subscription.
4. It returns them to where they came from: the web client's company step, or a page telling them to
   go back to their agent.

In conversation, `create_entity` without an allowance is refused with `allowance_required`, and the
refusal carries the deployment's address for getting one, which the skill gives the person.

### 4. A role that suspends and resumes

The `subscriptions` role carries one privilege, suspending and resuming the company. That makes it
an administrative role in `IAM-03`'s sense, held by a component and conferring nothing else: it
reads nothing and posts nothing. The component suspends a company when its subscription ends unpaid,
after Stripe's retries, or when it is canceled and its period ends; and resumes it when it is paid.
Suspension then works as for any company (`PLT-10`, `PLT-11`, `PLT-12`).

### 5. Managing the subscription

Settings links to the component for anyone holding a company's ownership. The component signs them
in, confirms through the published API that they hold the company, and redirects them to a Stripe
customer portal session for that company's subscription.

### 6. Stripe holds the record

The component keeps no store. A subscription's company, allowance and identity are metadata on the
subscription in Stripe, which is the operator's billing system (ADR-0038). Every webhook is
verified, and its handler is safe to repeat: suspending a suspended company changes nothing.

The webhook reaches the component, not CFOKit's API. It reads no entity data, and the component
acts on a company only through the published API with its own token and role. It is not a new way
into an entity's data.

### Consequences

* Good, because a self-hosted deployment has no commercial step and no Stripe account, and the
  product carries no commercial concept.
* Good, because a credential that can charge cards is never in the process that holds the books.
* Good, because a company that stops paying keeps its books readable and exportable.
* Good, because a person sees one commercial step, the plan, before setting anything up.
* Bad, because an allowance and a narrow administrative role are new authorization concepts,
  built for one component.
* Bad, because the Claude door has a hand-off to a web page for the plan before the first company.
* Bad, because a company deleted while subscribed keeps its subscription until the component
  notices. It checks each company's state when Stripe announces a renewal, and cancels a deleted
  company's subscription.
* Neutral, because pricing, trial length and plans are configured in Stripe, not in CFOKit.

### Confirmation

* Tests, with the component not named: no plan step or Settings link, and creating a company needs
  no allowance.
* Tests, with it named: creating a company without an allowance is refused with
  `allowance_required`; an allowance creates exactly one; the `subscriptions` role can suspend and
  resume and do nothing else.
* The component's tests run against the replay provider, with no Stripe account.
* `import-linter` keeps `cfokit.subscriptions` from importing CFOKit's other packages; it uses the
  published API.

## Pros and Cons of the Options

### A subscriptions component, named by the deployment or left out

* Good, because it meets every driver.
* Bad, because it adds an allowance and a role to the authorization model.

### A billing module in CFOKit's own process, like email and the feed provider

The pattern already used twice: a provider configured or absent, no extra process.

* Good, because it needs no component, no allowance and no role: the module could gate creation and
  suspend directly.
* Bad, because the process that holds every company's books would hold a credential that can charge
  and refund cards. ADR-0052 kept the mail relay in-process because its credential can only send.
* Bad, because the product would contain billing, which the requirements place outside it.

### Billing outside this repository, as the operator's private service

* Good, because it is the plainest reading of "the product must not presume a commercial operator".
* Bad, because the product needs the same hooks either way, so it saves nothing in the product.
* Bad, because a self-hoster who wants to sell their own deployment gets nothing, and the
  component's version could drift from the API's (ADR-0023).

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

* Suspension and resumption, through the published interface (`PLT-09` to `PLT-12`).
* The allowance at deployment scope, and its refusal `allowance_required`.
* The `subscriptions` role and its one privilege, in the catalog (ADR-0039).
* The plan step and the Settings link in the web client, shown only when the component is named.
* The component's address, its Stripe secret key and its webhook secret in the deployment contract;
  the secrets as containers populated out of band (ADR-0016), and the names in `infra/README.md`.

**Reversal cost.** Low for the component, which can be replaced without touching the product.
Moderate for the allowance and the role, which become part of the authorization model and its audit
history.

Related: ADR-0022 (modules and components), ADR-0023 (one image), ADR-0032 (component
authentication), ADR-0038 (the payer is in the operator's billing system), ADR-0058 (getting
started), ADR-0062 (a provider protocol with a replay provider).

[Stripe: free trials in Checkout](https://docs.stripe.com/payments/checkout/free-trials) ·
[Stripe: customer portal](https://docs.stripe.com/customer-management) ·
[Stripe: webhook endpoints](https://docs.stripe.com/webhooks/signature)

## Revisit when

* CFOKit's own funnel shows a card-required trial costing more starts than its higher conversion
  returns.
* A second payment processor is needed, which tests whether the provider protocol is the right
  shape.
* Another component needs a narrow administrative role, which would make the role a pattern rather
  than an exception.
