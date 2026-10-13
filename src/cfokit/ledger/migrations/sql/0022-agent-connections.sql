-- Which agents have connected, for whom, and as what (ADR-0066 § 3).
--
-- An agent is the client a person signed in through, and the server learns only the client's
-- ID from the token. What the person needs in order to recognize it is what the client reports
-- about itself when it opens an MCP session, and which of their own accounts it signed in as.
-- Both are recorded here when the session opens, so the web client can name the agent rather
-- than show an ID.
--
-- **One row per agent and person**, updated as they connect again: the first connection, the
-- last, and what the client and the token said the last time. Each connection also writes its
-- own `audit_log` row, so the history is in the trail and this table holds the current answer.
--
-- **Nothing here decides anything.** The client's name and version are its own claim, shown to
-- the person beside its ID. Authority is the grant's alone (ADR-0039, ADR-0066 § 2).
--
-- **Scoped to the person, not to an entity.** A connection belongs to no company: it happens
-- before the agent is allowed anywhere. A row is visible and writable only to a transaction
-- that declared the person it belongs to in `cfokit.person_id`, which the service sets from the
-- authenticated principal for that transaction alone, never from anything a caller supplies.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

CREATE TABLE agent_connection (
    -- The agent, `client:<client_id>` (ADR-0066 § 1).
    agent_id           text        NOT NULL CHECK (agent_id LIKE 'client:_%'),
    -- The person it acts for: the token's `sub`.
    acting_for         text        NOT NULL CHECK (length(trim(acting_for)) > 0),
    -- What the client reported in `initialize`, or null where it reported nothing.
    client_name        text,
    client_version     text,
    -- The account the agent signed in as, from the token's standard OpenID Connect claims, or
    -- null where the issuer sends none.
    person_email       text,
    person_name        text,
    first_connected_at timestamptz NOT NULL DEFAULT now(),
    last_connected_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_id, acting_for)
);

CREATE INDEX agent_connection_person_idx ON agent_connection (acting_for, last_connected_at);

ALTER TABLE agent_connection ENABLE ROW LEVEL SECURITY;

CREATE POLICY agent_connection_own_rows ON agent_connection
    USING (acting_for = current_setting('cfokit.person_id', true));

-- No DELETE: a connection that happened stays recorded.
GRANT SELECT, INSERT, UPDATE ON agent_connection TO cfokit_app;

-- A connection's audit row belongs to no entity. The entity policy (0001) checks an insert
-- against the declared entity, which a row naming none never matches, so this admits exactly
-- that row and reads nothing: an entity-less row is visible to no transaction of the
-- application, as before.
CREATE POLICY audit_log_entityless_insert ON audit_log
    FOR INSERT
    WITH CHECK (entity_id IS NULL);
