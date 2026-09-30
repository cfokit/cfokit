---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-30
decision-makers: [Geoff]
---

# ADR-0052: Notifications are records, delivered after their commit through CFOKit's own channels

**Requirements served:** `PLT-06`, `PLT-07`, `PLT-22`, `IAM-22`, `NFR-04`, `NFR-06`, `NFR-10`,
`SOC2-17`.

## Context and Problem Statement

CFOKit has to reach people. `PLT-07` requires it to reach the people who operate an entity when
something needs them — a transaction no rule resolves, a delivery that failed, a change in cash
beyond a threshold they set — on channels they choose, with any class turned off at will.
Invoices reach customers by the same channels, as
[ADR-0053](0053-an-invoice-is-a-page-delivered-by-public-address.md) sets out. `IAM-22` has a
person reset a forgotten password with no
administrator involved, and email is the recovery channel every account has. `PLT-06` requires
that no particular mail provider is required.

What reaches a person is a question, not the books: "I have a question about some transactions."
They answer it where they work — a screen in the web client
([ADR-0049](0049-cfokit-has-a-web-client.md)) or the conversational interface they use with the
agent.

A notification is a fact CFOKit holds, like a transaction: this person has this question about
this entity, raised at this moment by this act. It has to be true whether or not anything
delivers it, because a deployment on one machine may have no mail service at all, and a hosted
one has to deliver it without losing it or sending it for a change that never happened.

The maintained cloud target scales CFOKit to zero between requests (ADR-0017). A process that
holds a connection open, or runs work after a response has returned, costs an always-on instance
or does not run.

## Decision Drivers

* `PLT-07` holds on every deployment, including one with no mail service.
* A notification exists exactly when the act that raised it is committed: never for a change that
  rolled back, never lost after one that did not.
* No new infrastructure, no second store, and no always-on process beside CFOKit (ADR-0003,
  ADR-0017).
* No particular provider required (`PLT-06`), and no provider SDK in CFOKit (ADR-0004).
* A company's books stay under entity isolation and the audit record (`NFR-04`).
* New channels are added without reshaping what came before.

## Considered Options

* Notification records, delivered after commit by the process that wrote them
* A notification platform (Novu Community) as a separate component
* A hosted notification service (Novu Cloud, Knock, Courier)
* A relay that sweeps an outbox, or an event bus
* A relay woken by Postgres `LISTEN`/`NOTIFY`

## Decision Outcome

Chosen option: "Notification records, delivered after commit by the process that wrote them",
because it makes a notification part of the truth, degrades to in-app on any deployment, and adds
no infrastructure.

> A notification is a record in CFOKit's Postgres, written in the same transaction as the act that
> raises it. Every deployment shows a person their notifications in the web client and through the
> agent. Where channels are configured, the process that committed the notification delivers it
> immediately after the commit, through CFOKit's own channel layer, and records each delivery.

### 1. A notification is a record, beside the audit log

A notification row names its recipient, its entity, its class, what it is about (an opaque
reference to the subject) and the link that answers it. It is written through the same unit of
work as the act that raises it, in the same commit — the way every state-changing call already
writes its `audit_log` row. Any module raises one without depending on another module, and the
ledger learns no domain meaning: the columns are generic, as the audit log's are.

Rows are append-only. What happens to a notification afterwards is recorded as rows of its own,
never as an update to it: the hand-off to a channel, whose outcome means the relay accepted the
message or refused it, and the events a provider reports later (§ 5).

Before a notification is written, its recipient is checked to hold a role in the entity it
names, under the same grant check as any other act (`NFR-04`). An invoice emailed to the entity's
customer, who holds no role, is authorised as ADR-0053 sets out.

### 2. Every deployment shows notifications; channels add reaching people who are not looking

With no channel configured, a person's open notifications are listed in the web client and read
by the agent through the published interface. That is `PLT-07` in its simplest form, and it holds
on a deployment on one machine with nothing else running.

Channels add delivery: email first, then push to the installed web client and others as
requirements ask. Which classes arrive on which channels is each person's own setting, kept in
CFOKit, as is where they answer — the web client or their conversational interface.

### 3. Delivered after the commit, by the process that committed it

A notification is only ever written inside a request or a scheduled run, so the process that
commits it is awake. After the commit succeeds, and before the response returns, it hands the
notification to each channel the recipient has enabled, with a short timeout. No transaction and no
entity lock is held while it does (ADR-0011): a slow relay delays one response, never the next
write to that entity. A change that rolls back delivers nothing, because its notification never
existed.

A hand-off that fails is recorded as failed and left undelivered; the notification is still shown
in-app. Each later hand-off for the same entity first delivers that entity's undelivered
notifications, so a failure is retried the next time CFOKit delivers anything for that entity —
within the entity's own scope, never another's — with no sweep and no process of its own. A
notification that exhausts its attempts is marked as such and stays visible, never silently
dropped.

Delivery happens before the response, not in a task after it, because a platform that scales to
zero may withdraw CPU once a response has returned.

### 4. Channels are CFOKit's own, behind one small interface

A channel takes a notification and a recipient's address and returns a delivery outcome. The first
is email, sent over SMTP with Python's standard library to the deployment's relay (§ 5); on the
maintained cloud target that is port 587, since outbound port 25 is blocked there.

The implementations sit in a package of their own that depends on the ledger and that no module
depends on; the composition point supplies the configured channels to the write path. A new
channel is a new implementation of the same interface.

The relay's credential is held by CFOKit's process. It can only send mail, it is supplied as an
environment variable like any other secret (ADR-0016), and isolating it in a component would cost
an always-on process to protect a send-only credential.

### 5. One mail relay, configured the same way for CFOKit and the issuer

Email is SMTP and nothing else. A deployment names one relay by host, port, username, password
and sending address, and CFOKit and the issuer are configured with the same five values; with none
set, there is no email channel. Any relay that speaks SMTP works.

On the maintained cloud target the relay is SendGrid's, and its features are used through that
relay rather than a second integration: the sending domain is authenticated there, and its
suppression lists stop mail to addresses that bounced or complained. What is specific to SendGrid —
the `X-SMTPAPI` header CFOKit adds to its own messages, and the event webhook — is an option of the
email channel, off unless a deployment configures it. Without it, the channel sends plain SMTP and
CFOKit serves no webhook, so no deployment depends on SendGrid (`PLT-06`, ADR-0004). With it, each
message carries its notification's identifier in the `X-SMTPAPI` header, which the event webhook
returns with every event.

CFOKit receives SendGrid's event webhook and records each event against the notification it names:
delivered, deferred, bounced, dropped, marked as spam, unsubscribed, opened and clicked. Requests
are accepted only with a valid signature — SendGrid signs each one with an ECDSA key, over its
timestamp and raw payload — so an unauthenticated endpoint cannot be used to forge a delivery
record.

The webhook is an inbound HTTP endpoint, not part of CFOKit's REST interface. Its request is
SendGrid's format, which CFOKit conforms to and no third party builds against, so it is not a
published interface in ADR-0015's sense and is left out of the OpenAPI document. It carries no
token from the issuer, so neither audience validation nor entity grants apply to it: the signature,
verified with the key this deployment configures, is its whole authentication, and is what shows
the request is meant for this deployment (`NFR-06`). It acts for no person and writes nothing but
delivery events. Each accepted request writes one audit row naming the relay as its actor.

The event names a notification, not an entity, so the webhook resolves a notification's entity
before recording anything, and then records within that entity's scope. That resolution is the one
place this record reads across entities, and it reads nothing but the entity a notification
belongs to.

Open and click tracking are off in the relay's account settings and switched on per message, by
CFOKit, in the `X-SMTPAPI` header of its own mail. The issuer's mail is therefore never tracked:
its verification and password-reset links carry one-time credentials, and click tracking would pass
them through SendGrid. CFOKit's tracked links use a link domain branded as the deployment's own.
Opens are recorded as SendGrid reports them and read as a hint: mail clients that fetch images on
the reader's behalf report opens that did not happen.

A relay receives no customer financial data, and it does receive personal information:
recipients' names and email addresses, the questions sent, and the delivery, open and click events
it reports. It is a vendor within the Security criteria's vendor management, and what it holds is
handled as personal information under `SOC2-17`'s classification. An erasure request (`PLT-22`)
removes the person's address from the relay where its interface allows, and the record of the
request says where it could not. Whether recipients' contact details and their open and click
events bring the Privacy category into scope is a scope decision for the requirements (§ 8.1),
not this record's.

Templates are CFOKit's: kept in the repository, reviewed and tested like code, and rendered with
Jinja2, whose autoescaping keeps text from outside the books from becoming markup. They are never
kept in a provider, so every deployment and every relay sends the same message. The issuer's own
account email — verification, password reset — comes from its own email theme, styled from the same
design system, so a reader sees one sender. Marketing to contact lists is not part of the product.

### 6. A notification asks; its link answers

A notification is the agent asking, in its own voice. Its content carries identifiers, counts, the
company's name and one link — no amount, payee, account number or invoice line. The link opens
CFOKit, and after sign-in takes the person to where they answer: the web client's screen for that
question, or their conversational interface where it can be opened at the question. A message
read on a lock screen or forwarded reveals nothing.

What an invoice is delivered as, and to whom, is
[ADR-0053](0053-an-invoice-is-a-page-delivered-by-public-address.md).

### 7. A notification is the entity's data

Notifications and their deliveries are records the entity holds. They carry none of the retention
obligations `PLT-20` lists, so a person's erasure request (`PLT-22`) erases theirs, and they are
included in the entity's complete export (`EXP-02`).

### 8. Without a mail relay

A deployment with no relay configured has no email channel: notifications are in-app only, invoices
are delivered by the operator (ADR-0053), the issuer does not verify email, and a forgotten password
is reset by the operator in the issuer's console. `IAM-22`'s reset without an administrator holds
wherever a relay is configured, which every deployment serving people who do not administer it has.
The development overlay adds Mailpit (MIT), a local SMTP server with a web inbox, for work on email.

### Consequences

* Good, because `PLT-07` holds on every deployment, and email adds reach without adding a store,
  a process or a platform.
* Good, because a notification is committed or not with its act, and a failed delivery waits
  visibly rather than disappearing.
* Good, because CFOKit keeps scaling to zero.
* Good, because a channel is a small implementation, and the choice of relay is configuration.
* Good, because one relay and one template set serve every deployment, with the provider's
  deliverability features where it offers them.
* Bad, because a response waits for delivery, bounded by the channel's timeout.
* Bad, because a failed delivery is retried only when CFOKit next delivers something for that
  entity, which for a quiet entity can be a while; the notification is visible in-app meanwhile.
* Bad, because the webhook is a public endpoint authenticated by SendGrid's signature rather than
  by the issuer, so its safety rests on that verification, and it resolves a notification's entity
  across entities.
* Bad, because digests, scheduled sending and templates across channels are CFOKit's to build
  when a requirement asks for them.
* Bad, because Jinja2 is a runtime dependency.
* Bad, because the password reset `IAM-22` requires is unavailable where no relay is set.

### Confirmation

* A test asserts that an act whose transaction rolls back leaves no notification and delivers
  nothing, and that a committed one has its notification in the same commit.
* A test asserts that with no channel configured, a notification is listed in the web client's
  read and the agent's, and nothing is sent.
* A test runs the email channel against Mailpit: a notification is delivered and its delivery
  recorded; with the relay stopped, it is recorded as failed, stays listed, and is delivered by the
  next hand-off.
* A test asserts that a notification to a recipient with no role in its entity is refused.
* A test asserts that a hand-off delivers only its own entity's undelivered notifications, and that
  no transaction or entity lock is held while a channel sends.
* A test asserts that a webhook request with a missing or invalid signature records nothing, and
  that a valid event is recorded against the notification its identifier names, with one audit
  row naming the relay.
* A test asserts that the webhook route is absent from the generated OpenAPI document.
* A test asserts that without the SendGrid option configured, the channel adds no `X-SMTPAPI`
  header and the webhook route is not served, and that with it, CFOKit's messages carry their
  notification's identifier and switch tracking on.
* Not gated: that a notification's content carries no figures. That is review.

## Pros and Cons of the Options

### Notification records, delivered after commit by the process that wrote them

* Good, because it meets every driver.
* Bad, because a quiet deployment retries a failed delivery late, and multi-channel features are
  built as they are needed.

### A notification platform (Novu Community) as a separate component

Novu is MIT-licensed, self-hostable, and provides one API over many providers, workflows,
digests, subscriber preferences and an in-app inbox.

* Good, because channels, digests and templates would come built.
* Bad, because it is six more services and stores — an API, a worker, a WebSocket service and a
  dashboard, with MongoDB, Redis and object storage — larger than CFOKit, at about $60 to $240 a
  month on the maintained cloud target, and its worker and WebSocket service cannot scale to zero.
* Bad, because its queue loses acknowledged messages without trace when Redis restarts without an
  append-only file, and the managed Redis on the maintained cloud target offers only snapshots;
  the managed service that offers an append-only file is a further cost.
* Bad, because its inbox and preferences would duplicate what CFOKit now keeps as its own records.
* Bad, because its two-way conversation features are withheld from the self-hosted Community
  edition.

### A hosted notification service (Novu Cloud, Knock, Courier)

* Good, because there is nothing to operate.
* Bad, because every deployment depends on a vendor account, which `NFR-10` rules out for
  self-hosting, and recipients' contact details leave the deployment.

### A relay that sweeps an outbox, or an event bus

* Good, because delivery would happen off the request path.
* Bad, because a sweep is a polling process that runs whether or not anything is waiting.
* Bad, because an event bus is a second account of what happened (ADR-0012), when the notification
  record already is the account.

### A relay woken by Postgres `LISTEN`/`NOTIFY`

* Good, because `NOTIFY` is released only on commit and wakes a listener at once.
* Bad, because the listener is an always-on process, about $45 a month on the maintained cloud
  target.
* Bad, because the managed database's connection pooling does not support `LISTEN` in its default
  mode, and a failover drops listeners and the signals sent before they reconnect, so a catch-up
  is needed anyway.

## More Information

**Reversal cost.** Low. The notification record is the durable part and stays whatever delivers
it; a channel is replaced by another implementation of the same interface.

**Follow-on obligation.** `CLAUDE.md` and the ledger's `CLAUDE.md` make audience validation
mandatory on every request carrying a token from the issuer, and name the relay's webhook (§ 5) and
an invoice's link (ADR-0053) as the only requests authenticated otherwise.

Related: ADR-0003 (one store), ADR-0004 (portability), ADR-0012 (the event bus gate), ADR-0016
(secrets), ADR-0017 (scale to zero), ADR-0022 (modules and components), ADR-0049 (the web client
where notifications are answered).

## Revisit when

* Delivery latency or a timeout on the request path becomes a complaint, which is the case for
  delivering off the request path.
* A requirement asks for digests, scheduled sending or throttling across channels, which is where a
  notification platform starts to earn its size.
* A runtime that stays on anyway — a component with its own schedule — exists, which makes a queue
  for delivery cheap.
