-- 0002 — privileges for the application role.
--
-- Migrations run as the schema owner; the application connects as `cfokit_app`, which is a
-- non-superuser and does not own these tables. That is what makes the row-level security
-- policies in 0001 actually apply — a superuser bypasses them entirely, and an owner bypasses
-- them unless the table is FORCE'd (ADR-0003).
--
-- The role is a deployment prerequisite, created out of band and documented in
-- infra/README.md. If it does not exist this migration fails, which is the right outcome: a
-- deployment missing the role would otherwise run with entity isolation silently halved.
--
-- Privileges are granted per table rather than with ON ALL TABLES, because the grants
-- restate ADR-0007 at a second layer. The append-only triggers already refuse these
-- operations; withholding the privilege as well means a defect in a trigger is not the only
-- thing standing between a bug and a rewritten ledger.

GRANT USAGE ON SCHEMA public TO cfokit_app;

-- Entities are ordinary mutable records: an entity can be renamed, and its basis can change
-- with a recorded effective date (LED-14).
GRANT SELECT, INSERT, UPDATE ON entity TO cfokit_app;

-- The chart of accounts grows over the life of the books (LED-01). No DELETE: an account
-- that has ever been posted to cannot be removed without orphaning history.
GRANT SELECT, INSERT, UPDATE ON account TO cfokit_app;

-- No DELETE, ever. ADR-0007: "A posted transaction is never altered or removed." The
-- append-only trigger refuses every DELETE including on drafts; this withholds the privilege
-- too. UPDATE is needed for the draft-to-posted transition and for editing a draft.
GRANT SELECT, INSERT, UPDATE ON ledger_transaction TO cfokit_app;

-- UPDATE and DELETE are needed while the parent transaction is a draft, and are refused by
-- the trigger once it is posted.
GRANT SELECT, INSERT, UPDATE, DELETE ON posting TO cfokit_app;

-- Insert-only, or it is not a trail. The trigger raises on any UPDATE or DELETE; the role
-- does not hold the privilege either.
GRANT SELECT, INSERT ON audit_log TO cfokit_app;

-- A replay reads the stored result; the original write records it (ADR-0029).
GRANT SELECT, INSERT, UPDATE ON idempotency_key TO cfokit_app;

-- Readable so /readyz can report pending migrations, never writable: applying a migration is
-- the migrate job's business and it runs as the owner (ADR-0004).
GRANT SELECT ON schema_migration TO cfokit_app;

-- entity.lock_key is an identity column, so inserting an entity needs its sequence.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cfokit_app;
