-- Conversations with CFOKit's runtime, and the files people attach to them (ADR-0075, ADR-0076).
--
-- **These tables are not the ledger's.** `cfokit.conversations` owns them. They live in this
-- schema and this sequence for the reason 0010 and 0014 give: a module is a sibling in the same
-- deployable, sharing one database (ADR-0022 § 3, ADR-0023).
--
-- **A conversation is evidence** (`SOC1-06`): what the model was given and what it did, kept as it
-- happened. So every table here is append-only, and nothing in a message is ever rewritten.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- One conversation: one company's, and one person's.
--
-- **The person, never an agent.** When the runtime starts a conversation it acts for somebody,
-- and the conversation is theirs (`PLT-04`): an agent acting for another person cannot read it.
-- ---------------------------------------------------------------------------
CREATE TABLE conversation (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   uuid        NOT NULL REFERENCES entity (id),
    person      text        NOT NULL CHECK (length(trim(person)) > 0),
    started_by  text        NOT NULL CHECK (length(trim(started_by)) > 0),
    started_at  timestamptz NOT NULL DEFAULT now(),

    -- What the composite keys below name, so a row can only refer to its own company's.
    UNIQUE (entity_id, id)
);

CREATE INDEX conversation_person_idx ON conversation (entity_id, person, started_at);

-- ---------------------------------------------------------------------------
-- A file a person attached: a receipt, a statement. Stored once per company by its SHA-256.
--
-- **`SOC2-01`, `BKP-20`: every file is content the organization did not author.** The
-- classification is a column rather than a convention, so it travels with the row for as long as
-- the row is kept, and a second class is a value added here rather than a guess made later. A
-- conversation holding one is offered no posting tool for the rest of it (ADR-0075, `PLT-23`).
--
-- The bytes are here rather than in an object store because Postgres is the only store
-- (ADR-0003), and 32 MB is the most the Messages API accepts in a request (ADR-0076).
-- ---------------------------------------------------------------------------
CREATE TABLE conversation_file (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       uuid        NOT NULL REFERENCES entity (id),
    sha256          text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    media_type      text        NOT NULL CHECK (length(trim(media_type)) > 0),
    size            integer     NOT NULL CHECK (size > 0 AND size <= 33554432),
    content         bytea       NOT NULL,
    classification  text        NOT NULL CHECK (classification IN ('untrusted')),
    uploaded_by     text        NOT NULL CHECK (length(trim(uploaded_by)) > 0),
    uploaded_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT size_is_the_contents CHECK (octet_length(content) = size),
    UNIQUE (entity_id, sha256),
    UNIQUE (entity_id, id)
);

-- ---------------------------------------------------------------------------
-- One message, in its place in the conversation.
--
-- `content` is the runtime's own serialized form of the message, Pydantic AI's provider-neutral
-- JSON (ADR-0076). This module stores it as the evidence it is and interprets none of it: what
-- the model saw is recoverable because nothing here reshapes it.
--
-- A request is what was sent to the model: the person's words, the files they attached, the
-- results of the tools it called. A response is what the model returned, and names the model and
-- the skill that produced it (`SOC1-06`, `SOC1-35`).
-- ---------------------------------------------------------------------------
CREATE TABLE conversation_message (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid        NOT NULL REFERENCES entity (id),
    conversation_id  uuid        NOT NULL,
    -- From 1, with no gaps: the order the model saw them in.
    position         integer     NOT NULL CHECK (position > 0),
    kind             text        NOT NULL CHECK (kind IN ('request', 'response')),
    content          jsonb       NOT NULL,
    model            text,
    model_version    text,
    skill_version    text,
    recorded_by      text        NOT NULL CHECK (length(trim(recorded_by)) > 0),
    recorded_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (conversation_id, position),
    UNIQUE (entity_id, id),
    -- With the entity, so a message cannot join another company's conversation, whatever id it
    -- is given: a foreign key is checked past row-level security.
    FOREIGN KEY (entity_id, conversation_id) REFERENCES conversation (entity_id, id),
    CONSTRAINT a_response_names_its_model CHECK (
        kind = 'request' OR (model IS NOT NULL AND skill_version IS NOT NULL)
    ),
    CONSTRAINT a_request_names_no_model CHECK (
        kind = 'response' OR (model IS NULL AND model_version IS NULL AND skill_version IS NULL)
    )
);

-- Which files a message carried. Keys Postgres enforces, so a message can never name a file that
-- is not there, or one of another company's (`BKP-19`'s reasoning, applied to the conversation).
CREATE TABLE conversation_message_file (
    entity_id   uuid NOT NULL REFERENCES entity (id),
    message_id  uuid NOT NULL,
    file_id     uuid NOT NULL,

    PRIMARY KEY (message_id, file_id),
    FOREIGN KEY (entity_id, message_id) REFERENCES conversation_message (entity_id, id),
    FOREIGN KEY (entity_id, file_id) REFERENCES conversation_file (entity_id, id)
);

CREATE INDEX conversation_message_file_file_idx ON conversation_message_file (file_id);

-- ---------------------------------------------------------------------------
-- Append-only (ADR-0007's reasoning applied to evidence).
-- ---------------------------------------------------------------------------
CREATE TRIGGER conversation_append_only
    BEFORE UPDATE OR DELETE ON conversation
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER conversation_file_append_only
    BEFORE UPDATE OR DELETE ON conversation_file
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER conversation_message_append_only
    BEFORE UPDATE OR DELETE ON conversation_message
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

-- `link_append_only` names the row by its `id`, which this table does not have.
CREATE FUNCTION conversation_message_file_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'append_only_violated: conversation_message_file rows are never changed or removed'
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER conversation_message_file_append_only
    BEFORE UPDATE OR DELETE ON conversation_message_file
    FOR EACH ROW EXECUTE FUNCTION conversation_message_file_append_only();

ALTER TABLE conversation              ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_file         ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_message      ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_message_file ENABLE ROW LEVEL SECURITY;

CREATE POLICY conversation_entity_isolation ON conversation
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY conversation_file_entity_isolation ON conversation_file
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY conversation_message_entity_isolation ON conversation_message
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY conversation_message_file_entity_isolation ON conversation_message_file
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT
    ON conversation, conversation_file, conversation_message, conversation_message_file
    TO cfokit_app;
