---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-06
decision-makers: [Geoff Scott]
---

# ADR-0063: A feed provider's webhook is a signed way in that only marks one connection's sync as due

**Requirements served:** `BKP-16`, `PLT-14`, `NFR-04`, `NFR-06`, `SOC2-15`.

## Context and Problem Statement

A bank feed ([ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md)) is synchronized as
unattended work ([ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md)). Something has to say
when. A schedule can, but Plaid's model is that it announces new data: `SYNC_UPDATES_AVAILABLE`
"will fire whenever any change has happened to the Item's transactions", its launch checklist lists
webhooks as required for Transactions, and it refreshes from an institution one to four times a day
at times only it knows. A schedule alone either polls far more often than data changes, or leaves the
books a schedule's interval behind a refresh.

A webhook is a request from Plaid with no issuer token. Root `CLAUDE.md` allows an entity's data to
be reached without one in two ways only — a link of the kind `IAM-20` defines, and the mail relay's
signed event webhook ([ADR-0052](0052-notifications-are-records-delivered-after-commit.md)) — and
requires a new way in to have its own record. This is that record.

What Plaid sends, and how:

* **Signed.** Each request carries a JWT in the `Plaid-Verification` header, signed ES256 by a key
  fetched by its `kid` from `/webhook_verification_key/get`. Its `iat` is to be rejected when more
  than five minutes old, and its `request_body_sha256` compared with the SHA-256 of the raw body.
* **Retried, duplicated and unordered.** A request not answered 200 within 10 seconds is retried
  with backoff for up to 24 hours and then dropped. Plaid asks receivers to "handle duplicate and
  out-of-order webhooks" and to keep handlers minimal.
* **Addressed per connection.** The webhook URL is set for each connection when its link token is
  created, and the body names the connection by Plaid's `item_id`.
* **From addresses that change.** Plaid publishes its source IPs and says they are subject to change.

A self-hosted deployment may have no address Plaid can reach. It still has the schedule.

## Decision Drivers

* The webhook reads nothing and reaches no entity but the one its connection belongs to
  (`NFR-04`, `SOC2-15`).
* A request is shown to be from the provider and meant for this deployment before anything is
  written (`NFR-06`).
* A forged or replayed request can at worst cause a sync that would have happened anyway.
* Acknowledged means recorded: a 200 with nothing enqueued is a lost sync Plaid will not resend.
* Answer within 10 seconds, whatever the connection's history.
* A deployment without a reachable address loses latency, not capability.

## Considered Options

* A signed webhook that verifies the request and enqueues the connection's sync
* A webhook that runs the sync within the request
* No webhook: the schedule alone
* A webhook that records the events it receives
* Authenticating the webhook by Plaid's source addresses

## Decision Outcome

Chosen option: "A signed webhook that verifies the request and enqueues the connection's sync",
because a request that can only make an already-scheduled sync happen sooner is harmless even if
forged, and verifying it makes even that impossible.

> CFOKit serves one webhook route per provider, outside its REST interface. A request is accepted
> only with a valid signature over its exact body, recently issued, naming a connection in the
> entity its URL names. Its only effect is to enqueue that connection's sync. Everything the sync
> learns, it learns from the provider.

### 1. The URL names the entity and the connection

The webhook URL given to Plaid for a connection is
`{PUBLIC_BASE_URL}/webhooks/feed/plaid/{entity}/{connection}`, built from `PUBLIC_BASE_URL` and
never from a request header. The handler sets that entity's scope before it reads anything, finds
the connection under row-level security, and requires the signed body's `item_id` to equal the
connection's. A request naming a connection not in that entity, or an `item_id` not its own, is
discarded. Nothing is looked up across entities.

### 2. The signature is the whole authentication

The JWT is verified with PyJWT, already a dependency, requiring ES256. The key is fetched by `kid`
from Plaid and cached; an unknown `kid` fetches again, which is how a rotated key is learned. A
token issued more than five minutes ago is refused, and the body's SHA-256 is compared with the
signed one in constant time, over the raw bytes received. No issuer token is involved, so audience
validation and entity grants do not apply: as with the mail relay, the signature is what shows the
request is the provider's and meant for this deployment.

### 3. It writes one thing

A verified request enqueues a sync of its connection, coalescing with one already waiting, and
writes one `audit_log` row naming the provider as the actor. It stores nothing from the body. Every
webhook Plaid sends for a connection — new transactions, a login required, new accounts — has the
same effect, because the sync reads the connection's state from the provider itself (ADR-0062 § 4
and § 7). Duplicate and out-of-order requests are therefore harmless: the second joins the first,
and order carries no information.

It answers 200 once the enqueue commits. That is a few milliseconds of work, whatever the
connection's history.

### 4. Without a reachable address, the schedule suffices

The route is served only where a feed provider is configured. A connection is created with a webhook
URL only where `PUBLIC_BASE_URL` is set. Where it is not, or Plaid cannot reach it, the
connection's schedule syncs it, which Plaid's own guidance requires as a backstop anyway. The books
are then up to one schedule interval behind, and nothing else differs.

### Consequences

* Good, because syncs follow the provider's refreshes rather than a guess at them.
* Good, because the most a valid request can do is start a sync early, and the most an invalid one
  can do is be refused.
* Good, because the webhook stores nothing it was told, so there is no untrusted content to mark
  (`BKP-20`) and none to retain.
* Bad, because it is a third way to reach an entity without an issuer token, and a public endpoint
  that anyone can send requests to.
* Bad, because verification fetches Plaid's key over the network on a cache miss, so a request can
  wait on Plaid. Refusing it on failure is safe, since Plaid retries.
* Neutral, because the route is Plaid's format, which no third party builds against, so it is not a
  published interface in ADR-0015's sense and is absent from the OpenAPI document, as the mail
  relay's is.

### Confirmation

* Tests assert that a request with a missing signature, a signature by another key, an `iat` older
  than five minutes, a body that differs from the signed hash by one byte, an `item_id` other than
  the connection's, or a connection outside the named entity writes nothing.
* A test asserts that a valid request enqueues exactly one run, that a second coalesces with it, and
  that the request stores nothing from its body.
* A test asserts the route is absent from the generated OpenAPI document.
* Root `CLAUDE.md`'s list of ways to reach an entity without an issuer token names this webhook, and
  changes to it need human review, as every authentication change does.

## Pros and Cons of the Options

### A signed webhook that verifies the request and enqueues the connection's sync

* Good, because its effect is bounded to something the schedule would do anyway.
* Bad, because it adds a public route and a key fetch.

### A webhook that runs the sync within the request

* Good, because the sync starts without waiting for the worker to claim it.
* Bad, because a first sync can page through up to 730 days of history, and Plaid gives up on a
  request after 10 seconds and retries it. A slow sync becomes a retried one, then a duplicated one.
* Bad, because it holds an entity's lock and a provider conversation open inside a public request.

### No webhook: the schedule alone

* Good, because there is no new way in at all.
* Bad, because Plaid's launch checklist lists webhooks as required for Transactions.
* Bad, because the books lag each refresh by up to a schedule interval, and polling often enough to
  close that gap is polling mostly for nothing, against a per-connection limit.

It is what a deployment without a reachable address does (§ 4), so it is kept as the fallback, not
as the design.

### A webhook that records the events it receives

* Good, because the event history would be kept, as the mail relay's delivery events are.
* Bad, because nothing in Plaid's events is a fact the sync does not learn from the provider
  directly, and stored with the authority of a signature it would be a second account of a
  connection's state that could disagree with the first.
* Bad, because it makes the webhook a writer of content, which is the property that keeps it
  harmless.

### Authenticating the webhook by Plaid's source addresses

* Good, because it is simple and needs no key.
* Bad, because Plaid says the addresses are subject to change, so an allowlist fails closed without
  warning when they do.
* Bad, because an address is not authentication. Behind a load balancer or proxy, the address a
  service sees is a header, and root `CLAUDE.md` holds that headers lie.

## More Information

**Follow-on obligations.**

* Root `CLAUDE.md`'s Authentication section names this webhook beside the mail relay's as a way to
  reach an entity without an issuer token.
* On GCP the route is served through the existing load balancer. `infra/gcp/setup/check.sh` checks
  that it refuses an unsigned request.
* A provider other than Plaid that offers webhooks gets a route of its own under the same rules: a
  signature verified over the exact body, the entity and connection named in the URL, and one
  enqueue as its only effect.

**Reversal cost.** Low. Removing the route leaves every connection syncing on its schedule, and
nothing stored depends on a webhook having arrived.

## Revisit when

* Plaid changes its signing scheme or stops requiring webhooks.
* A provider's webhook carries data that cannot be fetched afterwards. The enqueue-only rule then
  stops being sufficient, and storing what it carries needs this record superseded.
* Requests to the route that fail verification are seen in volume, which would make rate limiting it
  at the load balancer worth a decision.
