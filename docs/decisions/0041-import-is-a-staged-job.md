---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-09
decision-makers: [Geoff]
---

# ADR-0041: An import is a staged job over an uploaded archive, not a tool call over a mounted file

**Requirements served:** `IMP-01`, `IMP-03`, `IMP-05`, `IMP-08`, `NFR-04`, `PLT-02`, `SOC1-14`.

## Context and Problem Statement

[ADR-0040](0040-import-is-the-first-module.md) settled where import lives, what it is called, and
that the file never passes through a model. It left the delivery mechanism as a path: the operator
mounts a directory, sets `IMPORT_ROOT`, and names a file inside it. That works on a laptop and
fails everywhere else.

**It is not a deployment shape.** A container on the one maintained cloud target has no host
directory to mount, and the substitutes are provider-coupled in a way [ADR-0004](0004-portability-as-a-build-gate.md)
forbids at module scope. **It is also not usable.** The operator is a person with a zip in their
downloads folder, and the instruction "place this file in a directory the server can see, then tell
me its path" is not an onboarding step anybody completes. `PLT-02` puts the runtime in the
organisation's hands; it does not require the organisation to operate a file share.

The replacement is an upload. That changes three things at once, and they cannot be decided
separately.

**The archive becomes untrusted input.** Today `IMPORT_ROOT` names a directory only the operator can
write to, so the reader's inputs are the operator's own files. An upload endpoint means anyone who
can reach it chooses the bytes. That is a trust boundary moving, and every bound the reader lacks
becomes reachable the day the endpoint ships.

**The work outlives a tool call.** Measured against the local stack: 10.2 ms per transaction through
the ordinary service path, of which 4.4 ms — 43% — is connection setup, entity scoping and the
advisory lock, because `entity_write` opens a connection per call. A real export of 5,553
transactions takes about 57 seconds locally, and materially longer against a managed database where
a connection costs a TLS handshake rather than a socket. That is not long for a batch job. It is far
too long for an MCP tool call: the client gives up, and the operator is left not knowing whether a
company's books were half-written.

**The same shape arrives again.** Bank feed ingestion is fetch, normalise, propose, confirm, post —
another ordered sequence over one artifact with one outcome. Deciding the shape once, now, is
cheaper than deciding it twice.

## Decision Drivers

* `NFR-04` requires one tenant's activity not to degrade another's. A process that decompresses an
  untrusted archive into memory serves every other entity's tools from the same process.
* `IMP-05` requires the operator to see what will be created and what will not, and to be able to
  abandon it. A job the operator cannot observe mid-flight cannot satisfy that at import scale.
* `IMP-03` requires an import that fails partway to leave the books in a state the operator can
  reason about, and `SOC1-14` requires the lineage to survive.
* [ADR-0003](0003-postgres-as-sole-storage-backend.md) makes Postgres the only storage backend,
  and [ADR-0023](0023-one-image-many-entrypoints.md) ships one image with many entrypoints. Both
  point at the same answer and neither has to be bent to reach it.
* [ADR-0029](0029-mandatory-idempotency-keys.md) already makes a repeated import a replay. A
  retryable worker is only safe because that landed first.

## Considered Options

* A staged job in Postgres, advanced by a worker entrypoint
* An event bus, with each stage a subscriber
* A provider queue — Cloud Tasks or Pub/Sub — with a local fallback
* A synchronous tool call that holds the connection until the import finishes
* Keeping the mounted directory and documenting it as the supported shape

## Decision Outcome

Chosen option: "A staged job in Postgres, advanced by a worker entrypoint".

### 1. The archive arrives by upload, and the mounted path is a development affordance

An endpoint accepts the bytes and returns a job id. The skill reads the file from disk and sends
it; the model never holds the contents, which is ADR-0040's rule unchanged — it was never about the
transport, it was about the context window.

`IMPORT_ROOT` stays for local development, where naming a path beats operating an upload. It is
**not a deployment shape** and the deployment contract does not describe one. A record that keeps a
convenience alive without saying which it is produces two supported paths by accident.

### 2. Where the bytes rest is a protocol with a local default

`ADR-0004` requires provider-specific code behind a protocol with a local default requiring no
cloud account. The default writes to a directory; an object store sits behind the same protocol.
This is not future-proofing — it is the condition under which the cloud target may be used at all,
and the local default is the one the tests run against.

### 3. The stages are rows, and the pipeline is not a bus

An import is a row with a stage, advanced by a worker: **received → scanned → read → planned →
posted → reconciled**, with a terminal `refused` carrying the reason. Claimed with
`SELECT … FOR UPDATE SKIP LOCKED`, which is a work queue with no new dependency, on the backend
`ADR-0003` already makes the only one.

**This is deliberately not an event bus, and the distinction is the decision.** A bus is
publish/subscribe: many producers, consumers the producer does not know, fan-out, decoupling in time
and identity. What an import needs is a fixed sequence over one artifact with one outcome. Nothing
subscribes and nothing fans out, so a bus would buy indirection and charge for it in the one place
this domain cannot afford it — *where is my import, and what happened to it* has to be answerable
exactly, months later, to somebody's auditor. A stage column answers that with a query. A bus
answers it by reading logs across consumers and inferring.

[ADR-0012](0012-binding-non-goals-and-scope-discipline.md) gates an event bus behind a record rather than forbidding one.
This is that record, and the answer is no — for now, and for a stated reason rather than by
default.

**What would change it:** a consumer CFOKit does not know about needing to react to its events.
That is `NFR-12`'s extension point, which does not exist, and drawing the boundary before it does is
the mistake the deleted `connectors` package already made once ([ADR-0031](0031-packages-named-for-capabilities.md)).
A provider queue is a *second implementation behind the protocol in § 2*, not a replacement for it —
`ADR-0004` requires the local default regardless, so the Postgres one is built either way and the
cheap order is to build it first.

### 4. Scanning is a stage, because the trust boundary moved

An uploaded archive is bounded before it is read: total size, expanded size, member count, and a
bounded read per member because the central directory is written by whoever made the file. The
bounds live in the reader rather than at an adapter — every path onto the books goes through
`quickbooks.read`, and a ceiling at one adapter is a ceiling the next one does not have.

The numbers come from a real export rather than a guess: eight members, 979,403 bytes expanded from
904,749, a ratio of 1.08. That ratio is structural — the members are `.xlsx` files, which are
themselves zips — so a genuine export is very nearly incompressible and a high ratio is evidence the
file is not one.

### 5. Batching is the write-path consequence, and is not decided here

43% of per-transaction cost is connection setup and lock acquisition, paid 5,553 times. Sharing one
`EntityWrite` across a run of entries would remove most of it, and collides with ADR-0040's reason
for one transaction per entry: a single enormous transaction means an eleven-thousand-line rollback
over one malformed row. Chunking bounds both. **It touches the write path and needs its own record
and human review**; it is named here so the measurement is not lost.

### Consequences

* Good, because the operator uploads a file, which is the interaction they already expect, and gets
  a job id they can ask about — which is `IMP-05`'s "sees what will be created" at a scale where a
  synchronous answer was never going to arrive.
* Good, because a stage is a row, so a failed import says where it stopped rather than requiring the
  logs to be reconstructed.
* Good, because retry is safe without new work: `ADR-0029`'s derived keys already make a second run
  a replay.
* Good, because nothing new is deployed. The worker is an entrypoint of the image that already
  ships, and the queue is a table in the database that already exists.
* Bad, because polling a table is not free, and a worker that is idle most of the time still holds a
  connection to ask. At one import per company per migration this is not the constraint; at bank-feed
  cadence it may become one, and that is when the provider queue question is worth reopening.
* Bad, because an upload endpoint is a new surface with a new abuse profile — size, rate, and
  storage cost — where a mounted directory had none of those because only the operator could write
  to it.
* Bad, because two delivery paths exist during the transition, and the mounted one is the one with
  the working end-to-end evidence behind it.

### Confirmation

The bounds are gated: `tests/test_archive_bounds.py` runs in the unit tier, refuses an archive past
each bound, and refuses a member whose declared size understates what it delivers. It also asserts
`openpyxl` is routing through `defusedxml`, because a dependency is only worth its place if it is
actually in the path and an environment variable can take it out of one silently.

The stage machine's confirmation is that an import interrupted at each stage resumes to the same
books — which is a property test over the stage transitions rather than a worked example, and it is
not written yet because the stages are not built yet.

**Not gated:** nothing prevents a second delivery path being added, or the mounted one being
described as supported. That is a review rule, and a weak one — see
[ADR-0036](0036-correctness-is-tested-in-four-layers.md) § 5 on why the ungated rules in a record
are a statement of what the gated ones are for.

## Pros and Cons of the Options

### A staged job in Postgres, advanced by a worker entrypoint

* Good, because the state is queryable, which is what an accounting system owes its operator.
* Good, because it adds no dependency, no broker and no second datastore.
* Good, because `SKIP LOCKED` gives concurrency and at-most-once claiming for free, and the database
  is already the serialisation point for a given entity (`ADR-0011`).
* Bad, because polling is a cost paid whether or not there is work.
* Bad, because retry, backoff and dead-lettering are ours to write rather than a broker's to supply.

### An event bus, with each stage a subscriber

* Good, because stages decouple, and a new stage is added without touching the ones around it.
* Good, because it is the shape most teams reach for, so it surprises nobody.
* Bad, because nothing here publishes to an unknown consumer, so the decoupling is paid for and
  unused.
* Bad, because it makes the operator's question — where did my import stop — an inference over
  consumer logs rather than a read.
* Bad, because ordering and delivery guarantees become the system's problem in exchange for
  flexibility this domain has no use for yet.

### A provider queue — Cloud Tasks or Pub/Sub — with a local fallback

* Good, because retry, backoff and dead-lettering are operated by someone else.
* Good, because it scales past anything a polled table will.
* Bad, because `ADR-0004` requires a local default needing no cloud account, so the Postgres
  implementation is built anyway and this is strictly additional.
* Bad, because it splits the job's state from the books, so a job that succeeded and a ledger write
  that did not are now two facts that can disagree.

### A synchronous tool call that holds the connection until the import finishes

* Good, because it is what exists, and the end-to-end evidence is behind it.
* Bad, because the measurement says a minute locally and longer in a managed environment, and MCP
  clients do not wait that long — the operator learns nothing about whether the books were written.
* Bad, because a client that retries a timed-out call is relying entirely on `ADR-0029` to avoid
  duplicating a company's history, with no way to observe which happened.

### Keeping the mounted directory and documenting it as the supported shape

* Good, because it is built, tested and demonstrated against a real company's books.
* Bad, because it has no analogue on the maintained cloud target that `ADR-0004` permits.
* Bad, because it asks a person with a zip in their downloads folder to operate a file share, which
  is not an onboarding step anybody completes.

## Revisit when

* A consumer CFOKit does not know about needs to react to its events, which is `NFR-12`'s extension
  point arriving and the only thing that makes a bus buy something.
* Bank feed ingestion lands, which puts many entities on a cadence rather than one company on a
  migration, and is where a polled table's cost stops being negligible.
* The measurement changes: batching the write path removes most of the 43%, and an import that
  finishes in seconds rather than a minute is one a synchronous call could carry after all.
