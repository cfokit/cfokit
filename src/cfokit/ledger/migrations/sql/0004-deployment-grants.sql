-- 0004 — deployment-scoped roles.
--
-- `IAM-18`: "Roles exist at two scopes, entity and deployment, and the two are independent.
-- Holding an administrative role in an entity confers nothing at deployment scope, and holding
-- a deployment-scoped role confers no role in any entity."
--
-- Independent means a separate table, not a nullable `entity_id` on `entity_grant`. A nullable
-- key would make "every grant in this entity" a query that silently returns deployment grants
-- to anyone who forgot the predicate, and the requirement is that the scopes confer nothing on
-- each other.
--
-- Same append-only shape as `entity_grant` and for the same reason (`IAM-14`): who held what,
-- at any past date, cannot be reconstructed from a table updated in place.
--
-- The first row is written by `python -m cfokit.ledger.bootstrap`, which is the only privileged
-- act that does not require a prior role (`IAM-06`, ADR-0038). There is no API path to it.

CREATE TABLE deployment_grant (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id text        NOT NULL,
    -- Deliberately one role today. `IAM-19` requires deployment capabilities to become
    -- enumerable and individually assignable, and that is a design this does not prejudge —
    -- adding values here is cheap, and splitting one value into several later is not.
    role         text        NOT NULL CHECK (role IN ('administrator')),
    -- `IAM-13`: who made it and when. The bootstrap names itself here, because the act has no
    -- prior principal to attribute to and recording "unknown" would be worse than recording
    -- what actually happened.
    granted_by   text        NOT NULL,
    granted_at   timestamptz NOT NULL DEFAULT now(),
    revoked_at   timestamptz,
    revoked_by   text,
    CONSTRAINT deployment_revoked_by_iff_revoked
        CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);

CREATE INDEX deployment_grant_lookup_idx ON deployment_grant (principal_id);

-- ---------------------------------------------------------------------------
-- Revoked, never edited and never removed. Identical reasoning to entity_grant.
-- ---------------------------------------------------------------------------
CREATE FUNCTION deployment_grant_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'append_only_violated: a grant is revoked, never deleted (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.id <> OLD.id
       OR NEW.principal_id <> OLD.principal_id
       OR NEW.role         <> OLD.role
       OR NEW.granted_by   <> OLD.granted_by
       OR NEW.granted_at   <> OLD.granted_at
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

CREATE TRIGGER deployment_grant_append_only
    BEFORE UPDATE OR DELETE ON deployment_grant
    FOR EACH ROW EXECUTE FUNCTION deployment_grant_append_only();

-- No row-level security: this table is not scoped to an entity, and a policy keyed on
-- `cfokit.entity_id` would hide every row from every session. Deployment scope is enforced in
-- the service layer, which is where ADR-0011 puts grant validation anyway.

GRANT SELECT, INSERT, UPDATE ON deployment_grant TO cfokit_app;

-- `audit_log.entity_id` is nullable already, which is what lets a deployment-scoped act — the
-- bootstrap, or creating an entity — be recorded before any entity exists to attribute it to.
