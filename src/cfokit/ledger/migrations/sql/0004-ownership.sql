-- Roles are rows; privileges are code (ADR-0039). Ownership (`IAM-21`, ADR-0038).
--
-- `IAM-01` makes a role "a defined set of capabilities", and `IAM-02` requires those
-- capabilities to distinguish reading, recording, posting, administering and holding. Which
-- roles exist, and which privileges each carries, is data: a role is added by inserting rows,
-- not by changing code and redeploying.
--
-- Privilege *names* stay in code, because a flag only means something if something checks it.
-- A row naming a privilege the code does not define confers nothing — it fails closed.

CREATE TABLE role (
    name        text PRIMARY KEY,
    description text NOT NULL,
    -- IAM-21: ownership cannot be granted for a stated period. IAM-09's lapse happens
    -- "without anyone acting", which must never be able to leave an entity unheld.
    never_lapses boolean NOT NULL DEFAULT false
);

CREATE TABLE role_privilege (
    role_name text NOT NULL REFERENCES role (name),
    privilege text NOT NULL,
    PRIMARY KEY (role_name, privilege)
);

-- The only role there is a case for. `owner` is what a person creating their own books holds,
-- and until somebody needs to delegate a part of it, a second role would be a name nobody
-- uses and a published contract nobody exercises. Others are added when the need arrives.
INSERT INTO role (name, description, never_lapses) VALUES
    ('owner', 'Holds the entity. Every privilege in it (IAM-21).', true);

INSERT INTO role_privilege (role_name, privilege) VALUES
    ('owner', 'read'),
    ('owner', 'record'),
    ('owner', 'post'),
    ('owner', 'grant'),
    ('owner', 'own');

-- The catalogue replaces the enumeration that was baked into the column.
ALTER TABLE entity_grant DROP CONSTRAINT entity_grant_role_check;

-- Entities created before this migration were given `administrator`, a role that no longer
-- exists, and would be left unheld: IAM-04's check counts owners and would find none. Nothing
-- has been released, so rather than migrate rows that exist on no deployment, this refuses
-- loudly. Locally the remedy is `docker compose down -v`.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM entity) THEN
        RAISE EXCEPTION
            'entities predate ownership and would be left unheld; recreate the database';
    END IF;
END $$;

ALTER TABLE entity_grant
    ADD CONSTRAINT entity_grant_role_fkey FOREIGN KEY (role) REFERENCES role (name);

-- Both tables are catalogue rather than entity data, so they are not entity-scoped and carry
-- no row-level security policy. Every session may read them; only a migration writes them.
GRANT SELECT ON role, role_privilege TO cfokit_app;
