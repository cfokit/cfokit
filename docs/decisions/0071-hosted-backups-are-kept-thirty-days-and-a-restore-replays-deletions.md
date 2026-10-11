---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0071: Backups on GCP are kept thirty days in the US, and a restore replays every deletion since its point

**Requirements served:** `NFR-07`, `PLT-13`, `PLT-19`, `SOC2-14`, `SOC2-18`.

## Context and Problem Statement

`NFR-07` requires committed records to survive the loss of any machine or storage device, a
deployment to be restorable to a known point, and the restore to be exercised rather than assumed.
`PLT-13` requires a deleted entity's data to be destroyed and the deletion confirmed, and `SOC2-18`
extends that to every copy derived from it. Backups are a copy, so the two pull against each other:
the longer backups are kept, the longer a deletion takes to be complete.

Facts that shape the answer:

* **The live database is the archive.** Ledger records are kept indefinitely and supporting
  documents for seven years in the database itself (`PLT-20`), and disposal is a deliberate,
  logged act (`PLT-19`). Backups exist to recover from a disaster or a mistake, not to keep history.
* **Cloud SQL backups cannot be edited.** A deleted entity's rows stay in every backup taken before
  the deletion until that backup expires.
* **Cloud SQL Enterprise edition**, which CFOKit's instance runs (ADR-0060), keeps point-in-time
  recovery logs for at most seven days. Automated backups are kept by count, up to 365. With
  `retain_backups_on_delete`, they outlive a deleted instance and expire on the same schedule.
  On-demand backups are kept until someone deletes them.
* **A backup's location defaults to the multi-region nearest the instance**, which for `us-central1`
  is the United States. Stating it makes the location a property of the deployment rather than of
  Google's default (`SOC2-14`).
* **Restoring to a point before a deletion brings the deleted entity back.** The database's own
  record of the deletion is not in a backup taken before it.
* **The GCP module's defaults are CFOKit's own production values**, and a self-hosted deployment on
  GCP overrides them through `TF_VAR_*` (`infra/gcp/variables.tf`). The compose stack has no backup
  of its own: its operator backs up the Postgres volume as for any self-hosted Postgres.

## Decision Drivers

* **A disaster or a mistake noticed weeks later is recoverable** (`NFR-07`).
* **A deletion is complete within a stated, short time**, including in backups (`PLT-13`,
  `SOC2-18`).
* **A restore never brings back what was deleted.**
* **The restore is exercised, with evidence** (`NFR-07`).
* **Backups are encrypted with CFOKit's key and kept in a stated place** (`SOC2-14`).
* **No cost beyond the instance CFOKit already runs.**

## Considered Options

* Thirty daily backups and seven days of recovery logs, in the US, with deletions replayed on restore
* Fourteen daily backups, as configured
* A year of backups, with monthly exports to Cloud Storage
* Enterprise Plus, for thirty-five days of recovery logs
* Copying backups to a second region

## Decision Outcome

Chosen option: "Thirty daily backups and seven days of recovery logs, in the US, with deletions
replayed on restore", because it recovers from a mistake noticed within a month, and bounds a
deletion's completion at thirty days.

> On GCP, Cloud SQL keeps thirty daily backups and seven days of recovery logs, in the `us`
> multi-region, encrypted with CFOKit's key. A deletion is complete when the last backup taken before
> it expires, at most thirty days later. Every restore replays the deletions recorded after its point
> before it serves anyone.

### 1. What is kept

* **Daily automated backups, thirty retained**, starting at 07:00 UTC.
* **Point-in-time recovery, seven days**, so any moment in the last week is recoverable.
* **Location `us`**, stated in the configuration.
* **No standing on-demand backups.** One taken for an operation, such as before a risky migration,
  is deleted when the operation is done, so nothing outlives the thirty days.
* **After the instance is deleted**, its backups follow the same thirty-day expiry
  (`retain_backups_on_delete`).

Each is a variable of the GCP module with these values as its defaults, so a self-hosted deployment on
GCP chooses its own.

### 2. Deletion and backups

Deleting an entity destroys its rows in the live database at once (`PLT-13`). Backups taken before
the deletion still hold them, and expire within thirty days. The confirmation to the requester says
both: that the entity is destroyed, and the date by which no backup holds it.

Each deletion is also written to the project's locked audit log bucket (`infra/gcp/audit.tf`, kept
400 days), outside the database a restore would replace.

### 3. A restore replays deletions

A restore is to a new instance, never over the live one. Before the restored instance serves anyone,
every entity deletion the audit log records after the restore's point is carried out again, and so is
every disposal the destruction log records (`PLT-19`). The restore's record lists what was replayed.

### 4. The restore is exercised

Each quarter, a named person clones the production instance to a point in time, runs the
restore's checks against the clone (migrations current, each entity's records complete under
`NFR-23`, the deletion replay), records the result, and deletes the clone. The clone raises the
existing alert on Cloud SQL restores and clones (`infra/gcp/monitoring.tf`), which is the evidence it
happened.

### Consequences

* Good, because a mistake noticed within a month is recoverable, and one within a week to the
  minute.
* Good, because a deletion is complete within a known thirty days, and the requester is told when.
* Good, because a restore cannot bring back a deleted entity.
* Good, because the backups' location and key are stated properties of the deployment.
* Bad, because a mistake noticed after thirty days is not recoverable from a backup. The live
  database's own history, append-only for financial records (ADR-0007), is what covers longer.
* Bad, because a restore has a step beyond Cloud SQL's, and the replay depends on the audit log
  bucket being intact.
* Neutral, because thirty small backups cost little against the instance itself.

### Confirmation

* The GCP module sets the values in § 1, and a review of `database.tf` shows them.
* The quarterly drill's record, and the clone alert it raised, are the evidence for `NFR-07`.
* The restore's replay is tested: an entity deleted after a restore point is absent from the
  restored database once the replay runs.

## Pros and Cons of the Options

### Thirty daily backups and seven days of recovery logs, in the US, with deletions replayed on restore

* Good, because it meets every driver.
* Bad, because it adds the replay to every restore.

### Fourteen daily backups, as configured

* Good, because a deletion completes in two weeks.
* Bad, because a mistake found at a month's end, when an owner reconciles, is past every backup.
  Owners look at their books rarely, so mistakes are found late.

### A year of backups, with monthly exports to Cloud Storage

The archive many services keep, and what an auditor sometimes expects to see.

* Good, because almost any mistake is recoverable.
* Bad, because a deletion would not be complete for a year, which no requester would accept as
  honoring `PLT-13`.
* Bad, because the live database already keeps the records for as long as the retention schedule
  requires; a year of backups would duplicate it.

### Enterprise Plus, for thirty-five days of recovery logs

* Good, because any moment in the last month would be recoverable.
* Bad, because its smallest machine costs about twice the shared core CFOKit runs (ADR-0060), for
  minute-level recovery that a daily backup and a week of logs nearly match.

### Copying backups to a second region

* Good, because it would survive the loss of the whole US multi-region.
* Bad, because a multi-region location already spans several US regions, and a second copy is a
  second place a deletion must reach.

## More Information

**Follow-on obligations.**

* `infra/gcp/database.tf` and `variables.tf`: the values in § 1, as variables.
* Entity deletion writes its record to the application log, routed to the audit bucket.
* The restore procedure and the quarterly drill's script, in `infra/gcp/setup/`, with the replay.
* The Privacy Policy states the thirty days.

**Reversal cost.** Low. Every value is a setting; raising retention takes effect at once, and lowering
it expires older backups at the next run.

Related: ADR-0003 (Postgres is the only store), ADR-0007 (append-only records), ADR-0060 (the GCP
deployment).

[Cloud SQL: about backups](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups) ·
[Cloud SQL: point-in-time recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)

## Revisit when

* A customer or an auditor requires a recovery window longer than thirty days.
* CFOKit moves to Enterprise Plus for another reason, which makes thirty-five days of recovery logs
  free to take.
* The Availability category is taken in SOC 2 scope, which would turn these values into stated
  commitments.
