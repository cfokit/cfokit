---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-06
decision-makers: [Geoff Scott]
---

# ADR-0062: A bank feed is synchronized by CFOKit's own process into account activity, through a provider protocol, and only a posted transaction becomes a line

**Requirements served:** `BKP-01`, `BKP-02`, `BKP-16`, `BKP-19`, `BKP-21`, `IAM-10`, `NFR-11`,
`NFR-12`, `NFR-21`, `PLT-07`, `PLT-15`, `SOC2-14`.

## Context and Problem Statement

`BKP-01` requires transactions to arrive from bank and card accounts without manual entry, and
`BKP-16` requires them to arrive with no person triggering them, when the source reports new activity
and in any case within an interval the deployment sets. Today every line
arrives from a statement a person uploads ([ADR-0046](0046-a-statement-proves-itself.md)), and is
drafted rather than posted, because a model transcribed it
([ADR-0047](0047-an-uploaded-line-is-drafted.md)).

A feed is the case `BKP-09` exists for: an approved pattern is never asked about again, so a line a
rule resolves is posted without a person. That is safe only if the line really came from the bank.
ADR-0047 records the gap: `source_kind` is supplied by the caller, and "a session describing an
upload as a feed would post it".

Where a feed runs was left open by [ADR-0022](0022-tiny-ledger-modules-and-components.md) § 5. Its
criteria pull both ways: a feed holds a third-party credential and runs unattended, which argue for a
separate component; it writes what the books then code, which argues for a module.
[ADR-0045](0045-assignment-is-stored-rules.md) § 1 assumed a component.

The provider for the hosted offering is Plaid ([journey](../product/journey.md)). What it delivers
shapes everything downstream:

* **A changing stream, not a record.** `/transactions/sync` returns `added`, `modified` and `removed`
  since a cursor. A pending transaction that posts arrives as the pending one removed and the posted
  one added, linked by `pending_transaction_id`, usually within 1–5 business days and rarely up to
  14; Capital One and USAA send no pending transactions at all. Plaid states that "a posted
  transaction cannot necessarily be considered immutable".
* **Paging is all-or-nothing.** The sync loop runs while `has_more` is true, and Plaid's guidance
  is to "retrieve all available updates before persisting", restarting from the loop's first cursor
  on any error, `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION` included.
* **History is fixed at link.** `days_requested` defaults to 90 and allows up to 730, and the
  initial and historical updates complete later, announced by status in the sync response.
* **Identities shift.** An `account_id` can change "if Plaid can't reconcile the account".
  `persistent_account_id` is stable only at a few banks that tokenize account numbers.
* **A long-lived secret.** The access token does not expire and "should never be exposed on the
  client side". `/item/remove` is what ends billing for the connection. Linking one institution
  twice is billed twice, and Plaid documents how to detect it before the token exchange.
* **Connections break.** `ITEM_LOGIN_REQUIRED`, `PENDING_DISCONNECT` seven days before consent
  lapses, and `NEW_ACCOUNTS_AVAILABLE` are repaired by Link in update mode, by the person, and the
  access token survives the repair.
* **Balances are cached.** Balances from the sync and from `/accounts/get` are as of the last
  update. Only `/accounts/balance/get` is live, limited to 30 calls an hour per connection.

Business accounts carry no data access right under the CFPB's Personal Financial Data Rights rule:
"consumer" means a natural person, and the rule is in any case enjoined pending reconsideration. A
business's feed rests on the provider's own agreements with institutions.

A deployment may also have no provider at all: `BKP-03` and `NFR-11` require the product to run
with no third-party account, and `NFR-21` requires a contributor to run the whole suite with no
credentials.

## Decision Drivers

* A rule may post only what came from the bank, so no caller may be able to claim a line is from a
  feed.
* The books are append-only (ADR-0007); the source is not. A change the source makes after a line
  is booked must never alter the books silently.
* What a sync was expected to cover, and what it delivered, is recorded (`BKP-21`).
* Bank credentials go to the provider, never to CFOKit, an agent or a model (`IAM-10`). The
  provider's token is a secret held by CFOKit's process alone, and the process that answers the
  internet cannot read it.
* Key custody, rotation and revocation are stated properties of a deployment (`SOC2-14`).
* A provider can be added as a contribution against a stable extension point (`NFR-12`), and none
  is needed to build, test or run the product (`NFR-11`, `NFR-21`).
* No runtime dependency is added without a reason (root `CLAUDE.md`).

## Considered Options

* Account activity synchronizes the feed in CFOKit's own process, through a provider protocol
* A separate component posting lines through the published API
* Apply every change the provider reports to the books, by reversal where needed
* Take the provider's PDF statements instead of its transactions
* Plaid's Python SDK rather than HTTPS from the standard library
* The token key in the deployment's environment
* A different provider for the hosted offering

## Decision Outcome

Chosen option: "Account activity synchronizes the feed in CFOKit's own process, through a provider
protocol", because a line no caller can forge is the only kind a rule can be trusted to post.

> A feed is a connection held by `cfokit.activity`, synchronized as a kind of unattended work
> ([ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md)) through a provider protocol. Every
> change the provider reports is stored as received. Only a posted transaction becomes a line, and
> a change to a line already coded is a question for a person, never an edit to the books. No
> published interface accepts a line as coming from a feed.

### 1. A feed line has one way in

The sync is a handler in `cfokit.activity`, run by the worker in CFOKit's own process. It is the only
code that creates a line whose source is a feed. No REST endpoint or MCP tool accepts a candidate
with `source_kind: feed`; a caller that sends one is refused.

That makes `source_kind` a fact the server established rather than one a caller asserted, which is
what lets a rule post a feed line while an uploaded one stays drafted (ADR-0047). It is a module by
ADR-0022 § 3's default: the credential argument for a component is met by § 6, and the scheduled
runtime shape by ADR-0061's worker.

### 2. A provider is a protocol, and a deployment configures one or none

The protocol has five operations: begin a link session, complete it, synchronize from a cursor,
report the connection's health, and remove the connection. A synchronization returns every change
since the cursor, the next cursor, and the provider's own account of how current its data is.

Plaid is the provider the hosted offering uses. A deployment names its provider and its credentials
in environment variables (ADR-0004); a self-hosted deployment may bring its own Plaid account. With
none configured, there is no feed: no webhook route is served, no feed work runs, and connecting an
account says this deployment has no feed. Uploads remain (`BKP-03`), as an unsent invoice remains a
link where a deployment has no mail relay (`PLT-06`).

**A replay provider stands in for Plaid wherever no account should be needed.** It is the Plaid
provider with its HTTPS calls answered from responses recorded from Plaid's Sandbox, so the code
that talks to Plaid is the code under test. In the web client a stand-in replaces Plaid Link and
completes without a bank, and the syncs play a scripted sequence — a first sync with history, pending
transactions that post, a modification and a removal of coded lines, a login required and repaired.
The recordings are Plaid's, so a test's expected value comes from outside the implementation
(ADR-0036). It serves two uses:

* **The test suite**, which exercises the feed end to end with no account and no network.
* **A contributor's local stack**, with `FEED_PROVIDER=replay`, so connect, sync, match, code and
  question can be clicked through in a browser from a clean checkout with no credentials
  (`NFR-21`). Its webhook is a button in the web client that enqueues a sync, as Plaid's would.

**It runs only on a loopback address.** The server refuses to start with `FEED_PROVIDER=replay`
unless `PUBLIC_BASE_URL` names `localhost`, a `.localhost` name or a loopback address, because its
lines are invented and a rule posts them into whatever entity it is connected to. Its institution is
named as a replay, and every line it produces says so in the reference it carries. On the local
stack, which holds real books (ADR-0018), it is connected to an entity made for trying it.

A developer with their own Plaid account may instead set Plaid's Sandbox keys, and reach webhooks
through a tunnel or rely on the backstop interval. Tests against the Sandbox run only where those
keys are present.

Payment processors (`BKP-02`) are further providers of the same protocol. Plaid is called over HTTPS
with the standard library, as the mail relay is ([ADR-0052](0052-notifications-are-records-delivered-after-commit.md)).

### 3. Connecting happens in the web client, and is a person's act

The person links an account through Plaid Link, embedded in the web client
([ADR-0049](0049-cfokit-has-a-web-client.md)). Their bank credentials go to Plaid and never to
CFOKit, an agent or a model (`IAM-10`). CFOKit creates the link token, naming the person by an
opaque identifier rather than an email address, and exchanges the public token on its server at
once.

**A duplicate is refused before the exchange.** If the institution and an account's mask match a
connection the entity already holds, the person is sent to repair that connection instead.

**Each provider account is mapped to a ledger account**, by a row the person confirms when
connecting. The mapping is what a line names, never the provider's `account_id`, so an id the
provider changes is re-pointed rather than becoming a new account.

Connecting, re-mapping and disconnecting are configuration changes, each recorded with who made it
and the prior value (`PLT-15`). Disconnecting stops the connection's syncs at once and enqueues its
removal at the provider, which is what ends billing. The removal needs the token, so it is
unattended work (§ 6).

### 4. A sync stores what the provider said, then advances

The handler runs the provider's sync loop to its end before writing anything. An error at any page,
a mutation during paging included, restarts the loop from the cursor it began with. Then one
transaction:

* stores each change as received — added, modified or removed, pending or posted — keyed by the
  provider's transaction id, append-only, as the statement's lines are stored as stated (ADR-0046 § 2);
* advances the cursor;
* records the sync: the window it was run for, the cursor before and after, the counts of each kind
  of change, and the provider's account of how current it is (`BKP-21`).

A sync that delivered nothing records a sync with nothing in it. A source that has stopped
refreshing is visible as one whose own currency has stopped advancing, which is how "silently
delivers nothing" is told apart from "an empty result". A connection that stays stale beyond a bound
raises a notification (`PLT-07`).

### 5. Only a posted transaction becomes a line

A posted transaction added by the provider becomes a line, and its candidate goes to assignment:
matched first ([ADR-0059](0059-a-line-is-matched-before-it-is-coded.md)), then coded by rule. Its
reference is `feed:{connection}:{provider transaction id}`, which assignment carries into
`derived_from` (`BKP-19`) and its idempotency key, so a sync replayed codes nothing twice.

A pending transaction is stored and never becomes a line. Its amount and date can change before it
posts, and some institutions never send one, so booking pending activity would book a guess and then
correct it.

**A change to a line already coded is a question.** When the provider later modifies or removes a
posted transaction, the change is stored and the books are untouched. A notification asks a person,
whose answer is a correcting entry or nothing (ADR-0007). The books never move because a source
changed its mind unseen.

### 6. The token is sealed by a key no CFOKit process holds

The access token is stored sealed, through a protocol with two operations — seal and open — and two
implementations:

* **On GCP, Cloud KMS.** A symmetric key, `feed-tokens`, on the `cfokit` key ring that already holds
  the database's key, rotating every 90 days and protected from destruction as that one is. The
  token is encrypted by KMS directly; a Plaid token is far below the 64 KiB a software key accepts.
  The key never leaves KMS, so no environment, image or memory dump holds it.
* **Everywhere else, AES-256-GCM** with `cryptography`, already a dependency
  ([ADR-0057](0057-push-is-web-push-sent-by-cfokit.md)), under a key the deployment supplies as
  `FEED_TOKEN_KEY`. It is the local default ADR-0004 requires, and needs no cloud account.

**Each ciphertext is bound to its connection.** The entity and connection ids are the additional
authenticated data of both implementations, so a sealed token copied into another connection's row
does not open.

**Sealing and opening are separate grants.** The API's service account, `cfokit-service`, holds
`roles/cloudkms.cryptoKeyEncrypter` on the key and nothing else: it seals the token when the person
finishes Link, and can never read one back. The worker's, `cfokit-work`
([ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md) § 3), holds
`roles/cloudkms.cryptoKeyDecrypter`: only syncs and removals open a token, and both are unattended
work. The process that faces the internet cannot read any token at all, which is the isolation a
separate component would have offered (ADR-0022 § 3), had by an IAM grant rather than a second
deployable.

**Every open is evidence.** KMS writes a Data Access audit log entry for each encrypt and decrypt,
and `infra/gcp/audit.tf` already keeps them for 400 days. Rotation creates a new primary version,
and older ones keep opening what they sealed, so nothing is re-encrypted. Disabling the key makes
every stored token unreadable at once, which is revocation as a property of the deployment
(`SOC2-14`).

KMS is called over HTTPS with the standard library, authenticated by the service account's access
token from Cloud Run's metadata server. That is the process's identity, not its configuration, which
is what ADR-0004 keeps out of metadata: the key's name still arrives as `FEED_TOKEN_KMS_KEY`.

No interface returns a token, no log line carries one, and no model sees one. After the provider
confirms a removal, the sealed token is deleted: it is a credential, not a financial record.

### 7. A broken connection is the person's to repair

When the provider reports that a connection needs the person — a login required, consent about to
lapse, new accounts available — the state is recorded on the connection and a notification is
raised. The person repairs it in the web client with Link in update mode. Syncs for that connection
are not retried in the meantime; they resume when the provider reports it repaired, and the next
sync's window covers the gap.

### 8. A feed's balance is not a reconciliation

Reconciliation (`BKP-15`) is against the bank's own statement, as [the journey](../product/journey.md)
states: a feed's balance comes from the same source as its transactions, and Plaid's is cached. A
feed's balance may be shown beside the books as a cross-check, and is never recorded as a
statement.

### Consequences

* Good, because a rule posts feed lines straight through, and nothing outside the server can
  produce one — which closes the hole ADR-0047 recorded for feeds.
* Good, because the books never change because the source did. Every change the provider makes is
  kept, and the ones that matter reach a person.
* Good, because a provider is an implementation of five operations, and the suite needs none.
* Good, because no dependency is added.
* Good, because no CFOKit process holds the key, the internet-facing one cannot open a token, and
  every open is in the audit log.
* Bad, because pending activity is invisible to the books, so a cash view lags the bank by a few
  days. That is the books being right rather than early.
* Bad, because a feed requires the web client to connect. A person working only in an agent cannot
  link an account there.
* Bad, because every sync opens its token with a call to KMS, so a KMS outage stops syncs. They
  wait as due work and resume (ADR-0061); nothing is lost.
* Bad, because the seal has two implementations, and the one production uses is exercised only on
  GCP. The local one is what the suite tests.
* Bad, because Plaid's client is ours to maintain against its API changes, rather than Plaid's.
* Neutral, because every feed run is one more kind of unattended work, which ADR-0061 already
  accounts for.

### Confirmation

* A test asserts that every REST endpoint and MCP tool that accepts a candidate refuses
  `source_kind: feed`.
* A test asserts that the server refuses to start with `FEED_PROVIDER=replay` and a
  `PUBLIC_BASE_URL` that is not a loopback address.
* Tests against the replay provider assert that: a failure mid-loop leaves the cursor and the
  stored changes unchanged; a pending transaction never becomes a line; pending-then-posted produces
  one line; a sync replayed codes nothing new; a modification or removal of a coded line changes no
  posting and raises a notification; a duplicate connection is refused before exchange; a re-mapped
  account keeps its lines' ledger account.
* A test asserts that no response body and no log record contains a stored token, by planting a
  known token and searching for it.
* A test asserts that a sealed token moved to another connection's row fails to open, for the local
  implementation.
* `infra/gcp/setup/check.sh` asserts the key's IAM policy: `cfokit-service` may only encrypt,
  `cfokit-work` may only decrypt, and no one else holds either.
* A test against Plaid's sandbox runs only where Plaid credentials are present. CI gate 2 runs with
  none, so it is not gated.

Not gated: that a self-hosted deployment keeps `FEED_TOKEN_KEY` from processes that do not need it.
The local implementation has one key for sealing and opening, so that separation is GCP's.

## Pros and Cons of the Options

### Account activity synchronizes the feed in CFOKit's own process, through a provider protocol

* Good, because the server establishes where a line came from.
* Good, because the sync, the source's record and the coverage commit together.
* Bad, because the token and its key live in the same deployment as the API.

### A separate component posting lines through the published API

ADR-0022 § 3's verdict for anything holding third-party credentials and running on a schedule. The
component authenticates as an OAuth client ([ADR-0032](0032-component-authentication-and-configuration.md)),
holds the token where the API never sees it, and posts lines over REST.

* Good, because a compromise of the API alone does not reach the provider's tokens.
* Bad, because it needs a published endpoint that accepts lines as a feed's. Then any client holding
  that grant can post a line a rule will book — ADR-0047's hole, moved to a client credential.
* Bad, because the isolation it offers is had without it. With sealing and opening granted
  separately (§ 6), the API cannot read a token either; it holds Plaid's client secret regardless,
  because the public token is exchanged when the person finishes Link.
* Bad, because it is a second deployed client, a second credential and a second process to operate,
  for one provider's calls.

### Apply every change the provider reports to the books, by reversal where needed

What a bank-feed mirror does: the books follow the provider, pending included.

* Good, because the books always agree with the bank's current view, with no questions asked.
* Bad, because pending activity changes and disappears in normal operation, and Capital One and USAA
  send none, so the books would be corrected routinely and inconsistently by institution.
* Bad, because reversing a posted entry in a period already reconciled or closed, with no person
  involved, is what ADR-0007 and `LED-11` exist to prevent.

### Take the provider's PDF statements instead of its transactions

Plaid Statements returns the bank's own statement, which ADR-0046's balance proof could check.

* Good, because it is the bank's own document, and proves itself.
* Bad, because it covers depository accounts only, about 40% of US depository accounts, and no cards.
* Bad, because a statement arrives once a month, which is not `BKP-16`'s current books. It is a
  reconciliation source, which is § 8's, not a feed.

### Plaid's Python SDK rather than HTTPS from the standard library

`plaid-python` is MIT, maintained by Plaid, and generated from its API definition.

* Good, because request and response types track Plaid's API without our effort.
* Bad, because it is a seventh runtime dependency, generated across Plaid's whole API, for the
  handful of endpoints the protocol uses: create and exchange a link token, sync, item status,
  accounts, remove, and the webhook verification key.
* Bad, because the replaying provider tests the client we write. A generated client would put the
  part we most need to test behind code we do not own.

### A different provider for the hosted offering

* **Teller** is self-serve and cheap — $0.30 per connection a month, with 100 live connections free
  — but offers no change cursor: Teller recommends re-reading the last 7–10 days because a
  transaction's date changes when it posts. Business account support is not documented.
* **Stripe Financial Connections** is $0.30 per connection a month with a daily refresh, but returns
  at most 180 days of history, against Plaid's 730, which is short of a year for a business
  connecting mid-year.
* **MX, Finicity and Akoya** are priced only through sales, and production requires a contract.
* **SimpleFIN Bridge** is $15 a year, paid by the person, and is the natural option for a self-hoster
  bringing their own access, but allows at most 24 requests a day with a 90-day window each, and
  offers no cursor, no webhook and no statements.
* **GoCardless Bank Account Data** has closed new signups and covers the EEA only.

Plaid has a change cursor, up to 730 days of history, statements for the accounts that have them,
self-serve pay-as-you-go pricing, and a production review of "a couple of business days". The
protocol is what keeps the choice reversible.

### The token key in the deployment's environment

AES-256-GCM under a key supplied as a secret, on every target.

* Good, because it is one implementation, tested everywhere it runs, with no network call to open a
  token.
* Bad, because the key sits in the environment of every process given it. Anyone who can read the
  API's secrets reads every token, and no record shows that they did.
* Bad, because sealing and opening cannot be granted apart, so the internet-facing process can read
  every token.
* Bad, because rotation is a re-encryption we write, and revocation is deleting a secret every
  process has already loaded.

It remains the implementation where there is no KMS, which is the local default ADR-0004 requires.

## More Information

**Follow-on obligations.**

* [ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md) gains a feed kind: operational and
  ingestion, missed windows coalesced, throttled to Plaid's 2,500 sync calls a minute per client. Its
  backstop interval is `FEED_SYNC_INTERVAL`, six hours by default, and a connection synchronized
  within it is not synchronized again by the backstop. No entity sets it: the provider's
  webhook drives syncs, Plaid refreshes from an institution on its own timing one to four times a
  day, and it bills per connection rather than per call, so a customer's choice of interval would buy
  neither fresher books nor a lower bill (`BKP-16`).
* [ADR-0063](0063-a-feed-provider-webhook-only-marks-a-connection-due.md) decides the provider's
  webhook, the signal that a connection has new data.
* [ADR-0045](0045-assignment-is-stored-rules.md) § 1 is corrected in place: a feed is synchronized by
  account activity in CFOKit's process, not by a component.
* [ADR-0047](0047-an-uploaded-line-is-drafted.md)'s consequence on caller-supplied `source_kind` is
  corrected in place to name § 1 here.
* `compose.dev.yaml` documents `FEED_PROVIDER=replay`, and `CONTRIBUTING.md` describes trying the
  feed with it and with Plaid's Sandbox.
* `infra/README.md` gains `FEED_PROVIDER` (`plaid`, `replay`, or unset) and the provider's credentials, each a secret container
  populated out of band; `FEED_TOKEN_KMS_KEY`, the KMS key's name; and `FEED_TOKEN_KEY`, the local
  key, for a deployment without KMS. One of the last two is set wherever a provider is.
* `infra/gcp/` gains the `feed-tokens` key on the `cfokit` ring, with a 90-day rotation and
  `prevent_destroy`, and its two IAM grants. A key version costs about $0.06 a month and an operation
  $0.03 per 10,000, so a few hundred connections synchronized several times a day cost cents a
  month. Rotated versions accumulate at four a year and stay billed until destroyed, which is never
  while a token sealed by one survives.
* `src/cfokit/activity/CLAUDE.md` is created with the rule of § 1: nothing outside the sync handler
  creates a line whose source is a feed, and no interface accepts one.
* Before the hosted offering connects a customer's bank, Plaid's production review and its security
  questionnaire are completed. The questionnaire's topics are visible only in Plaid's dashboard and
  are not verified here.
* Plaid's item status is the source of § 4's "how current" for Plaid. Which field reports the last
  successful refresh from the institution was not verified against Plaid's reference.

**Reversal cost.** Low for the provider: a second one is another implementation of the protocol.
Low for § 6: moving between seals is opening each token with one and sealing it with the
other, which the worker can do as work. A destroyed KMS key, though, is every connection relinked by
its person: the key is guarded as the database's is. Moderate for § 5: lines already coded from posted transactions would need re-reading if pending
activity were ever booked, though the stored changes keep everything needed to do it. High for § 1:
once rules post feed lines straight through, opening a published path for feed lines would make
every such posting suspect.

## Revisit when

* The rewritten CFPB rule is published and extends a data access right to business accounts, or an
  institution offers direct FDX access worth a provider of its own.
* Self-hosters ask for a feed without a Plaid account. SimpleFIN Bridge is the candidate provider.
* A person working only in an agent needs to connect an account, which would need a link the agent
  can hand them rather than the web client's screen.
* An examiner or a customer requires keys in hardware. An HSM key version is about $1 a month,
  and the protocol is unchanged.
* Questions about changed lines become frequent enough to be a burden, which would argue for a
  narrow rule — a removal before the line's period is reconciled — that a person approves once.
