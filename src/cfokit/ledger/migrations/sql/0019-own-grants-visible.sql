-- A principal may see its own grants in every entity, and nothing else of any entity's
-- (`IAM-08`, `IAM-01`).
--
-- **Why.** An agent, or the web client, has to be able to ask which companies the person holds
-- a role in; without that, every conversation starts with the person reciting an entity id. The
-- answer is in `entity_grant`, which row-level security scopes to one entity at a time (0003), so
-- no query can see across entities to answer it.
--
-- **What this allows, exactly.** A second policy, for reading only: a row is visible when it
-- names the principal the transaction declared, in `cfokit.principal_id`. Policies of the same
-- command combine with OR, so a transaction scoped to an entity still sees that entity's grants
-- as before; one that declares a principal also sees that principal's own grants elsewhere — the
-- entity, the role and the dates of each — and not another principal's, and not one row of any
-- entity's books. Writes are untouched: the policy is `FOR SELECT`, so granting and revoking
-- still require the entity's scope.
--
-- **Who declares the principal.** Only the read that lists a caller's entities, which sets it to
-- the authenticated principal for that transaction alone (`set_config(..., true)`), never from
-- anything a caller supplies. Unset, `current_setting` returns null, which matches no row, so
-- every existing query is unchanged.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

CREATE POLICY entity_grant_own_rows ON entity_grant
    FOR SELECT
    USING (principal_id = current_setting('cfokit.principal_id', true));
