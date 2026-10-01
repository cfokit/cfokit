---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-01
decision-makers: [Geoff]
---

# ADR-0057: Push notifications are Web Push to the installed web client, sent by CFOKit's own process

**Requirements served:** `PLT-07`, `PLT-24`, `PLT-22`, `NFR-10`, `IAM-11`, `SOC2-17`.

## Context and Problem Statement

`PLT-07` requires CFOKit to reach the people who operate an entity when something needs them, on
channels they choose. [ADR-0052](0052-notifications-are-records-delivered-after-commit.md) makes
a notification a record, shown in the web client and to the agent everywhere, and delivered after
its commit through CFOKit's own channels. Email is its first channel. Email reaches an inbox; a
question that needs a person today is better as a notification on the device they carry.

The web client is a progressive web app, installable to a home screen or a desktop on every
platform `PLT-24` names ([ADR-0049](0049-cfokit-has-a-web-client.md) § 8). There is no native
application, and none is planned.

The constraints are ADR-0052's, applied to a second channel:

* Delivery happens in the process that committed the notification, right after the commit, with a
  short timeout, because the maintained target scales to zero and withdraws CPU once a response
  has returned (ADR-0017). Nothing holds a connection open.
* No provider SDK and no provider required (`NFR-10`, ADR-0004). A deployment on one machine, with
  no cloud account, must be able to offer the channel or simply not have it.
* A notification carries identifiers, the company's name and one link, never a figure, because it
  may be read on a lock screen (ADR-0052 § 6).
* Runtime dependencies are few, and each one is a decision.

Browsers deliver push to a web app through the Web Push standards: a subscription the browser
creates for the app (RFC 8030), messages encrypted to that subscription's keys (RFC 8291), and an
application server identified by a signed token (VAPID, RFC 8292). Each browser vendor runs its own
push service — Google's for Chrome and Edge, Mozilla's for Firefox, Apple's for Safari — and the
subscription's endpoint URL names which one. On iPhone and iPad, Web Push reaches a web app only
once it has been added to the home screen, from iOS and iPadOS 16.4.

## Decision Drivers

* `PLT-07` on the devices people carry, with the installed web client as the only app there is.
* The same delivery model as email: in-process, after commit, recorded, retried at the next
  hand-off (ADR-0052 § 3).
* No provider SDK, no provider account, and nothing a self-hosted deployment cannot run.
* A push service sees nothing of the books: not the question, not the company's name.
* Only the person turns push on for their own device; an agent cannot.
* No new runtime dependency unless the alternative is worse.
* A device that is gone stops being sent to.

## Considered Options

* Web Push, sent by CFOKit's process, built on `cryptography` and PyJWT
* Web Push through `pywebpush`
* Web Push with the encryption from `http-ece`
* Firebase Cloud Messaging through its SDKs
* A hosted push service (OneSignal and similar)
* Native applications with APNs and FCM

## Decision Outcome

Chosen option: "Web Push, sent by CFOKit's process, built on `cryptography` and PyJWT", because it
is the only option that reaches every browser's push service with no provider in the shipped
artifact and no new runtime dependency.

> Push is a channel in ADR-0052's sense. The web client subscribes a device through its service
> worker and registers the subscription with CFOKit; CFOKit stores it as the person's own record.
> When a notification is delivered, CFOKit encrypts its message to each of the recipient's
> subscriptions and posts it to the push service the subscription names, signed with the
> deployment's VAPID key. A deployment with no VAPID key has no push channel.

### 1. A subscription is the person's own record

A subscription — the endpoint URL and the two keys the browser generated for it — belongs to a
person, not to an entity: one device receives the person's notifications from every entity they
hold a role in. It is stored as a record of that person, with the device label the client supplies
and the time it was registered.

* `POST /push-subscriptions` registers one. It is refused to a principal acting for another (the
  `act` check of [ADR-0042](0042-person-only-acts-are-a-capability.md) § 2, applied alone), so an
  agent cannot add a device to someone's notifications.
* `DELETE /push-subscriptions/{subscription_id}` removes one of the caller's own, as above.
* `GET /push-subscriptions` lists the caller's own, so the web client can show which devices are on.
* `GET /push-subscriptions/application-server-key` returns the deployment's VAPID public key, which
  the browser needs to subscribe.

Each state-changing call carries an idempotency key and writes one `audit_log` row (ADR-0029). The
routes are published REST and go through gate 5 (ADR-0015); none is an MCP tool.

Removal is a row recording that the subscription ended, not a deletion, like every other change of
state. A person's erasure request (`PLT-22`) erases their subscriptions outright: an endpoint URL
identifies a device and is personal information (`SOC2-17`), and no retention obligation applies.

### 2. Sending is RFC 8030, 8291 and 8292, on what CFOKit already has

For each of the recipient's live subscriptions, CFOKit:

* builds the message — the notification's class as a title, its text, and its link — within
  ADR-0052 § 6's limits;
* encrypts it to the subscription's keys with `aes128gcm` as RFC 8291 specifies: an ephemeral P-256
  key, ECDH, HKDF and AES-GCM, all from `cryptography`, which is already installed beneath PyJWT;
* signs a VAPID token with ES256 using PyJWT, with the push service's origin as audience and the
  deployment's contact as subject;
* posts it to the endpoint with the standard library's HTTP client, with a `TTL` of one day, `normal`
  urgency, and the notification's identifier as `Topic`, so a retry replaces a message still waiting
  at the push service instead of adding a second.

The outcome is recorded against the notification as a message, as email's is (ADR-0052 § 4). A
`201` is accepted. A `404` or `410` means the subscription no longer exists: it is ended, and not
sent to again. Anything else is a failed hand-off, retried at the entity's next hand-off like any
other. A notification closed before then is not sent
([ADR-0056](0056-a-notification-is-open-until-answered-or-dismissed.md) § 6).

The push service sees an endpoint, a ciphertext, the timing and the size, and nothing else. It is
not a vendor that receives personal information in the clear.

### 3. The service worker shows it; a tap opens the question

The web client's service worker handles the `push` event by showing a system notification with the
message's title and text, and the `notificationclick` event by focusing an open window of the
client, or opening one, at the notification's link. It caches nothing it receives (ADR-0049 § 8).
Every push results in a visible notification, which browsers require.

The client asks for permission only when the person chooses to turn notifications on for this
device, never on load: Safari grants the prompt only from a user gesture, and an unprompted request
is the one browsers learn to suppress. On iPhone and iPad, where push needs the app on the home
screen, the client says so and explains how, instead of offering a switch that cannot work.

Which classes of notification arrive by push is the person's channel setting, as ADR-0052 § 2
provides for every channel.

### 4. Configured like any other secret, and optional like email

A deployment that offers push sets two environment variables: the VAPID private key, as a secret
populated out of band (ADR-0016), and the contact address the VAPID token names. The public key is
derived from the private one. With no key set, there is no push channel and no subscription routes
are served; the client does not offer the switch. The key pair is generated once per deployment,
with a command CFOKit provides, and rotating it invalidates every subscription, which the client
renews on its next load.

Push needs a secure context, which a deployment has over HTTPS and a laptop has at
`http://localhost`.

### Consequences

* Good, because a question reaches the person's phone or desktop as a system notification, through
  the app they installed, on every major browser.
* Good, because no provider SDK or account is involved, and a self-hosted deployment offers push by
  setting one key.
* Good, because the push service carries only ciphertext.
* Good, because no runtime dependency is added.
* Bad, because CFOKit owns about forty lines of message encryption. Every primitive is
  `cryptography`'s, and RFC 8291's worked example checks the composition byte for byte, but the
  code is ours to keep correct.
* Bad, because on iPhone and iPad push works only from the home-screen app, which is a step many
  people will not take.
* Bad, because push services are outside CFOKit's control: delivery is best effort, and a device
  that is off for longer than the TTL misses the message. The notification is still open in the
  web client and to the agent.
* Neutral, because each notification is sent once per subscription, so a person with three devices
  receives it three times, as any push-enabled product does.

### Confirmation

* A conformance case reproduces RFC 8291 Appendix A: from its keys, salt and plaintext, the
  encryption yields its ciphertext exactly. It cites the RFC (ADR-0036 layer 2).
* A test verifies the VAPID token against RFC 8292: ES256, the endpoint's origin as `aud`, an `exp`
  within a day, and the configured contact as `sub`.
* A test against a stand-in push service asserts that a delivery posts the encrypted message with
  the `TTL`, `Urgency`, `Topic` and `Authorization` headers; that a `410` ends the subscription and
  it is not sent to again; that a `500` is recorded as failed and retried at the next hand-off; and
  that a closed notification is not sent.
* A test asserts that registering or removing a subscription with an `act` claim is refused, that a
  person cannot remove another's, and that with no VAPID key the routes are not served.
* An end-to-end test in Chromium registers a subscription through the service worker against the
  local stack. Delivery through a real push service is not tested in CI, which reaches no vendor.

## Pros and Cons of the Options

### Web Push, sent by CFOKit's process, built on `cryptography` and PyJWT

* Good, because it meets every driver.
* Bad, because the encryption's composition is ours, guarded by the RFC's worked example.

### Web Push through `pywebpush`

The standard Python library for exactly this, maintained in the web-push-libs organization.

* Good, because it is the well-trodden implementation and handles every detail above.
* Bad, because it brings `aiohttp` and `requests` and their dependencies into the runtime for one
  HTTPS POST that the standard library makes, against `CLAUDE.md`'s rule that runtime dependencies
  are few and load-bearing. It and `py-vapid` beneath it are MPL-2.0, which is permitted for a
  server dependency and is not the reason.

### Web Push with the encryption from `http-ece`

The strongest alternative: one small package, MIT, depending only on `cryptography`, written by the
author of the encryption RFCs, doing exactly the part of this that is easiest to get wrong.

* Good, because the encryption would be a maintained library's rather than ours.
* Bad, because it is a runtime dependency added to save about forty lines whose correctness is
  checked byte for byte by the same RFC test either way, and whose specification is fixed. If the
  RFC's example did not exist, this option would win.

### Firebase Cloud Messaging through its SDKs

* Good, because one service fronts every platform, with a console, analytics and topic messaging.
* Bad, because it is a provider SDK on the server and Google's script in the client, and every
  deployment, including a self-hosted one, would need a Firebase project (`NFR-10`, ADR-0004).
  Web Push already reaches Chrome's push service, which is FCM, without any of that.

### A hosted push service (OneSignal and similar)

* Good, because subscription management, delivery and analytics would be someone else's.
* Bad, because it is a vendor in the path of every notification, a third-party script in a client
  whose CSP allows only its own origin (ADR-0049 § 6), and an account every deployment would need.

### Native applications with APNs and FCM

* Good, because push on iPhone would not depend on the home-screen step.
* Bad, because there is no native application, and building two to carry notifications reverses
  ADR-0049's one client for every device.

## More Information

**Follow-on obligations.**

* The command that generates a deployment's VAPID key pair, and `infra/README.md`'s entries for the
  two variables.
* The channel setting per person and class, which ADR-0052 § 2 names and push is the second
  channel to need.
* `PLT-22`'s erasure covering subscriptions.

**Reversal cost.** Low. The channel is one implementation behind ADR-0052's channel interface, and
subscriptions are renewed by the client; replacing the sending code, or adopting `http-ece` for the
encryption, changes nothing outside it.

Related: ADR-0052 (channels), ADR-0056 (what is open), ADR-0049 (the installed web client),
ADR-0042 (acting as oneself), RFC 8030, RFC 8291, RFC 8292.

## Revisit when

* A native application exists for another reason, which makes APNs and FCM worth their cost.
* A browser that people use drops Web Push or changes how it requires permission.
* Encryption bugs, or a revision of RFC 8291, make a maintained library the safer owner of that code.
