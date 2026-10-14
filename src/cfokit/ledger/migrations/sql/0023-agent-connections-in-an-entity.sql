-- An entity sees the connections of the agents allowed in it (ADR-0066 § 2, § 6).
--
-- The company's administrators are shown the account an allowed agent signed in as, and allowing
-- an agent is refused unless some person it connected for holds a role there. Both read
-- `agent_connection` under the entity's scope, where 0022's policy, keyed on the person, admits
-- nothing.
--
-- **What this allows, exactly.** A second policy, for reading only: under an entity's scope, a
-- connection is visible when the agent holds a grant in force in that entity and so does the
-- person it was made for. Both are already visible there, in `entity_grant`, so the row adds the
-- agent's reported name and the account, nothing about any other entity, and nothing about an
-- agent a member connected but did not allow here. The subqueries read `entity_grant` under its
-- own policies, so they see only the scoped entity's grants.
--
-- Allowing checks membership after inserting the grant, in the same transaction: `granted_at`
-- defaults to `now()`, the transaction's start, so the new grant is in force for the check, and
-- a refusal rolls it back.
--
-- `NULLIF` because a custom setting reads as an empty string, not null, once any transaction on
-- the connection has set it.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

CREATE POLICY agent_connection_allowed_agents ON agent_connection
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
              FROM entity_grant g
             WHERE g.entity_id = NULLIF(current_setting('cfokit.entity_id', true), '')::uuid
               AND g.principal_id = agent_connection.agent_id
               AND g.granted_at <= now()
               AND (g.lapses_at IS NULL OR g.lapses_at > now())
               AND (g.revoked_at IS NULL OR g.revoked_at > now())
        )
        AND EXISTS (
            SELECT 1
              FROM entity_grant g
             WHERE g.entity_id = NULLIF(current_setting('cfokit.entity_id', true), '')::uuid
               AND g.principal_id = agent_connection.acting_for
               AND g.granted_at <= now()
               AND (g.lapses_at IS NULL OR g.lapses_at > now())
               AND (g.revoked_at IS NULL OR g.revoked_at > now())
        )
    );
