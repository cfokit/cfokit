# cfokit-ledger

Multi-tenant Postgres double-entry accounting engine, exposed as an MCP server and a REST
service.

Publishes a tool contract and knows nothing about any consumer. The bookkeeper skill and
this package are separate systems with separate dependency graphs that share that
contract — there is no code dependency between them in either direction
([ADR-0014](../../../docs/decisions/README.md)).

## Layering

Enforced by import-linter, not by convention ([ADR-0008](../../../docs/decisions/README.md)):

| Layer | Responsibility |
|---|---|
| `api`, `mcp` | Protocol adapters. MCP calls the service layer in-process, not over HTTP. |
| `service` | Orchestration, audit logging, entity locking, grant validation. |
| `repository` | Hand-written SQL. No ORM. |
| `engine` | Pure booking logic. No I/O, no configuration, no clock. |

`config.py` is the complete configuration surface. Adding to it requires an ADR, because
`infra/README.md` is the portability contract
([ADR-0016](../../../docs/decisions/0016-opentofu-single-cloud-target-iac.md)).

## Non-negotiables

- Money is `decimal.Decimal`; all decimal columns are `NUMERIC(28,10)`. No floats
  anywhere, including tests and fixtures
  ([ADR-0005](../../../docs/decisions/README.md)).
- Financial records are append-only. Corrections are reversing entries
  ([ADR-0007](../../../docs/decisions/README.md)).
- Postgres is the only storage backend
  ([ADR-0003](../../../docs/decisions/0003-postgres-as-sole-storage-backend.md)).
- Every state-changing service call writes exactly one `audit_log` row.

## Migrations

Plain SQL in `src/cfokit/ledger/migrations/sql/`, named `NNNN-short-description.sql` and
applied in lexical order. They ship inside the package so the same files run in the
container, on a laptop, and in CI.

```
uv run task migrate        # explicit, never at startup
```
