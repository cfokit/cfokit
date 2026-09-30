---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0052: Messaging is an optional separate component, built on Novu Community

**Requirements served:** `PLT-06`, `PLT-07`, `AR-09`, `IAM-22`, `NFR-10`.

## Context and Problem Statement

CFOKit has to reach people. `PLT-07` requires it to reach the people who operate an entity when
something needs them — a transaction no rule resolves, a delivery that failed, a change in cash
beyond a threshold they set — on channels they choose, with any class of message turned off at
will. `AR-09` delivers invoices by email. `IAM-22` has a person reset a forgotten password with
no administrator involved, which only email can do. `PLT-06` requires that no particular mail
provider is required.

The channels are several and will grow: email first, then push notifications to the installed
web client ([ADR-0049](0049-cfokit-has-a-web-client.md)), in-app messages, and SMS where a
requirement asks. Each needs templates, per-person preferences, retries, and a record of what was
sent. Building that is a product of its own.

Novu is an open-source notification platform that does it: one API in front of many providers
(SendGrid, SES, Postmark or plain SMTP for email; Twilio and others for SMS; FCM, APNs and a
webhook for push; Slack, Teams and more for chat), with workflows, digests, delays, subscriber
preferences and an in-app inbox. Its core is MIT; its browser libraries are ISC; code under
`enterprise/` is proprietary and excluded from the self-hosted Community edition.

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

* `PLT-07`'s whole surface — channels, preferences, opt-out by class — without building a
  notification platform.
* No particular provider required (`PLT-06`), and no provider SDK in CFOKit (ADR-0004).
* Nothing a person was told they were sent is silently dropped.
* A company's books stay in CFOKit's Postgres, under entity isolation and the audit record
  (ADR-0003).
* A deployment on one machine stays small, and works with no mail service at all.
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
> MongoDB, Redis and object storage. CFOKit triggers named workflows through Novu's API with
> identifiers, counts and links, never figures. A deployment without it runs, and sends nothing.

### 1. A separate component, with stores of its own

Novu has its own runtime, holds provider credentials, and runs on its own schedule — each a
criterion ADR-0022 § 3 gives for a separate component. Its MongoDB, Redis and object storage are
its own and sit behind its API. ADR-0003 governs CFOKit's own data: the books, and everything the
ledger and its modules keep, which live in Postgres and nowhere else. A separate component's
internal stores are not a second store for CFOKit; the identity provider's already are not.

### 2. Optional, and absent from a deployment on one machine

The base compose stack runs no messaging component and no mail server. It sends nothing:
the issuer does not verify email, and a forgotten password is reset by the operator in the
issuer's console — on one machine the operator is the administrator. A deployment that wants
messages runs the component and names a mail relay.

`IAM-22`'s reset without an administrator therefore holds wherever a mail relay is configured,
which every hosted deployment has. The development overlay adds Mailpit (MIT), a local SMTP
server with a web inbox, for work on email itself.

### 3. Nothing acknowledged is silently lost

Redis runs with its append-only file enabled at startup, synced on every write, on a persistent
volume. The official compose file does neither, and without both a crash loses queued messages
that were already acknowledged, leaving no record. A deployment that cannot meet this does not
run the component.

### 4. Email is SMTP, one relay for everything that sends it

Novu's generic SMTP provider and the issuer's own mail settings point at the same relay, so
account email (verification, reset) and product email (invoices, notices) share one provider,
one sending domain and one reputation. On the maintained cloud target the relay is SendGrid's
SMTP service on port 587, since outbound port 25 is blocked there. Any relay that speaks SMTP
replaces it by configuration. A relay on a private network is named in `NOVU_SAFE_OUTBOUND_ALLOW`.

### 5. A message says what needs doing, never what the books say

A workflow's payload carries identifiers, counts, a company's name and a link into CFOKit:
"3 transactions need you", not the transactions. No amount, payee or account number crosses into
Novu, which holds only who is reached and how — names, addresses, preferences. The books stay
where entity isolation and the audit record apply, and the person reads them after signing in.
An invoice is the one document sent whole, because sending it is `AR-09`'s purpose.

### 6. The keep-alive beacon does not leave a deployment unannounced

The component's outbound traffic is limited, wherever the platform allows, to the providers it
is configured to use, which stops the beacon. Where it cannot be limited, the deployment
documentation says what is sent and to whom.

### 7. Replies and conversations are not decided here

Novu's two-way features are withheld from Community. How CFOKit receives replies, and whether
conversations with the agent run through a messaging platform (`PLT-04`, `PLT-05`), is its own
decision, with its own license and trust questions.

### Consequences

* Good, because `PLT-07`'s channels, preferences and opt-outs come with the platform, and a new
  channel or provider is configuration.
* Good, because no provider SDK and no notification logic enters CFOKit.
* Good, because a deployment on one machine is as small as before and needs no mail account.
* Good, because the books never leave Postgres; Novu holds contact details and prompts.
* Bad, because a hosted deployment runs four more services and three more stores, larger than
  CFOKit itself, and operates them.
* Bad, because a message's durability rests on a Redis configuration the upstream compose file
  omits, and a deployment that copies it loses messages silently.
* Bad, because Novu's direction is toward agents, some of which are proprietary, and the line
  between Community and Enterprise may move.
* Bad, because the password reset `IAM-22` requires is unavailable where no mail relay is set.

### Confirmation

* A test asserts the messaging component's Redis starts with the append-only file enabled and
  synced on every write, on a persistent volume.
* An integration test starts the component behind its compose profile with outbound traffic
  blocked, sends a workflow through Mailpit, and sends one while the worker is stopped and
  checks it arrives after restart.
* Novu images are pinned by version and digest, and Dependabot proposes their updates.
* Not gated: that a workflow's payload carries no figures. That is review.

## Pros and Cons of the Options

### Novu Community as an optional separate component

* Good, because it meets every driver once Redis is configured for durability.
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

**Reversal cost.** Low to medium. CFOKit's side is a set of named workflow triggers; replacing
Novu means re-creating the workflows elsewhere. Contact details and preferences live in Novu and
would be exported.

Related: ADR-0003 (the scope this clarifies), ADR-0004 (portability), ADR-0021 (Slack as a
delivery surface), ADR-0022 (the separate-component criteria), ADR-0049 (the web client that
receives push).

## Revisit when

* Novu changes its license, or moves Community features into the proprietary edition.
* CFOKit needs replies or conversations, which is the separate decision § 7 names.
* A deployment finds the component's size is the reason it does not send messages.
* Novu's compose file starts configuring Redis for durability, which removes the need to
  diverge from it.
