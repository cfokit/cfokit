# Ledger — package rules

Loads when you work in `src/cfokit/ledger/`. Root `CLAUDE.md` still applies.

## Layering

Enforced by `import-linter`, so a violation fails `uv run task lint` rather than surviving
review. (ADR-0008, ADR-0009)

```
api | mcp     protocol adapters — siblings, must not import each other
service       orchestration, audit, locking, grant validation
repository    hand-written SQL
engine        pure booking logic
```

Never skip a layer. An adapter that reaches into `repository` has bypassed audit logging,
entity locking, and grant validation in one move.

**`engine` is pure.** No I/O, no configuration, no database, no clock, no environment. Every
input is an argument and every output a return value. This is what makes booking semantics
testable with no infrastructure — layer 1 of ADR-0036, and the differential oracle later, when
`LED-18` activates it (ADR-0010). If a function in `engine` needs the current date, take it as a
parameter.

**Two adapters, one service layer.** `mcp` calls the service in-process — it does not loop
back through HTTP. (ADR-0009)

## SQL

Hand-written, in `repository/`. **No SQLAlchemy, no SQLModel, no query builder.** The SQL
that runs against the books is the SQL in that directory, readable without a translation
step. This is an auditability requirement, not a taste preference. (ADR-0028)

- All decimal columns are `NUMERIC(28,10)`. No `REAL`, `DOUBLE PRECISION`, `FLOAT`, or
  `MONEY` — `uv run task check-money` fails the build on any of them. (ADR-0005)
- **No `UPDATE` on financial fields. No `DELETE`.** Corrections are reversing entries.
  (ADR-0007)
- Every write takes `pg_advisory_xact_lock` for its entity. **Lock on `entity.lock_key`, never
  on a hash of `entity.id`.** ADR-0011 requires a documented, collision-free scheme; the advisory
  namespace is a global `bigint` and entity ids are uuids, so a hash is collision-*resistant* at
  best, and a collision silently serializes two unrelated entities against each other.
  `lock_key` is an identity column, so it is collision-free by construction. (ADR-0011)
- Row-level security keyed on `entity_id`, **plus** explicit service-layer filtering. Two
  layers, because RLS misconfiguration is silent.
- Zero-sum per commodity is a deferred constraint trigger, not only an application check.
  For a system whose value proposition is correct books, losing the database-level guard
  against silently creating money is disqualifying. (ADR-0006)
- Every transaction carries the principal that wrote it, its class — person, rule, or agent —
  and who it acted for. This ships in the migration that first writes transactions: added later,
  every existing row has an unknowable value. Same for the link to what a transaction was derived
  from. (`LED-20`, `BKP-19`, ADR-0033)

## Money

`decimal.Decimal` everywhere. **Never `float`, including in tests and fixtures** — a float
in a fixture teaches the next person the wrong thing and eventually leaks into production
code. (ADR-0005)

Construct from `str`, never from `float`: `Decimal("0.1")`, not `Decimal(0.1)`.

**Never round here.** Amounts are stored unrounded; rounding is a presentation concern and a
rounding call anywhere in this package means the boundary has been misplaced. Allocation — dividing
an amount so the parts sum exactly — lives in `engine`, is largest-remainder with ties broken by
line order, and is property-tested. (ADR-0025)

**Basis never branches a posting path.** An issued invoice posts whether the entity declared cash
or accrual; the cash view is derived from the stored obligation-to-settlement link. (ADR-0037)

## Service layer obligations

Each of these is a bug if missed, not a nice-to-have:

- **Exactly one `audit_log` row per state-changing call.** A code path that mutates state
  without one is a bug.
- Mandatory idempotency keys on writes. A retry must not double-book. (ADR-0029)
- Entity grants validated **server-side regardless of token contents**, inside the locked
  transaction rather than at the edge — which is also what makes `IAM-15`'s "takes effect
  immediately" true, since there is no cache to invalidate. An agent's authority is the
  **intersection** of its own grants and those of the person it acts for (`IAM-11`).
  (ADR-0011, ADR-0019)
- Audience validated against `AUTH_AUDIENCE` on every request carrying an issuer token — tokens
  from a shared issuer are otherwise replayable across resource servers. (ADR-0019) Without one, an
  entity's data is reached only through an `IAM-20` link or the relay's signed webhook (ADR-0052,
  ADR-0053).
- One request id per inbound call, propagated into `audit_log`.

## Errors

Stable, machine-readable `code` on every error crossing a published interface. Callers depend
on it, so adding a code is a contract change and renaming one is breaking. (ADR-0015)

## Logging

**Never log token values, posting amounts, account numbers, or payee names at info level.**
Log identifiers and counts. Structured JSON.

## Configuration

`config.py` is the complete surface, read from environment variables only. No cloud metadata,
no provider SDK at module scope. Adding a variable means updating `infra/README.md`, which is
authoritative for the names; changing the *shape* of that contract requires an ADR.
(ADR-0004, ADR-0016)

`PUBLIC_BASE_URL` is authoritative for anything the service says about itself. Never derive
external URLs from request headers.

## Migrations

Plain SQL in `migrations/sql/`, `NNNN-short-description.sql`, lexical order, never
renumbered. Applied by an explicit command, **never at startup**. (ADR-0004)

## Published interfaces

The REST OpenAPI document and the MCP tool descriptions are published interfaces with
stability obligations. Generated output must match what is committed; a diff means a contract
change and needs review. (ADR-0015)

## Stop and ask

Booking semantics, auth, and the write path need human review **before** you proceed. So does
adding any runtime dependency. The list lives in the root `pyproject.toml`, each entry carrying
its reason and its verified license in a comment beside it; read it there and count them there.
Whatever the number is, the next one is a decision rather than a convenience.

The count is deliberately not restated here. It was, and it drifted: this file said five while
the manifest held six, and the file with directory priority is the one an agent working in the
ledger reads. A fact worth stating twice is a fact that will disagree with itself.
