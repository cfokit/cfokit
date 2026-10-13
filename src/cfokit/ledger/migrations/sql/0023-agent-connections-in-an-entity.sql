-- An entity sees the connections its members made (ADR-0066 § 2, § 6).
--
-- Allowing an agent in a company is refused unless some person the agent connected for holds a
-- role there, and the company's administrators are shown the account an allowed agent signed in
-- as. Both read `agent_connection` under the entity's scope, where 0022's policy, keyed on the
-- person, admits nothing.
--
-- **What this allows, exactly.** A second policy, for reading only: under an entity's scope, a
-- connection is visible when the person it was made for holds a grant in force in that entity.
-- That person's membership is already visible there, in `entity_grant`, so the rows add the
-- agent's reported name and the account, nothing about any other entity. The subquery reads
-- `entity_grant` under its own policies, so it sees only the scoped entity's grants. Which of
-- these rows a caller is shown is narrowed again by the service, to administrators and to agents
-- allowed there.
--
-- `NULLIF` because a custom setting reads as an empty string, not null, once any transaction on
-- the connection has set it.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

CREATE POLICY agent_connection_entity_members ON agent_connection
    FOR SELECT
    USING (EXISTS (
        SELECT 1
          FROM entity_grant g
         WHERE g.entity_id = NULLIF(current_setting('cfokit.entity_id', true), '')::uuid
           AND g.principal_id = agent_connection.acting_for
           AND g.granted_at <= now()
           AND (g.lapses_at IS NULL OR g.lapses_at > now())
           AND (g.revoked_at IS NULL OR g.revoked_at > now())
    ));
