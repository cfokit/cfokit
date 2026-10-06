---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-06
decision-makers: [Geoff Scott]
---

# ADR-0061: Unattended work is a queue in Postgres, filled from stored schedules and drained by one job on a short tick

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
work — period-close checks, recurring invoices, scheduled reports — run daily or monthly. The
deployment is mostly idle by assumption: the API scales to zero
([ADR-0017](0017-gcp-initial-cloud-target.md)), and the hosted database is a `db-g1-small`.

Four existing records bound the answer. [ADR-0023](0023-one-image-many-entrypoints.md) allows two
runtime shapes, a request-serving service and a one-shot job, and rules out long-running workers. It
also treats a run schedule as infrastructure, which `BKP-16` and `PLT-14` contradict: a schedule the
entity controls is the entity's data. [ADR-0003](0003-postgres-as-sole-storage-backend.md) allows no
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
* Cost proportional to a mostly idle workload.
* Latency of minutes is acceptable: nothing waiting on this work is waiting on a person.

## Considered Options

* A work table in Postgres, filled from stored schedules and by causes, drained by a job on a short tick
* The same table, drained by an always-on worker
* A task-queue library on Postgres
* A managed queue: Cloud Tasks or Pub/Sub
* A Redis-backed queue: Celery or RQ
* One Cloud Scheduler job per schedule
* `pg_cron` in the database

## Decision Outcome

Chosen option: "A work table in Postgres, filled from stored schedules and by causes, drained by a
job on a short tick", because it is a real queue — durable, transactional with its cause, claimable
safely by more than one drainer — in the store the books already require, at the cost of a few
minutes' latency the workload does not notice.

> Unattended work is a row in Postgres, enqueued in the same commit as what caused it. Schedules are
> the entity's own rows, and a due window becomes a row. One entrypoint drains what is due, run by a
> fixed tick: Cloud Scheduler starting a Cloud Run job in the cloud, a compose service on by default
> locally.

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

Each drain enqueues a run for every window due since the last one enqueued. **Each kind declares how
missed windows are recovered.** An ingestion kind coalesces them into one run over the whole span,
because one sync catches up any gap. A kind whose windows are distinct — one recurring invoice per
month — enqueues one run per window. A missed window is never dropped.

### 3. One drain, started by a tick

`python -m cfokit.server work` claims due runs and runs each through the handler its kind names. It
lives in `server` because only the composition point knows the module list; the handlers live in
their modules.

* **Claim:** a short transaction selects due runs with `FOR UPDATE SKIP LOCKED`, marks them running
  under a lease, and commits. Two drains never take the same run; a crashed drain's lease expires
  and the run is due again.
* **Run:** each handler runs in its entity's scope — `cfokit.entity_id` set, row-level security in
  force — and takes the entity's lock for any ledger write, as every write does
  ([ADR-0011](0011-entity-advisory-lock.md)).
* **Exit:** when nothing is due, or a time budget inside the job's timeout is spent. Nothing runs
  between ticks.

The tick is infrastructure and fixed: Cloud Scheduler starts the Cloud Run job every five minutes.
Locally it is a compose service that runs the same entrypoint in a loop, **on by default**, because a
self-hosted deployment with a feed has to sync. What runs when is the schedules' business, not the
tick's: the tick only bounds the latency.

**On GCP the drain runs as its own service account, `cfokit-work`**, not the API's `cfokit-service`.
Unattended work holds permissions a request never needs — decrypting a feed's token
([ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) § 6) is the first — and a
separate identity is what lets them be granted to the drain alone. It holds the database secret and
what its kinds of work require, nothing more. Cloud Scheduler starts the job as an identity allowed
only to run it.

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
* Good, because a missed tick, a failed attempt and a crashed drain each leave work due rather than
  lost, which is `PLT-14`'s recoverability as a property of storage rather than of the code.
* Good, because one mechanism serves every kind of unattended work, on a laptop and in the cloud.
* Good, because it adds no store and no runtime dependency. The claim is a few lines of SQL Postgres
  has supported since 9.5.
* Bad, because work waits up to one tick — five minutes — before it starts. A person who has just
  connected a bank waits that long for the first sync to begin.
* Bad, because the tick costs money when nothing is due. Cloud Run bills a job instance for at least
  one minute, so a 1 vCPU, 512 MiB job started every five minutes is about $5 a month after the free
  tier, and the same job every minute is about $44 — as much as never stopping. Five minutes is the
  shortest tick that stays cheap.
* Bad, because the run table is read across entities, an exception to row-level security that has
  to stay content-free to stay harmless.
* Neutral, because [ADR-0023](0023-one-image-many-entrypoints.md)'s two runtime shapes stand. The
  drain is a job; there is still no long-running worker in the cloud.

### Confirmation

Integration tests drive the drain as a function against the compose database: a run enqueued in a
transaction that rolls back is never claimed; two concurrent drains never claim the same run; an
expired lease makes a run due again; a missed span coalesces for an ingestion kind and enumerates
for a windowed one; a suspended entity's runs are not claimed and its outbound runs are canceled; a
run that exhausts its retries raises a notification.

A schema test asserts that the run table has no column of a money type and no free-text column
beyond the kind's reference. Content creeping into the queue is the failure § 6 exists to prevent.

Not gated: that the deployed tick is running. `infra/gcp/setup/check.sh` is where that belongs, and
a run overdue by more than a few ticks is what a person would notice.

## Pros and Cons of the Options

### A work table in Postgres, filled from stored schedules and by causes, drained by a job on a short tick

* Good, because it is transactional with its cause, which no queue outside Postgres can be.
* Good, because it fits ADR-0023's job shape and scales to zero between ticks.
* Bad, because its latency is the tick's interval, and its idle cost is the tick's.

### The same table, drained by an always-on worker

The strongest alternative: same storage and semantics, with latency in seconds by polling or
`LISTEN`/`NOTIFY`.

* Good, because work starts almost immediately.
* Bad, because an instance that never scales to zero costs about $44 to $49 a month (1 vCPU, 512 MiB, instance-based billing, which background work
  needs because request-based billing throttles CPU outside a request) — against about $5 for the tick — to wait for
  work that arrives a few times a day per connection. The latency it buys is spent waiting for Plaid,
  which refreshes from the bank one to four times a day.
* Bad, because it is the long-running worker ADR-0023 excludes, and it would be the only one.

Reversible from the chosen option without touching the queue: the drain is the same function either
way.

### A task-queue library on Postgres

Procrastinate is the strongest of these: the same `SKIP LOCKED` design, with retries, scheduling and
a worker already written.

* Good, because it is written and tested by others.
* Bad, because it is a seventh runtime dependency (MIT, 3.10.0), and its worker requires an async
  connector: the synchronous psycopg 3 connector "may only be used for deferring jobs". Its worker is
  long-running by default, though `run_worker(wait=False)` exits once caught up and would fit a job.
  pgqueuer and Chancy (both MIT) are the same trade.
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
* Bad, because both need a long-running worker.

### One Cloud Scheduler job per schedule

* Good, because there is no tick, and scheduling is entirely the platform's.
* Bad, because the schedule then lives in infrastructure. An entity changing its cadence becomes an
  infrastructure write from the application, which is a provider SDK in the app (`NFR-10`), and the
  change is recorded in a cloud audit log rather than the books' (`PLT-15`).
* Bad, because it has no local equivalent, and it handles only timers, not work a webhook causes.

### `pg_cron` in the database

* Good, because it is a timer inside the store, with nothing else to run.
* Bad, because it runs SQL, not Python, and a feed sync is an HTTPS conversation with a provider.
  At most it could replace the tick. Cloud SQL supports it (1.6.4, behind the
  `cloudsql.enable_pg_cron` flag); a timer that can only run SQL cannot start a job that calls Plaid.

## More Information

**Follow-on obligations.**

* [ADR-0023](0023-one-image-many-entrypoints.md) is corrected in place: a run schedule is the
  entity's data, the tick is infrastructure, and the local tick runs by default. Its two runtime
  shapes and its exclusion of long-running workers stand.
* [ADR-0012](0012-binding-non-goals-and-scope-discipline.md)'s table of items that have passed the
  gate gains this record. A queue is not on the list, but an event bus is, and a queue is near enough
  to it that passing it unrecorded would be the drift the gate exists to catch.
* `infra/` gains the Cloud Scheduler trigger, the Cloud Run job for the drain, the `cfokit-work`
  service account it runs as, and the invoker identity Cloud Scheduler uses; and `compose.yaml`
  gains the drain service, outside any profile. `infra/README.md` states that any target must supply
  a fixed tick that starts a one-shot job.
* A kind of work declares its cadence bounds, its recovery of missed windows, whether it is ingestion
  or outbound, and its retry bound. A kind that leaves one undeclared does not register.
* A root `CLAUDE.md` rule: unattended work is enqueued as a run in the same transaction as its cause,
  and nothing runs on a timer of its own.

**Reversal cost.** Low for the drain: moving to an always-on worker, or to a different tick, changes
infrastructure and not the queue. Moderate for the queue: every kind of unattended work is enqueued
through it, and replacing it with an external queue gives up enqueueing in the cause's transaction,
which would have to be rebuilt as an outbox — this table under another name.

## Revisit when

* A kind of work needs to start within seconds of its cause, which the tick cannot give. That is the
  case for an always-on drain.
* The tick's idle cost becomes a visible share of the hosted bill, or the drain regularly exhausts
  its time budget with work still due.
* Claiming contends: drains waiting on one another, or the run table large enough that the due-work
  query is no longer cheap.
* Plaid stops requiring webhooks, or a feed provider pushes data rather than announcing it.
