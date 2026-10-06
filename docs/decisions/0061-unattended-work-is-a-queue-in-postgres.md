---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-06
decision-makers: [Geoff Scott]
---

# ADR-0061: Unattended work is a queue in Postgres, filled from stored schedules and drained by an always-running worker

**Requirements served:** `PLT-14`, `BKP-16`, `PLT-07`, `PLT-10`, `PLT-12`, `PLT-18`, `SOC2-15`.

## Context and Problem Statement

Everything CFOKit does today happens inside a request someone made. Several requirements need work
that no request starts:

* `BKP-16`: feeds synchronize "on a schedule the entity controls, with no person triggering them".
* `PLT-14`: scheduled work "runs on a timer the entity controls. A missed window is recoverable
  rather than skipped in silence, and every run is attributable in the same way a person's action is."
* `PLT-07`: a scheduled run that did not complete reaches the people who operate the entity.
* `PLT-10` and `PLT-12`: suspension halts every scheduled job and cancels outbound work in flight;
  on resume, ingestion backfills the suspended period and canceled outbound work is not replayed.
* `PLT-18`: an examiner is shown "what the system did unattended" over a period.

Some of this work is not on a timer at all. A bank feed provider announces new data by webhook, and
the provider for the hosted offering, Plaid, makes webhooks its primary signal: its launch
checklist requires them for Transactions, and its webhook guide still calls for "polling or
recovery logic since webhooks exceeding the 24-hour retry window are lost". The webhook cannot do
the work itself. Plaid retries any delivery not answered within 10 seconds, and a first sync can
return up to 24 months of history across many pages. So a webhook leaves work to be done shortly,
by something else.

The workload is small and bursty. A feed is synchronized a few times a day per connection, because
Plaid itself refreshes from an institution "one to four times per day". Other kinds of scheduled
work — period-close checks, recurring invoices, scheduled reports — run daily or monthly. The API
scales to zero ([ADR-0017](0017-gcp-initial-cloud-target.md)), so nothing in the deployment is
running when no one is using it.

This is production work, part of the application, and it changes with the application's code.
Whatever runs it has to be deployed as the application is — the same image, in the same step — or a
handler can run last week's code against this week's schema. A trigger that lives in infrastructure
is a second thing to deploy and a second place for that skew to hide.

Four existing records bound the answer. [ADR-0023](0023-one-image-many-entrypoints.md) allowed two
runtime shapes, a request-serving service and a one-shot job, and ruled out long-running workers. It
also treated a run schedule as infrastructure, which `BKP-16` and `PLT-14` contradict: a schedule
the entity controls is the entity's data. [ADR-0003](0003-postgres-as-sole-storage-backend.md) allows no
second store. [ADR-0012](0012-binding-non-goals-and-scope-discipline.md) gates an event bus. And
`NFR-11` and `NFR-17` require every capability, scheduled work included, to run on one machine with
no cloud account.

## Decision Drivers

* A schedule is the entity's to set and change, with each change recorded (`PLT-15`).
* Work that is due survives a crash, a failed attempt, or a missed timer, and is recovered rather
  than lost (`PLT-14`).
* Work is enqueued in the same commit as whatever caused it, or not at all — a webhook acknowledged
  with nothing recorded is a lost sync.
* Every run is attributable, and the record of runs is the examiner's evidence (`PLT-18`).
* Suspension stops work without losing ingestion (`PLT-10`, `PLT-12`).
* The same mechanism on a laptop and in the cloud (`NFR-11`, `NFR-17`).
* No second store (ADR-0003), and no runtime dependency without a reason (root `CLAUDE.md`).
* Unattended work deploys as the application does — same image, same step — with no
  infrastructure that knows when work runs.
* Its cost is stated and bounded. Tens of dollars a month is acceptable for a capability every
  entity depends on; a design that bends the application around saving them is not.

## Considered Options

* A work table in Postgres, filled from stored schedules and by causes, drained by an always-running worker
* The same table, drained by a job on a fixed tick
* The same table, drained by a thread in the API's process
* A task-queue library on Postgres
* A managed queue: Cloud Tasks or Pub/Sub
* A Redis-backed queue: Celery or RQ
* One Cloud Scheduler job per schedule
* `pg_cron` in the database

## Decision Outcome

Chosen option: "A work table in Postgres, filled from stored schedules and by causes, drained by an
always-running worker", because it is a real queue — durable, transactional with its cause, claimable
safely by more than one worker — in the store the books already require, drained by a process that
is deployed exactly as the API is.

> Unattended work is a row in Postgres, enqueued in the same commit as what caused it. Schedules are
> the entity's own rows, and a due window becomes a row. One always-running worker, from the same
> image and rolled out in the same step as the API, claims and runs what is due. No timer exists
> outside it.

This is a queue, and this record is what [ADR-0012](0012-binding-non-goals-and-scope-discipline.md)'s
gate asks of one. It is not an event bus: a row names one piece of work for one handler, and nothing
subscribes to it. The ledger remains the only account of what happened.

### 1. A run is a row, enqueued with its cause

A run names its entity, its kind, an opaque reference the kind's handler understands (a feed
connection, a schedule), the window it covers, and when it becomes due. It is inserted in the same
transaction as what caused it: a verified webhook, a person's request, or a schedule's window
falling due. A cause that commits has enqueued its work; one that rolls back has not.

**At most one open run per entity, kind and reference.** A second cause while one is waiting joins
it rather than adding another. Plaid sends duplicate and out-of-order webhooks and asks for
idempotent handling; this is where that is satisfied.

### 2. A schedule is the entity's row, and a missed window is coalesced, never skipped

A schedule is a cadence for one kind of work, in the entity's time zone (`PLT-08`), within bounds the
kind declares — a feed may run every few hours, never every few seconds. It is a chain of versions,
appended and never edited, so the cadence in force at any moment is recoverable and every change
names who made it (`PLT-15`), the shape [ADR-0045](0045-assignment-is-stored-rules.md) § 2 gives a
rule.

Each pass of the worker's loop enqueues a run for every window due since the last one enqueued. **Each kind declares how
missed windows are recovered.** An ingestion kind coalesces them into one run over the whole span,
because one sync catches up any gap. A kind whose windows are distinct — one recurring invoice per
month — enqueues one run per window. A missed window is never dropped.

### 3. One worker, always running, deployed as the application is

`python -m cfokit.server work` is a long-running process. It lives in `server` because only the
composition point knows the module list; the handlers live in their modules. It loops:

* **Enqueue** a run for every schedule window that has come due (§ 2).
* **Claim:** a short transaction selects due runs with `FOR UPDATE SKIP LOCKED`, marks them running
  under a lease, and commits. Two workers never take the same run; a run whose worker died is due
  again when its lease expires.
* **Run:** each handler runs in its entity's scope — `cfokit.entity_id` set, row-level security in
  force — and takes the entity's lock for any ledger write, as every write does
  ([ADR-0011](0011-entity-advisory-lock.md)).
* **Wait** a few seconds when nothing was due, then loop.

Its loop is the only timer. What runs when is the schedules' business, held in the database, so a
schedule changes without a deploy and the worker changes only when the code does.

**On a stop signal it claims nothing more**, finishes what it holds if it can, and exits. A run cut
off mid-way is due again when its lease expires and runs again from the start, which is safe because
every write it makes is idempotent by key ([ADR-0029](0029-mandatory-idempotency-keys.md)). Cloud Run
allows ten seconds between the signal and the kill.

**On GCP it is a Cloud Run worker pool, `cfokit-work`, of one instance.** A worker pool is Cloud Run's
resource for a process that serves no requests: no URL, no port to listen on. It is rolled out in the
same step that updates `cfokit-rest` and `cfokit-mcp` to the merged commit's image. **Locally it is a
compose service running the same command, on by default**, because a self-hosted deployment with a
feed has to sync. More than one instance is safe, and one is the configuration.

**It runs as its own service account, `cfokit-work`**, not the API's `cfokit-service`. Unattended
work holds permissions a request never needs — decrypting a feed's token
([ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) § 6) is the first — and a separate
identity is what lets them be granted to the worker alone. It holds the database secret and what its
kinds of work require, nothing more.

### 4. Every run is recorded, and a failure reaches a person

Each attempt is appended with its outcome. A run's cause is on the run — the schedule version, the
webhook delivery, or the request id — and every `audit_log` row a handler writes carries the run's
id as its request id, so a change made unattended traces to the schedule, and the schedule to the
person who set it. That record, over a period, is `PLT-18`'s "what the system did unattended".

A failed attempt is retried with backoff up to a bound the kind declares. A run that exhausts it is
failed, and a notification is raised (`PLT-07`, [ADR-0052](0052-notifications-are-records-delivered-after-commit.md)).
Nothing fails silently.

### 5. Suspension stops claiming; each kind says what resumes

The claim takes runs only for active entities, and schedules enqueue nothing for a suspended one.
**Each kind declares whether it is ingestion or outbound.** On suspension, open outbound runs are
canceled and recorded as canceled (`PLT-10`). Ingestion runs wait. On resume, the coalesced window
spans the suspension, so the books carry no gap (`PLT-12`), and nothing canceled is replayed.

### 6. The queue holds routing, never content

Claiming reads due runs across entities, so the run table is read without an entity scope.
`SOC2-15` makes a cross-entity read of an entity's data impossible, and the run table holds none: an
entity's id, a kind, an opaque reference, times and states — what the `entity` table already says
to every process about which entities exist. Never an amount, a payee, an account number, or a
credential. Everything a handler reads or writes is under row-level security for the entity it
claimed, so what the claim learns is only that an entity has work due.

### Consequences

* Good, because work commits with its cause, so an acknowledged webhook always has a run behind it.
* Good, because a failed attempt, a dead worker and a deploy mid-run each leave work due rather than
  lost, which is `PLT-14`'s recoverability as a property of storage rather than of the code.
* Good, because one mechanism serves every kind of unattended work, on a laptop and in the cloud.
* Good, because it adds no store and no runtime dependency. The claim is a few lines of SQL Postgres
  has supported since 9.5.
* Good, because it deploys as the application does. Nothing in infrastructure knows a schedule, and
  there is no second artifact to fall behind the code.
* Good, because work starts within seconds of its cause. A person who has just connected a bank sees
  the first sync begin at once.
* Bad, because one instance runs all month whether or not anything is due: about $25 a month at
  1 vCPU and 512 MiB by the worker pool rates Google publishes for us-central1, after the free tier.
* Bad, because a run can be cut off by a deploy, ten seconds after the signal. Every handler must
  tolerate running again from the start, which idempotency keys give writes but a handler must not
  undo with a side effect of its own.
* Bad, because the run table is read across entities, an exception to row-level security that has
  to stay content-free to stay harmless.
* Neutral, because [ADR-0023](0023-one-image-many-entrypoints.md) gains a third runtime shape, the
  worker, beside the service and the job.

### Confirmation

Integration tests drive one pass of the worker's loop as a function against the compose database: a
run enqueued in a transaction that rolls back is never claimed; two concurrent workers never claim
the same run; an expired lease makes a run due again; a stop signal claims nothing more; a missed span coalesces for an ingestion kind and enumerates
for a windowed one; a suspended entity's runs are not claimed and its outbound runs are canceled; a
run that exhausts its retries raises a notification.

A schema test asserts that the run table has no column of a money type and no free-text column
beyond the kind's reference. Content creeping into the queue is the failure § 6 exists to prevent.

`infra/gcp/setup/check.sh` asserts that the worker pool runs the image the API runs.

Not gated: that the worker is alive between deploys. A run overdue by more than a few minutes is the
symptom, and watching for it is monitoring's, not CI's.

## Pros and Cons of the Options

### A work table in Postgres, filled from stored schedules and by causes, drained by an always-running worker

* Good, because it is transactional with its cause, which no queue outside Postgres can be.
* Good, because it is one more name in the rollout the API already has.
* Bad, because it is paid for while idle.

### The same table, drained by a job on a fixed tick

The cheapest way to run the same drain: Cloud Scheduler starts a Cloud Run job every five minutes,
which drains what is due and exits.

* Good, because it scales to zero between ticks, at about $5 a month against the worker's $25.
* Bad, because the trigger lives in infrastructure: a Cloud Scheduler job, a job resource, an
  invoker identity allowed to start it, and a deploy step whose only purpose is to keep the job's
  image current. Forget that step and the job runs stale code with nothing failing loudly — the skew
  ADR-0023 exists to prevent.
* Bad, because work waits up to a tick, and a tick cannot be shortened cheaply. Cloud Run bills a job
  instance for at least a minute, so a one-minute tick costs about $44 a month, more than the worker.
* Bad, because executions overlap when a drain outlasts the tick, so the drain needs a time budget
  and the tick a margin, both tuned against each other.

### The same table, drained by a thread in the API's process

* Good, because there is nothing new to deploy at all.
* Bad, because the API scales to zero, so the drain would stop whenever no one is using CFOKit —
  which is when unattended work most needs to happen. Keeping one instance always on costs about
  $44 a month as a service, more than a worker pool.
* Bad, because every API instance would run a drain, and the permissions unattended work needs —
  opening a feed's token first — would be granted to the process that faces the internet.

### A task-queue library on Postgres

Procrastinate is the strongest of these: the same `SKIP LOCKED` design, with retries, scheduling and
a worker already written.

* Good, because it is written and tested by others.
* Bad, because it is a seventh runtime dependency (MIT, 3.10.0), and its worker requires an async
  connector: the synchronous psycopg 3 connector "may only be used for deferring jobs". pgqueuer and
  Chancy (both MIT) are the same trade.
* Bad, because the parts this record needs most — schedules the entity controls and versions,
  per-kind recovery of missed windows, suspension semantics, runs attributable through `audit_log` —
  are ours to write either way. What the library supplies is the claim, which is the part that is a
  few lines of SQL.
* Bad, because its tables would be the one schema in the database not written by hand
  ([ADR-0028](0028-hand-written-sql-no-orm.md)).

### A managed queue: Cloud Tasks or Pub/Sub

* Good, because delivery is pushed, so latency is seconds and nothing ticks.
* Bad, because the work is then a second store outside Postgres (ADR-0003), and enqueueing cannot be
  in the same transaction as its cause. A webhook acknowledged after the commit and before the
  publish loses its sync, which is the failure this record exists to prevent.
* Bad, because it is a GCP API in the request path, with only Pub/Sub offering an official emulator —
  Cloud Tasks has community ones — for the local deployment `NFR-11` requires. A self-hosted
  deployment would run an emulator in production, or a second implementation of the queue.

### A Redis-backed queue: Celery or RQ

* Good, because they are the conventional Python answer, with mature tooling.
* Bad, because Redis is a second store (ADR-0003) and a second service to operate and secure, and
  the queue still cannot commit with its cause.
* Bad, because their workers are built around their brokers, so the worker this record needs anyway
  would be theirs rather than ours, with their retry semantics instead of § 4's.

### One Cloud Scheduler job per schedule

* Good, because there is no worker, and scheduling is entirely the platform's.
* Bad, because the schedule then lives in infrastructure. An entity changing its cadence becomes an
  infrastructure write from the application, which is a provider SDK in the app (`NFR-10`), and the
  change is recorded in a cloud audit log rather than the books' (`PLT-15`).
* Bad, because it has no local equivalent, and it handles only timers, not work a webhook causes.

### `pg_cron` in the database

* Good, because it is a timer inside the store, with nothing else to run.
* Bad, because it runs SQL, not Python, and a feed sync is an HTTPS conversation with a provider.
  Cloud SQL supports it (1.6.4, behind the `cloudsql.enable_pg_cron` flag), but a timer that can
  only run SQL cannot call Plaid, so a process to do the work is needed regardless.

## More Information

**Follow-on obligations.**

* [ADR-0023](0023-one-image-many-entrypoints.md) is corrected in place: a third runtime shape, the
  worker, beside the service and the job; a run schedule is the entity's data.
* [ADR-0012](0012-binding-non-goals-and-scope-discipline.md)'s table of items that have passed the
  gate gains this record. A queue is not on the list, but an event bus is, and a queue is near enough
  to it that passing it unrecorded would be the drift the gate exists to catch.
* `infra/gcp/` gains the `cfokit-work` worker pool (`google_cloud_run_v2_worker_pool`, in the
  provider since 6.37.0) and the `cfokit-work` service account. `infra/gcp/setup/deploy.sh` updates
  the worker pool's image in the same rollout step as `cfokit-rest` and `cfokit-mcp`.
* `compose.yaml` gains the worker as a service outside any profile.
* `infra/README.md` states that any target must supply a runtime for one always-running process
  with no ingress.
* A kind of work declares its cadence bounds, its recovery of missed windows, whether it is ingestion
  or outbound, and its retry bound. A kind that leaves one undeclared does not register.
* A root `CLAUDE.md` rule: unattended work is enqueued as a run in the same transaction as its cause,
  and nothing runs on a timer of its own.
* Worker pool pricing is from Google's published rate table. The pricing page's own worked example
  comes out lower than the table, and the two were not reconciled, so the $25 is an upper estimate.
  How a worker pool replaces instances on a new revision is not documented for worker pools; the ten
  seconds are Cloud Run's general container contract.

**Reversal cost.** Low for the worker: the loop's body is the same function a ticked job would run,
so moving to a job changes infrastructure and not the queue. Moderate for the queue: every kind of unattended work is enqueued
through it, and replacing it with an external queue gives up enqueueing in the cause's transaction,
which would have to be rebuilt as an outbox — this table under another name.

## Revisit when

* A kind of work needs to start faster than the worker's wait between polls, which is the case for
  waking it with `LISTEN`/`NOTIFY`.
* One worker cannot keep up: runs waiting behind others long enough that the queue's lag is visible.
  More instances are the first answer, and they are already safe.
* Claiming contends: workers waiting on one another, or the run table large enough that the
  due-work query is no longer cheap.
* A second cloud target is added that offers no always-running runtime without ingress.
* Plaid stops requiring webhooks, or a feed provider pushes data rather than announcing it.
