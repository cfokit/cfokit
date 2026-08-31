"""Persistence — hand-written SQL only (ADR-0028).

No SQLAlchemy, no SQLModel, no query builder. Auditability requirement: the SQL that
runs against the books is the SQL in this directory, readable without a translation step.

Postgres is the only backend (ADR-0003). All decimal columns are NUMERIC(28,10)
(ADR-0005). Financial records are append-only — no UPDATE on financial fields, no
DELETE; corrections are reversing entries (ADR-0007).
"""
