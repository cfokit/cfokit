---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0052: Messaging is an optional separate component, built on Novu Community

**Requirements served:** `PLT-06`, `PLT-07`, `PLT-22`, `AR-09`, `IAM-22`, `NFR-04`, `NFR-10`.

## Context and Problem Statement

CFOKit has to reach people. `PLT-07` requires it to reach the people who operate an entity when
something needs them — a transaction no rule resolves, a delivery that failed, a change in cash
beyond a threshold they set — on channels they choose, with any class of message turned off at
will. `AR-09` delivers invoices by email. `IAM-22` has a person reset a forgotten password with
no administrator involved, and email is the recovery channel every account has. `PLT-06`
requires that no particular mail provider is required.

What reaches a person is a question, not the books: "I have a question about some transactions."
Answering it happens where they work — a screen in CFOKit's web client
([ADR-0049](0049-cfokit-has-a-web-client.md)) or the conversational interface they use with the
agent.

The channels are several: email, push notifications to the installed web client, an in-app inbox,
and SMS where a requirement asks. Each needs templates, per-person preferences, retries, and a
record of what was sent. Building that is a product of its own.

Novu is an open-source notification platform that does it: one API in front of many providers
(SendGrid, SES, Postmark or plain SMTP for email; Twilio and others for SMS; FCM, APNs and a
webhook for push), with workflows, digests, delays, subscriber preferences and an in-app inbox. Its
core is MIT; its browser libraries are ISC; code under `enterprise/` is proprietary and excluded
from the self-hosted Community edition.

Novu Community 3.19.0 was run from its official compose file, isolated from the internet, and
tested. It started and sent through a plain SMTP server with no route to Novu's cloud. A message
sent while the worker was stopped was delivered when it restarted. A message queued when Redis
was killed — as the official compose file configures Redis — was lost without a trace: the send
had been acknowledged as processed, and afterwards Novu held no record of it, so there was no
failure to see and nothing to retry. With Redis's append-only file enabled from startup, the same
test delivered. Novu refuses by default to connect to a private IP address, so a self-hosted mail
relay on a private network is refused until it is named in `NOVU_SAFE_OUTBOUND_ALLOW`. Its
documentation states that an hourly keep-alive beacon — hostname, IP, instance id, memory,
platform — is sent to Novu whether or not telemetry is enabled. Replies and agent conversations
are withheld from Community: its dashboard disables them for a self-hosted Community instance,
and they are offered on Novu Cloud and the proprietary Enterprise edition.

Novu keeps its own state in MongoDB, Redis and S3-compatible storage, and needs about 4 CPUs and
8 GB of memory before those stores — more than the rest of CFOKit.

## Decision Drivers

* `PLT-07` on every deployment, including one with no messaging at all.
* `PLT-07`'s whole surface where messaging runs — channels, preferences, opt-out by class —
  without building a notification platform.
* No particular provider required (`PLT-06`), and no provider SDK in CFOKit (ADR-0004).
* A message is sent exactly when the change that raised it is committed: never for a change that
  rolled back, and never lost after one that did not.
* A company's books stay in CFOKit's Postgres, under entity isolation and the audit record
  (ADR-0003, `NFR-04`).
* A deployment on one machine stays small.
* No required relationship with a vendor for a self-hosted deployment (`NFR-10`).

## Considered Options

* Novu Community as an optional separate component
* Provider integrations written into CFOKit
* Novu Cloud
* A hosted notification service

## Decision Outcome

Chosen option: "Novu Community as an optional separate component", because it provides the
notification platform `PLT-07` describes under an MIT license, runs self-hosted with no vendor
relationship, and keeps every provider behind configuration rather than code.

> Messaging is a separate component: Novu Community, from its published images, with its own
> MongoDB, Redis and object storage. Any deployment may run it; none has to. Without it, CFOKit
> shows what needs a person inside the product. With it, CFOKit records each message in the same
> commit as the change that raised it and relays it to Novu, carrying a question and a link, never
> the books.

### 1. A separate component, with stores of its own

Novu has its own runtime, holds provider credentials, and runs on its own schedule — each a
criterion ADR-0022 § 3 gives for a separate component. Its MongoDB, Redis and object storage are
its own and sit behind its API. ADR-0003 governs CFOKit's own data: the books, and everything the
ledger and its modules keep, which live in Postgres and nowhere else. A separate component's
internal stores are not a second store for CFOKit.

### 2. Off by default, available to any deployment, and never the only way a person is reached

**What every deployment does, with or without the component.** What needs a person is shown to
them in the product: the web client lists the open questions when they open it, and the agent
raises them in conversation. That is `PLT-07` in its simplest form, and it holds on a deployment
on one machine with nothing else running.

**What the component adds.** Being reached when not looking: email, push to the installed web
client, an in-app inbox that updates live, invoices delivered by email.

**Who runs it.** A deployment on one machine does not by default: the base compose stack runs no
messaging component and no mail server, because the component is larger than CFOKit and email
needs a mail provider. Any deployment may turn it on — on one machine or in the cloud — by
starting it and naming a mail relay. A deployment that serves people who do not administer it
generally does, because account email depends on it.

**Without a mail relay**, the issuer does not verify email, and a forgotten password is reset by
the operator in the issuer's console; on one machine the operator is the administrator. `IAM-22`'s
reset without an administrator therefore holds wherever a mail relay is configured. The
development overlay adds Mailpit (MIT), a local SMTP server with a web inbox, for work on email
itself.

A person may also have their own agent look for them: a scheduled task in their agent runtime that
checks for open questions and tells them (`PLT-02`). That is theirs to set up, needs no component,
and is not relied on here.

### 3. A message is part of the commit that raised it

CFOKit writes a message to send into its own Postgres, in the same transaction as the change that
raised it — the transactional outbox. A relay reads committed messages and triggers the Novu
workflow, passing the message's identifier as Novu's `transactionId`, which Novu documents as its
idempotency key. A change that rolls back sends nothing, because its message was never committed.
A relay that fails retries, and a retry of a message Novu already accepted is recognised rather
than sent twice.

Before a message is written, CFOKit checks that its recipient holds a role in the entity it names,
under the same grant check as any other act (`NFR-04`). Novu is never asked to decide who may be
told what.

### 4. Nothing acknowledged is silently lost

Redis runs with its append-only file enabled at startup, synced on every write, on a persistent
volume. The official compose file does neither, and without both a crash loses queued messages
that were already acknowledged, leaving no record. A deployment that cannot meet this does not
run the component.

### 5. A message asks; a link answers

A message is the agent asking, in its own voice: "I have a question about some transactions." Its
payload carries identifiers, counts, the company's name and one link. No amount, payee, account
number or invoice line crosses into Novu.

The link opens CFOKit. After sign-in it takes the person to where they answer: the web client's
screen for that question, or the conversational interface they use with the agent, as they have
chosen. The web client's screen always works; a conversational interface is offered where it can
be opened at the question. The link names the question and nothing else, so a message read on a
lock screen or forwarded reveals nothing.

An invoice is delivered the same way: the email carries a link to the invoice, a read path that
cannot be guessed and can be revoked (`IAM-20`), not the invoice itself.

### 6. Who is reached, and what Novu holds about them

A Novu subscriber is a person. Each message names its entity in Novu's `context`, the field Novu
provides for separating tenants. A person's preferences — which classes of message, on which
channels — are held in Novu per person.

Novu therefore holds contact details, preferences, and a history of messages that are questions
and links. It holds no record of an entity that exists nowhere else: nothing `EXP-02` exports lives
only in Novu. Its message history is questions and links, which carry none of the retention
obligations `PLT-20` lists for records, so it is kept for as long as the deployment sets. A
person's erasure request (`PLT-22`) removes their subscriber and message history there, and
deleting an entity removes its messages.

### 7. Email is SMTP, one relay for everything that sends it

Novu's generic SMTP provider and the issuer's own mail settings point at the same relay, so
account email (verification, reset) and product email (notices, invoice links) share one
provider, one sending domain and one reputation. On the maintained cloud target the relay is
SendGrid's SMTP service on port 587, since outbound port 25 is blocked there. Any relay that
speaks SMTP replaces it by configuration. A relay on a private network is named in
`NOVU_SAFE_OUTBOUND_ALLOW`.

### 8. The keep-alive beacon does not leave a deployment unannounced

The component's outbound traffic is limited to the providers it is configured to use — on the
maintained cloud target, by egress firewall rules on its network — which stops the beacon. Where
a platform cannot limit it, the deployment's documentation says what is sent and to whom.

### 9. Push, conversations and chat are not decided here

Novu has no native Web Push; how push reaches the installed web client is decided with the first
push message. Novu's two-way features are withheld from Community, and how CFOKit receives
replies, and whether conversations with the agent run through a messaging platform (`PLT-04`,
`PLT-05`), is its own decision. Chat platforms such as Slack are conversational interfaces for
talking with the agent, not channels for these messages, even though Novu can send to them.

### Consequences

* Good, because `PLT-07` holds on every deployment, and where messaging runs, its channels,
  preferences and opt-outs come with the platform.
* Good, because no provider SDK and no notification logic enters CFOKit.
* Good, because a message can neither precede a rolled-back change nor be lost after a committed
  one.
* Good, because the books never leave Postgres; Novu holds contact details, questions and links.
* Bad, because a deployment that runs it operates four more services and three more stores, larger
  than CFOKit itself.
* Bad, because a message's durability rests on a Redis configuration the upstream compose file
  omits, and a deployment that copies it loses messages silently.
* Bad, because Novu's direction is toward agents, some of which are proprietary, and the line
  between Community and Enterprise may move.
* Bad, because the password reset `IAM-22` requires is unavailable where no mail relay is set.

### Confirmation

* A test asserts the messaging component's Redis starts with the append-only file enabled and
  synced on every write, on a persistent volume.
* An integration test starts the component behind its compose profile with outbound traffic
  blocked and sends through Mailpit. It asserts that a message raised by a change that rolls back
  is never sent, that one sent while the worker is stopped arrives after restart, and that a
  message relayed twice is delivered once.
* A test asserts the outbox refuses a recipient with no role in the entity the message names.
* Novu images are pinned by version and digest, and Dependabot proposes their updates.
* Not gated: that a workflow's payload carries no figures. That is review.

## Pros and Cons of the Options

### Novu Community as an optional separate component

* Good, because it meets every driver once Redis is configured for durability and messages pass
  through an outbox.
* Bad, because of its size, and because its durability depends on configuration upstream omits.

### Provider integrations written into CFOKit

SMTP, web push and later SMS written directly, with no platform in between.

* Good, because there is no new component, no MongoDB or Redis, and nothing to operate beside
  CFOKit.
* Bad, because preferences per person and per class, digests, retries, a record of what was sent
  and an in-app inbox would all be written here — a notification platform built inside a
  bookkeeping product.
* Bad, because each new channel is new code in CFOKit rather than configuration.

### Novu Cloud

* Good, because there is nothing to operate, and its conversation features are available.
* Bad, because every deployment then depends on a vendor account, which `NFR-10` rules out for
  self-hosting, and contact details leave the deployment.

### A hosted notification service

Knock, Courier, or a single provider's own platform, such as Twilio's.

* Good, because of mature delivery and support.
* Bad, for the same reasons as Novu Cloud, with no self-hosted edition to fall back to.

## More Information

**Reversal cost.** Low to medium. CFOKit's side is an outbox and a set of named workflow triggers;
replacing Novu means re-creating the workflows elsewhere and pointing the relay at them. Contact
details and preferences live in Novu and would be exported.

Related: ADR-0003 (the scope this clarifies), ADR-0004 (portability), ADR-0021 (Slack as a
conversational surface), ADR-0022 (the separate-component criteria), ADR-0049 (the web client
where questions are answered).

## Revisit when

* Novu changes its license, or moves Community features into the proprietary edition.
* CFOKit needs replies or conversations, which is the separate decision § 9 names.
* The first push message is designed, which decides how push reaches the web client.
* A deployment finds the component's size is the reason it does not send messages.
* Novu's compose file starts configuring Redis for durability, which removes the need to diverge
  from it.
