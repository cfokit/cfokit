-- Notifications, and what closed them (`PLT-07`, ADR-0052, ADR-0056).
--
-- **The ledger's tables, with generic columns.** Any module raises a notification without
-- depending on another, and the ledger learns no domain meaning from it, as it learns none from
-- `audit_log`: a class, an opaque reference to what it is about, and where it is answered.
--
-- **A notification is written in the same transaction as the act that raises it**, so a change
-- that rolls back leaves no question behind, and a question cannot exist without its act.
--
-- **Open is derived, never stored.** A notification is open until a closing row exists for it.
-- There is no status column to update and no read or unread: what the list counts is what still
-- needs the person (ADR-0056 § 3).
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- One notification, to one recipient. A question raised to two owners is two rows, because
-- each of them may dismiss their own (ADR-0056 § 2).
-- ---------------------------------------------------------------------------
CREATE TABLE notification (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id          uuid        NOT NULL REFERENCES entity (id),
    -- The principal it is addressed to. Checked to hold a role in this entity before the row is
    -- written, under the same grant check as any other act (ADR-0052 § 1, `NFR-04`).
    recipient          text        NOT NULL CHECK (length(trim(recipient)) > 0),
    -- What kind of question it is. Named by the module that raises it; the ledger reads it only
    -- to find the notifications an answering act closes.
    notification_class text        NOT NULL CHECK (notification_class ~ '^[a-z][a-z_]*$'),
    -- What it is about, opaque. Not a foreign key: what it names belongs to the module that
    -- raised it, and a REFERENCES into a module's table is the dependency ADR-0022 forbids.
    subject_ref        text        NOT NULL CHECK (length(trim(subject_ref)) > 0),
    -- Where it is answered, as a path under the deployment's own address. A path rather than a
    -- URL, because `PUBLIC_BASE_URL` is authoritative for the address and can change.
    link               text        NOT NULL CHECK (link LIKE '/%'),
    raised_at          timestamptz NOT NULL DEFAULT now()
);

-- A person's open list, and the lookup an answering act makes for its subject.
CREATE INDEX notification_recipient_idx ON notification (entity_id, recipient, raised_at);
CREATE INDEX notification_subject_idx
    ON notification (entity_id, notification_class, subject_ref);

-- ---------------------------------------------------------------------------
-- What closed a notification. Two kinds, written by two different things:
--
-- * `answered` — by the act that answers the question, in that act's own transaction, for every
--   recipient's notification about the subject (ADR-0056 § 1). `closed_by` is the principal
--   whose act it was, and `act_ref` names the act, so "answered by this" is recorded rather
--   than inferred.
-- * `dismissed` — by the recipient, for their own alone, as themselves and never through an
--   agent (ADR-0056 § 2).
--
-- Each at most once per notification. A dismissed notification whose subject is later answered
-- gains an `answered` row as well; nothing re-opens.
-- ---------------------------------------------------------------------------
CREATE TABLE notification_closing (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid        NOT NULL REFERENCES entity (id),
    notification_id  uuid        NOT NULL REFERENCES notification (id),
    kind             text        NOT NULL CHECK (kind IN ('answered', 'dismissed')),
    closed_by        text        NOT NULL CHECK (length(trim(closed_by)) > 0),
    act_ref          text,
    closed_at        timestamptz NOT NULL DEFAULT now(),

    UNIQUE (notification_id, kind),
    CONSTRAINT an_answer_names_its_act CHECK ((kind = 'answered') = (act_ref IS NOT NULL))
);

-- ---------------------------------------------------------------------------
-- Append-only (ADR-0052 § 1). What happens to a notification afterwards is a row of its own.
-- ---------------------------------------------------------------------------
CREATE TRIGGER notification_append_only
    BEFORE UPDATE OR DELETE ON notification
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER notification_closing_append_only
    BEFORE UPDATE OR DELETE ON notification_closing
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

ALTER TABLE notification         ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_closing ENABLE ROW LEVEL SECURITY;

CREATE POLICY notification_entity_isolation ON notification
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY notification_closing_entity_isolation ON notification_closing
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT ON notification, notification_closing TO cfokit_app;
