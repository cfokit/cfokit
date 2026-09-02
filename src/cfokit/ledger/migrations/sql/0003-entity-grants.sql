-- 0003 — entity grants: who may do what, in which entity.
--
-- `IAM-01`: "An identity's access to an entity is governed by a role. A role carries a
-- defined set of capabilities, and an identity holding no role for an entity can do nothing
-- with it."
--
-- **A grant is a record with a history, not a current-state row.** `IAM-14` requires the
-- system to produce, for any date in the past, who held which role and who granted it, and
-- states that "current state is not sufficient". That cannot be reconstructed from a table
-- that is updated in place, which is the same argument ADR-0013 made for `recorded_at`: the
-- property has to be designed in, because it cannot be recovered afterwards.
--
-- So rows are immutable except for the one transition a grant genuinely has — being revoked —
-- and a trigger enforces that nothing else changes. Deletion is refused outright: a grant that
-- vanished would take its history with it.
--
-- Decisions and requirements relied on:
--   IAM-01   Access is governed by a role; no role means no access
--   IAM-02   Roles distinguish reading, recording, posting, administering
--   IAM-09   A role can be granted for a stated period and lapses without anyone acting
--   IAM-11   A skill acts for a person; authority is the intersection of the two
--   IAM-13   Every grant, revocation and lapse is recorded, with who and when
--   IAM-14   Point-in-time reconstruction of who held which role
--   ADR-0003 Row-level security keyed on entity_id
--   ADR-0011 Grants are validated server-side regardless of token contents

CREATE TABLE entity_grant (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id    uuid        NOT NULL REFERENCES entity (id),
    -- The identity or skill this grant is for. Opaque here: resolving it to a person is the
    -- identity provider's business, and the ledger never learns what a skill is (ADR-0022).
    principal_id text        NOT NULL,
    -- Superseded by 0004: the catalogue in `role` replaced this enumeration, because which
    -- roles exist is data rather than a fixed list (ADR-0040). Left as written; a migration
    -- is a record of what was applied.
    role         text        NOT NULL CHECK (role IN ('reader', 'recorder', 'poster', 'administrator')),
    -- IAM-13: who made it, and when.
    granted_by   text        NOT NULL,
    granted_at   timestamptz NOT NULL DEFAULT now(),
    -- IAM-09: "A role can be granted for a stated period, after which it lapses without
    -- anyone acting." Null means open-ended. Lapsing is the absence of a further act, so it
    -- is a stored boundary rather than a job that has to run.
    lapses_at    timestamptz,
    -- IAM-15: revocation takes effect immediately. The row stays so IAM-14 can still answer
    -- what was held before it.
    revoked_at   timestamptz,
    revoked_by   text,
    CONSTRAINT revoked_by_iff_revoked CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);

-- The lookup every write makes: what does this principal hold in this entity, now.
CREATE INDEX entity_grant_lookup_idx ON entity_grant (entity_id, principal_id);
-- IAM-14's query: who held what, at a date.
CREATE INDEX entity_grant_history_idx ON entity_grant (entity_id, granted_at);

-- ---------------------------------------------------------------------------
-- A grant is revoked, never edited and never removed.
-- ---------------------------------------------------------------------------
CREATE FUNCTION entity_grant_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'append_only_violated: a grant is revoked, never deleted (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.id           <> OLD.id
       OR NEW.entity_id    <> OLD.entity_id
       OR NEW.principal_id <> OLD.principal_id
       OR NEW.role         <> OLD.role
       OR NEW.granted_by   <> OLD.granted_by
       OR NEW.granted_at   <> OLD.granted_at
       OR NEW.lapses_at IS DISTINCT FROM OLD.lapses_at
    THEN
        RAISE EXCEPTION
            'append_only_violated: only revocation may change a grant (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION
            'append_only_violated: grant % is already revoked', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER entity_grant_append_only
    BEFORE UPDATE OR DELETE ON entity_grant
    FOR EACH ROW EXECUTE FUNCTION entity_grant_append_only();

-- ---------------------------------------------------------------------------
-- Entity isolation, as for every other tenant table (ADR-0003).
-- ---------------------------------------------------------------------------
ALTER TABLE entity_grant ENABLE ROW LEVEL SECURITY;

CREATE POLICY entity_grant_entity_isolation ON entity_grant
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

-- No DELETE: the trigger refuses it and the role does not hold the privilege either
-- (0002 explains why both).
GRANT SELECT, INSERT, UPDATE ON entity_grant TO cfokit_app;
