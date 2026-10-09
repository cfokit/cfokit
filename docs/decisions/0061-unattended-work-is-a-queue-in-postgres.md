---
status: "accepted"
kind: "requirement-driven"
date: 2026-10-06
decision-makers: [Geoff Scott]
---

# ADR-0061: Unattended work is a queue in Postgres, filled from stored schedules and drained a pass at a time, on a tick and when a person waits

**Requirements served:** `PLT-14`, `BKP-16`, `PLT-07`, `PLT-10`, `PLT-12`, `PLT-18`, `SOC2-15`.

## Context and Problem Statement

Everything CFOKit does today happens inside a request someone made. Several requirements need work
that no request starts:

* `BKP-16`: feeds synchronize with no person triggering them, when the source reports new activity
  and in any case within an interval the deployment sets.
* `PLT-14`: scheduled work runs on a timer — the entity's where its timing is a business decision,
  such as when an invoice recurs, and the deployment's where it is operational, such as how often a
  feed is checked. "A missed window is recoverable rather than skipped in silence, and every run is
  attributable in the same way a person's action is."
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

Almost none of it has a person waiting. A sync announced by webhook brings data the provider fetched
from the bank hours before, so minutes more are invisible, and a recurring invoice or a period-close
check has a day to run in. The exceptions are a person's own requests: connecting an account, whose
first sync brings the history they are waiting to see; asking for a sync now; repairing a broken
connection. Each is a person on a page, waiting for work the request itself cannot do.

This is production work, part of the application, and it changes with the application's code.
Whatever runs it has to be deployed as the application is — the same image, in the same step — or a
handler can run last week's code against this week's schema.

Four existing records bound the answer. [ADR-0023](0023-one-image-many-entrypoints.md) builds every
entrypoint from one image so none runs a different version from the API, and names the runtime
shapes a deployment must provide; whatever runs unattended work is one of them. Under `PLT-14`, when
an entity's invoice recurs is the entity's data, not infrastructure, so no schedule may need a
deploy to change. [ADR-0003](0003-postgres-as-sole-storage-backend.md) allows no
second store. [ADR-0012](0012-binding-non-goals-and-scope-discipline.md) gates an event bus. And
`NFR-11` and `NFR-17` require every capability, scheduled work included, to run on one machine with
no cloud account.

## Decision Drivers

* A business schedule is the entity's to set and change, with each change recorded (`PLT-15`). An
  operational interval is the deployment's, and is never asked of a customer.
* Many entities' work never falls due at the same instant, and no entity's backlog holds up
  another's.
* Unattended work stays inside the limits of the services it calls.
* Work that is due survives a crash, a failed attempt, or a missed timer, and is recovered rather
  than lost (`PLT-14`).
* Work is enqueued in the same commit as whatever caused it, or not at all — a webhook acknowledged
  with nothing recorded is a lost sync.
* Every run is attributable, and the record of runs is the examiner's evidence (`PLT-18`).
* Suspension stops work without losing ingestion (`PLT-10`, `PLT-12`).
* The same mechanism on a laptop and in the cloud (`NFR-11`, `NFR-17`).
* No second store (ADR-0003), and no runtime dependency without a reason (root `CLAUDE.md`).
* Unattended work deploys as the application does — same image, same step — and nothing outside the
  database knows a schedule.
* A person waiting on work sees it start within seconds. Work no one is waiting on may wait minutes.
* Its cost is stated, bounded, and in proportion to the work while there is little of it. Tens of
  dollars a month is acceptable for a capability every entity depends on; paying them for a process
  that is idle almost all month is not, and a design that bends the application around saving them
  is not either.

## Considered Options

* A work table in Postgres, filled from stored schedules and by causes, drained a pass at a time by
  a job on a fixed tick and started early when a person is waiting
* The same table, drained by an always-running worker
* The same table, drained by a job on a fixed tick alone
* The same table, drained by a thread in the API's process
* A task-queue library on Postgres
* A managed queue: Cloud Tasks or Pub/Sub
* A Redis-backed queue: Celery or RQ
* One Cloud Scheduler job per schedule
* `pg_cron` in the database

## Decision Outcome

Chosen option: "A work table in Postgres, filled from stored schedules and by causes, drained a pass
at a time by a job on a fixed tick and started early when a person is waiting", because it is a real
queue — durable, transactional with its cause, claimable safely by any number of passes at once — in
the store the books already require, drained by code deployed exactly as the API is, and paid for
only while it runs.

> Unattended work is a row in Postgres, enqueued in the same commit as what caused it. Schedules are
> the entity's own rows, and a due window becomes a row. A pass, from the same image and rolled out
> in the same step as the API, claims and runs what is due, and exits. A tick starts a pass every
> fifteen minutes, and a person's request that leaves work they are waiting on starts one at once.
> The tick knows no schedule: what is due is the database's to say.

This is a queue, and this record is what [ADR-0012](0012-binding-non-goals-and-scope-discipline.md)'s
gate asks of one. It is not an event bus: a row names one piece of work for one handler, and nothing
subscribes to it. The ledger remains the only account of what happened.

### 1. A run is a row, enqueued with its cause

A run names its entity, its kind, an opaque reference the kind's handler understands (a feed
connection, a schedule), the window it covers, and when it becomes due. It is inserted in the same
transaction as what caused it: a verified webhook, a person's request, or a schedule's window
falling due. A cause that commits has enqueued its work; one that rolls back has not.

**At most one waiting run per entity, kind and reference, and at most one running.** A cause
arriving while a run waits joins it rather than adding another; Plaid sends duplicate and
out-of-order webhooks and asks for idempotent handling, and this is where that is satisfied. A cause
arriving while a run is already running enqueues a new waiting run, because what it announces may
have arrived after the running one read its source. The waiting run is not claimed until the
running one finishes, so a connection is never synchronized by two runs at once.

### 2. A schedule is the entity's where its timing is a business decision, and a missed window is never skipped

**Each kind declares whose its timing is.**

* **A business kind** — a recurring invoice, a scheduled report — has a schedule the entity sets: a
  cadence in the entity's time zone (`PLT-08`), within bounds the kind declares. It is a chain of
  versions, appended and never edited, so the cadence in force at any moment is recoverable and every
  change names who made it (`PLT-15`), the shape [ADR-0045](0045-assignment-is-stored-rules.md) § 2
  gives a rule.
* **An operational kind** — a feed's backstop sync — has an interval the deployment sets, in its
  environment (ADR-0004), with a default the kind declares. It is never shown to a customer as a
  setting. Each reference's windows are offset within the interval by a hash of its id, so a
  deployment's connections fall due spread across the interval, never all at the top of the hour.
  **An operational window is a backstop**: it enqueues a run only if its reference has had no
  successful run within the interval. Work its cause already did — a feed synchronized on a
  webhook an hour ago — is not done again because a timer came round.

Each pass of the worker's loop enqueues a run for every window due since the last one enqueued.
**Each kind declares how missed windows are recovered.** An ingestion kind coalesces them into one
run over the whole span, because one sync catches up any gap. A kind whose windows are distinct —
one recurring invoice per month — enqueues one run per window. A missed window is never dropped.

### 3. A pass, run on a tick and when a person waits, deployed as the application is

`python -m cfokit.server work` runs passes. It lives in `server` because only the composition point
knows the module list; the handlers live in their modules. A pass:

* **Enqueue** a run for every schedule window that has come due (§ 2).
* **Claim:** a short transaction selects due runs with `FOR UPDATE SKIP LOCKED`, marks them running
  under a lease, and commits. Two workers never take the same run; a run whose worker died is due
  again when its lease expires. The claim takes the oldest due run of each entity in turn, never a
  second run of an entity that has one running, so one entity's backlog — a first sync of two
  years' history — delays only that entity.
* **Throttle:** a kind that calls an outside service declares that service's limit, and the worker
  starts no more of its runs than the limit allows. Plaid's is 2,500 `/transactions/sync` calls a
  minute per client. With more than one instance, each takes an equal share.
* **Run:** each handler runs in its entity's scope — `cfokit.entity_id` set, row-level security in
  force — and takes the entity's lock for any ledger write, as every write does
  ([ADR-0011](0011-entity-advisory-lock.md)).
* **Repeat** until nothing is due or the pass has run for its budget, ten minutes by default, then
  claim nothing more, finish what it holds, and exit.

A pass runs several runs at once, in threads, up to a bound it is configured with. Handlers are
synchronous code holding a transaction, as ADR-0024 requires inside the ledger. **Two passes at once
are safe**, because the claim is the only way to a run and two claims never take the same one; the
budget bounds a pass's cost, not its correctness.

**What runs when is the schedules' business, held in the database**, so a schedule changes without a
deploy and the pass changes only when the code does. The tick that starts a pass knows nothing of
schedules: a pass enqueues every window that has come due since the last one enqueued (§ 2), so a
tick late or missed delays work and never loses it.

**On a stop signal a pass claims nothing more**, finishes what it holds if it can, and exits. A run
cut off mid-way is due again when its lease expires and runs again from the start, which is safe
because every write it makes is idempotent by key ([ADR-0029](0029-mandatory-idempotency-keys.md)).

**On GCP a pass is a Cloud Run job, `cfokit-work`, running `work --once`.** Cloud Scheduler starts it
every fifteen minutes. Its image is updated in the same step that updates `cfokit-rest` and
`cfokit-mcp` to the merged commit's image, as the migration job's already is. **Locally it is a
compose service running `work`, on by default, which starts a pass a few seconds after the last
ends**, because a self-hosted deployment with a feed has to sync, and a laptop has no tick to start
one.

**A person's request that leaves work they are waiting on starts a pass at once**: connecting an
account, asking for a sync now, repairing a connection. The request enqueues its run in its own
transaction, as every cause does (§ 1), and after the commit the API starts `cfokit-work`, without
waiting for it to finish or knowing what it will claim. The wake is a convenience, never the only way
a run gets claimed: if it fails, the run is due, and the next tick takes it. A webhook does not wake a
pass. What it announces is hours old already, and no one is waiting on it.

Starting the job is the API's one permission over it: `roles/run.jobsExecutor` on `cfokit-work`
alone, which runs the job as it is deployed and cancels its executions, and cannot change its image,
command, arguments or environment (`run.jobs.runWithOverrides` is a separate permission, not
granted). What a pass does is decided by the queue, so a caller who can start one can make it run
sooner, never differently. The call is Cloud Run's Admin API over HTTPS with the standard library,
behind a protocol whose local default does nothing, because the local pass is never stopped;
authenticated by the service account's token from the metadata server, which is the process's
identity, as [ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) § 6 has it; and named
by `WORK_JOB`, so the job's name is configuration in the environment (ADR-0004). **With `WORK_JOB` unset the
wake does nothing and reaches for no credential**, which is the local stack's configuration and any
deployment's that runs the worker continuously: there a committed run is claimed by the next pass
within seconds. Where it is set and the call fails — a missing metadata server, a refused permission
— the failure is logged and the request's outcome is unchanged.

**A pass runs as its own service account, `cfokit-work`**, not the API's `cfokit-service`.
Unattended work holds permissions a request never needs — decrypting a feed's token
([ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) § 6) is the first — and a separate
identity is what lets them be granted to the pass alone. It holds the database secret and what its
kinds of work require, nothing more. Starting the job does not lend the API any of them.

**An always-running worker is the same code, looping.** When the queue is rarely empty at a tick, or
people wait on the wake often enough that its start time shows, `cfokit-work` becomes a Cloud Run
worker pool of one instance running `work`, as the local service does, and the tick and the wake are
removed. That changes infrastructure and nothing in the queue.

### 4. Every run is recorded, and a failure reaches a person

Each attempt is appended with its outcome. A run's cause is on the run — the schedule version, the
webhook delivery, or the request id — and every `audit_log` row a handler writes carries the run's
id as its request id, so a change made unattended traces to the schedule, and the schedule to the
person who set it. That record, over a period, is `PLT-18`'s "what the system did unattended".

A failed attempt is retried with exponential backoff and full jitter — a random delay up to the
backoff, so retries after a shared failure do not arrive together — up to a bound the kind declares.
A provider's refusal for its rate limit is a failed attempt like any other. A run that exhausts it is
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
* Good, because it deploys as the application does, and nothing in infrastructure knows a schedule:
  the tick only starts a pass.
* Good, because a person who has just connected a bank sees the first sync begin within the time a
  job takes to start, seconds to tens of seconds, without anything running while no one needs it.
* Good, because it is paid for only while it runs. A pass every fifteen minutes is about a third of
  the five-minute tick's $5 a month, under $2, before the free tier, against about $25 for a worker
  pool of one instance at 1 vCPU and 512 MiB by the rates Google publishes for us-central1.
* Bad, because work no one waits on waits up to a tick: a webhook's sync, a schedule's window. For
  the workloads above the delay is invisible; for one that needs it shorter, see Revisit when.
* Bad, because the API calls Cloud Run's Admin API, the one place the API knows the deployment's
  cloud. It sits behind a protocol with a local default, and its permission is to start the job and
  nothing more.
* Bad, because a run can be cut off: a pass's budget, a job's timeout, or a deploy. Every handler
  must tolerate running again from the start, which idempotency keys give writes but a handler must
  not undo with a side effect of its own.
* Bad, because the run table is read across entities, an exception to row-level security that has
  to stay content-free to stay harmless.
* Bad, because a Postgres queue degrades in known ways: dead rows from completed runs bloat the
  table, and one long-running transaction anywhere in the database holds back the cleanup of all of
  them. Completed runs are kept as the record of what ran (§ 4), so the claim reads from an index
  over open runs only.
* Neutral, because [ADR-0023](0023-one-image-many-entrypoints.md) gains a third runtime shape, the
  worker, beside the service and the job. On GCP it is run as a Cloud Run job until it is busy enough
  to be always on.

### Confirmation

Integration tests drive one pass as a function against the compose database: a
run enqueued in a transaction that rolls back is never claimed; two concurrent workers never claim
the same run; a cause arriving during a run enqueues one waiting run that is claimed only after the
running one finishes; an entity with a backlog does not delay another entity's due run; a throttled
kind starts no more runs than its limit; operational windows for many references are spread across
the interval; an expired lease makes a run due again; a stop signal, or a pass's budget running
out, claims nothing more; two passes at once never claim the same run; a missed span coalesces for an
ingestion kind and enumerates for a windowed one; a suspended entity's runs are not claimed and its
outbound runs are canceled; a run that exhausts its retries raises a notification; a person's request
whose wake fails leaves its run due.

A schema test asserts that the run table has no column of a money type and no free-text column
beyond the kind's reference. Content creeping into the queue is the failure § 6 exists to prevent.

`infra/gcp/setup/check.sh` asserts that `cfokit-work` runs the image the API runs.
`tests/test_gcp_infrastructure.py` asserts that the API holds `roles/run.jobsExecutor` on
`cfokit-work` and no other role on it.

Not gated: that the tick fires. A run overdue by more than a tick is the symptom, and watching for it
is monitoring's, not CI's.

## Pros and Cons of the Options

### A work table in Postgres, drained a pass at a time on a tick and when a person waits

* Good, because it is transactional with its cause, which no queue outside Postgres can be.
* Good, because it is paid for only while it runs, which while there is little work is almost never.
* Good, because the one wait a person sees — after connecting an account, asking for a sync, or
  repairing a connection — is a job's start, not a tick.
* Bad, because it has two triggers where a worker has none: a Cloud Scheduler job, with an identity
  allowed to start the job, and the API's wake, with its one permission.
* Bad, because work no one waits on waits up to fifteen minutes.

### The same table, drained by an always-running worker

The same code, looping in a Cloud Run worker pool of one instance, as it does locally.

* Good, because work starts within seconds of any cause, a webhook's included, with no trigger in
  infrastructure and no permission for the API to hold.
* Good, because it is the simplest shape to reason about: one process, always there.
* Bad, because it is paid for while idle, about $25 a month, for a queue that is empty almost all of
  every day while there is little work. It is where this design goes when that stops being true
  (§ 3); the code is the same, so going there later costs only infrastructure.

### The same table, drained by a job on a fixed tick alone

* Good, because it is the cheapest shape, with no permission for the API to hold.
* Bad, because a person who has just connected an account waits up to a tick, seven and a half minutes
  on average at fifteen, before the history they are waiting for begins to arrive, at the point a new
  customer is deciding whether CFOKit works. A tick short enough not to be noticed is not cheap: Cloud
  Run bills a job instance for at least a minute, so a one-minute tick costs about $44 a month, more
  than a worker.

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
* Bad, because the parts this record needs most — business schedules the entity versions, fairness
  between entities, throttling against a provider's limit,
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
  worker, beside the service and the job, run on GCP as a ticked and woken job; a run schedule is the
  entity's data.
* [ADR-0012](0012-binding-non-goals-and-scope-discipline.md)'s table of items that have passed the
  gate gains this record. A queue is not on the list, but an event bus is, and a queue is near enough
  to it that passing it unrecorded would be the drift the gate exists to catch.
* `infra/gcp/` gains the `cfokit-work` job, running `work --once` as the `cfokit-work` service
  account; a Cloud Scheduler job that starts it every fifteen minutes, as an identity holding
  `roles/run.jobsExecutor` on it and nothing else; and `roles/run.jobsExecutor` on it for
  `cfokit-service`. `infra/gcp/setup/deploy.sh` updates its image in the same rollout step as
  `cfokit-rest` and `cfokit-mcp`, as it does the migration job's.
* `compose.yaml` gains the worker as a service outside any profile, running `work`.
* `infra/README.md` states that any target must supply a way to run the worker unattended: a job it
  can start on a timer and on request, or one always-running process with no ingress. It gains
  `WORK_JOB`, the job a person's request starts, which a deployment that runs the worker
  continuously leaves unset.
* A kind of work declares its cadence bounds, its recovery of missed windows, whether it is ingestion
  or outbound, and its retry bound. A kind that leaves one undeclared does not register.
* A root `CLAUDE.md` rule: unattended work is enqueued as a run in the same transaction as its cause,
  and no schedule lives outside the database. What starts a pass knows only that one should start.
* Prices are from Google's published rate tables for us-central1. Worker pool pricing's own worked
  example comes out lower than the table, and the two were not reconciled, so the $25 is an upper
  estimate. The job's cost scales from the five-minute tick's estimate by the number of executions.
  Whether starting a job also needs the starter to act as the job's service account was not
  verified; the API is granted nothing more without a record saying why.

**Reversal cost.** Low for how a pass is run: a ticked job, a woken job and an always-running worker
run the same function, so moving between them changes infrastructure and not the queue. Moderate for the queue: every kind of unattended work is enqueued
through it, and replacing it with an external queue gives up enqueueing in the cause's transaction,
which would have to be rebuilt as an outbox — this table under another name.

## Revisit when

* The queue is rarely empty when a tick starts a pass, or people wait on the wake often enough that a
  job's start time shows: the case for the always-running worker (§ 3), and for removing the tick and
  the wake.
* A kind of work no person starts needs to start faster than a tick: the same case.
* One pass cannot keep up: runs waiting behind others long enough that the queue's lag is visible.
  More passes at once, or more instances of the worker, are the first answer, and they are already
  safe.
* Claiming contends: workers waiting on one another, or the run table large enough that the
  due-work query is no longer cheap. A Postgres queue's ceiling is not published anywhere this
  record could find; the symptom is the measure.
* Completed runs, kept as the record of what ran (§ 4), grow the run table to where its size is a
  cost of its own — at about eight runs a connection a day, tens of millions of rows a year at ten
  thousand connections. That is the case for partitioning it by month, and for a retention rule for
  run records under `PLT-19`.
* A deployment needs more of a provider's limit than its share, which is a conversation with the
  provider before it is a change here.
* A second cloud target is added that offers no job runtime a deployment can start on a timer and on
  request.
* Plaid stops requiring webhooks, or a feed provider pushes data rather than announcing it.
