# Ledger — package rules

Loads when you work in `packages/ledger/`. Root `CLAUDE.md` still applies.

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
testable in isolation and differentially against the Beancount oracle (ADR-0010). If a
function in `engine` needs the current date, take it as a parameter.

**Two adapters, one service layer.** `mcp` calls the service in-process — it does not loop
back through HTTP. (ADR-0009)

## SQL

Hand-written, in `repository/`. **No SQLAlchemy, no SQLModel, no query builder.** The SQL
that runs against the books is the SQL in that directory, readable without a translation
step. This is an auditability requirement, not a taste preference. (ADR-0008)

- All decimal columns are `NUMERIC(28,10)`. No `REAL`, `DOUBLE PRECISION`, `FLOAT`, or
  `MONEY` — `uv run task check-money` fails the build on any of them. (ADR-0004)
- **No `UPDATE` on financial fields. No `DELETE`.** Corrections are reversing entries.
  (ADR-0006)
- Every write takes `pg_advisory_xact_lock` for its entity. (ADR-0011)
- Row-level security keyed on `entity_id`, **plus** explicit service-layer filtering. Two
  layers, because RLS misconfiguration is silent.
- Zero-sum per commodity is a deferred constraint trigger, not only an application check.
  For a system whose value proposition is correct books, losing the database-level guard
  against silently creating money is disqualifying. (ADR-0005)

## Money

`decimal.Decimal` everywhere. **Never `float`, including in tests and fixtures** — a float
in a fixture teaches the next person the wrong thing and eventually leaks into production
code. (ADR-0004)

Construct from `str`, never from `float`: `Decimal("0.1")`, not `Decimal(0.1)`.

## Service layer obligations

Each of these is a bug if missed, not a nice-to-have:

- **Exactly one `audit_log` row per state-changing call.** A code path that mutates state
  without one is a bug.
- Mandatory idempotency keys on writes. A retry must not double-book. (ADR-0011)
- Entity grants validated **server-side regardless of token contents**. (ADR-0011, ADR-0019)
- Audience validated against `AUTH_AUDIENCE` on every request — tokens from a shared issuer
  are otherwise replayable across resource servers. (ADR-0019)
- One request id per inbound call, propagated into `audit_log`.

## Errors

Stable, machine-readable `code` on every error crossing a published interface. Callers depend
on it, so adding a code is a contract change and renaming one is breaking. (ADR-0015)

## Logging

**Never log token values, posting amounts, account numbers, or payee names at info level.**
Log identifiers and counts. Structured JSON.

## Configuration

`config.py` is the complete surface, read from environment variables only. No cloud metadata,
no provider SDK at module scope. Adding a variable requires an ADR, because `infra/README.md`
is the portability contract. (ADR-0003, ADR-0016)

`PUBLIC_BASE_URL` is authoritative for anything the service says about itself. Never derive
external URLs from request headers.

## Migrations

Plain SQL in `migrations/sql/`, `NNNN-short-description.sql`, lexical order, never
renumbered. Applied by an explicit command, **never at startup**. (ADR-0003)

## Published interfaces

The REST OpenAPI document and the MCP tool descriptions are published interfaces with
stability obligations. Generated output must match what is committed; a diff means a contract
change and needs review. (ADR-0015)

## Stop and ask

Booking semantics, auth, and the write path need human review **before** you proceed. So does
adding any runtime dependency — this package currently has none, and that is deliberate.
