"""Service layer — orchestration and invariants that span the repository.

Obligations, each of which is a bug if missed:

- Every state-changing call writes exactly one `audit_log` row.
- Every write takes `pg_advisory_xact_lock` for its entity, and carries an idempotency
  key (ADR-0029).
- Entity grants are validated server-side regardless of token contents (ADR-0011,
  ADR-0019).
- Never log token values, posting amounts, account numbers, or payee names at info
  level. Log identifiers and counts.
"""
