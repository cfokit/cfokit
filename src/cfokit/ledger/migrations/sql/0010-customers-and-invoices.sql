-- Customers and invoices (`AR-01` to `AR-06`, ADR-0022).
--
-- **These tables are not the ledger's.** The ledger owns the double-entry primitive and
-- "knows nothing about customers, invoices, banks" — ADR-0022's test is that if the ledger
-- needs to know what a customer is, the boundary has moved wrongly. `cfokit.receivables`
-- owns them, and reaches them through its own repository.
--
-- They live in this schema and in this migration sequence because a module is a sibling in
-- the same deployable, sharing one database and one transaction (ADR-0022 § 3, ADR-0023). An
-- issued invoice and the postings it produces must reach one COMMIT, which is the whole
-- reason receivables is in-process rather than a separate component.

CREATE TABLE customer (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id  uuid        NOT NULL REFERENCES entity (id),
    -- What the entity calls them. Not unique: two customers legitimately share a name, and a
    -- uniqueness constraint here would force an operator to invent a distinction that does
    -- not exist in their world.
    name       text        NOT NULL CHECK (length(trim(name)) > 0),
    -- Where an invoice is delivered, when it is delivered by email. `AR-07` makes delivery
    -- the operator's act by any means, so this is optional and carries no format constraint
    -- beyond being non-empty — an address CFOKit rejects is an invoice that cannot be sent.
    email      text        CHECK (email IS NULL OR length(trim(email)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Archived rather than deleted. An invoice names its customer for as long as the invoice
    -- exists, and financial records are append-only (ADR-0007).
    archived_at timestamptz
);

CREATE INDEX customer_entity_name_idx ON customer (entity_id, lower(name));

-- ---------------------------------------------------------------------------
-- Invoices. Draft until issued, and permanent after (`AR-04`).
-- ---------------------------------------------------------------------------
CREATE TABLE invoice (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   uuid        NOT NULL REFERENCES entity (id),
    customer_id uuid        NOT NULL REFERENCES customer (id),
    status      text        NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft', 'issued', 'cancelled')),
    -- Assigned at issue and never before, from a gapless series (`AR-05`). A draft has none,
    -- because a draft that never issues would otherwise consume a number and leave the gap
    -- the requirement forbids.
    number      integer     CHECK (number IS NULL OR number > 0),
    issue_date  date,
    -- Derived from the terms at issue (`AR-06`), and stored rather than recomputed: terms can
    -- change, and an issued invoice's due date is a fact about what was sent.
    due_date    date,
    -- Free text, because payment terms are whatever the parties agreed. `AR-06` requires a due
    -- date derived from them; it does not require CFOKit to have opinions about "net 30".
    terms       text,
    commodity   text        NOT NULL,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    issued_at   timestamptz,
    -- The postings an issue produced. Null while draft: an unissued invoice is not in the
    -- books (`AR-04`), exactly as a draft transaction is not (`LED-07`).
    transaction_id uuid     REFERENCES ledger_transaction (id),
    cancelled_at   timestamptz,
    cancel_reason  text,

    -- The number series has no gaps, so a number is unique within its entity and a cancelled
    -- invoice keeps the one it had (`AR-05`).
    UNIQUE (entity_id, number),
    -- Issued means: numbered, dated, and in the books. Anything less is a partial issue, and
    -- a partial issue is what leaves a number pointing at nothing.
    CONSTRAINT issued_is_complete CHECK (
        (status = 'draft') = (number IS NULL)
        AND (status = 'draft') = (issued_at IS NULL)
        AND (status = 'draft') = (transaction_id IS NULL)
        AND (status = 'draft') = (issue_date IS NULL)
    ),
    CONSTRAINT cancelled_has_a_reason CHECK (
        (status = 'cancelled') = (cancelled_at IS NOT NULL)
        AND (cancelled_at IS NULL OR length(trim(cancel_reason)) > 0)
    )
);

CREATE INDEX invoice_entity_status_idx ON invoice (entity_id, status, issue_date);
CREATE INDEX invoice_customer_idx ON invoice (customer_id);

CREATE TABLE invoice_line (
    id          uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   uuid           NOT NULL REFERENCES entity (id),
    invoice_id  uuid           NOT NULL REFERENCES invoice (id) ON DELETE CASCADE,
    -- Position on the document, so two exports of an unchanged invoice read alike.
    position    integer        NOT NULL CHECK (position > 0),
    description text           NOT NULL CHECK (length(trim(description)) > 0),
    -- `AR-03`: every line names the income account it credits, which is what makes an issued
    -- invoice a posting rather than only a document.
    account_id  uuid           NOT NULL REFERENCES account (id),
    quantity    numeric(28,10) NOT NULL DEFAULT 1 CHECK (quantity <> 0),
    unit_amount numeric(28,10) NOT NULL,
    created_at  timestamptz    NOT NULL DEFAULT now(),

    UNIQUE (invoice_id, position)
);

CREATE INDEX invoice_line_invoice_idx ON invoice_line (invoice_id);

-- ---------------------------------------------------------------------------
-- The gapless series (`AR-05`).
--
-- A Postgres sequence is not gapless: it advances outside the transaction so a rollback
-- leaves a hole, which is the property that makes sequences fast and the one this cannot
-- have. A counter row updated inside the transaction gives up that concurrency, and the write
-- path already serialises per entity on an advisory lock (ADR-0006, ADR-0029), so there is no
-- concurrency here to give up.
-- ---------------------------------------------------------------------------
CREATE TABLE invoice_series (
    entity_id uuid    PRIMARY KEY REFERENCES entity (id),
    next      integer NOT NULL DEFAULT 1 CHECK (next > 0)
);

-- ---------------------------------------------------------------------------
-- An issued invoice is never edited (`AR-14`). A correction is a credit note or a reversal,
-- and both the original and the correction stay visible.
--
-- Enforced here rather than in the service layer for the same reason as the ledger's own
-- append-only rules: the guarantee is the product, and a rule only the application honours is
-- a rule the next bulk-import script will not (ADR-0007).
-- ---------------------------------------------------------------------------
CREATE FUNCTION invoice_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'append_only_violated: invoices are never deleted (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.status = 'draft' THEN
        RETURN NEW;  -- freely editable until issued (`AR-04`)
    END IF;

    -- Issued or cancelled. The only permitted move is issued -> cancelled, and the invoice
    -- itself is otherwise fixed: a cancelled invoice keeps its number and stays visible as
    -- cancelled (`AR-05`).
    IF NEW.status <> OLD.status AND NOT (OLD.status = 'issued' AND NEW.status = 'cancelled') THEN
        RAISE EXCEPTION
            'append_only_violated: invoice % is %; correct it with a credit note', OLD.id, OLD.status
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.id <> OLD.id
        OR NEW.entity_id <> OLD.entity_id
        OR NEW.customer_id <> OLD.customer_id
        OR NEW.number IS DISTINCT FROM OLD.number
        OR NEW.issue_date IS DISTINCT FROM OLD.issue_date
        OR NEW.due_date IS DISTINCT FROM OLD.due_date
        OR NEW.commodity <> OLD.commodity
        OR NEW.transaction_id IS DISTINCT FROM OLD.transaction_id
        OR NEW.issued_at IS DISTINCT FROM OLD.issued_at
    THEN
        RAISE EXCEPTION 'append_only_violated: invoice % is issued and is never edited', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER invoice_append_only
    BEFORE UPDATE OR DELETE ON invoice
    FOR EACH ROW EXECUTE FUNCTION invoice_append_only();

CREATE FUNCTION invoice_line_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
BEGIN
    SELECT status INTO parent_status FROM invoice
     WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.invoice_id ELSE NEW.invoice_id END;

    IF parent_status <> 'draft' THEN
        RAISE EXCEPTION
            'append_only_violated: the lines of an issued invoice are never changed'
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER invoice_line_append_only
    BEFORE UPDATE OR DELETE ON invoice_line
    FOR EACH ROW EXECUTE FUNCTION invoice_line_append_only();

-- ---------------------------------------------------------------------------
-- Entity isolation, the same second layer every other table has (ADR-0003).
-- ---------------------------------------------------------------------------
ALTER TABLE customer ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_line ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_series ENABLE ROW LEVEL SECURITY;

CREATE POLICY customer_entity_isolation ON customer
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY invoice_entity_isolation ON invoice
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY invoice_line_entity_isolation ON invoice_line
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY invoice_series_entity_isolation ON invoice_series
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

-- A customer's name and an invoice's terms are editable while the record is live, so these
-- carry UPDATE where the ledger's own tables do not. The triggers above decide what an update
-- may touch; the grant decides only that one is possible at all.
GRANT SELECT, INSERT, UPDATE ON customer, invoice, invoice_line, invoice_series TO cfokit_app;

-- DELETE on lines alone, and only because a draft is freely editable (`AR-04`): rewriting one
-- means removing the lines that were there. The trigger above refuses it the moment the
-- invoice leaves draft, so this is the same two layers as everywhere else — the grant makes
-- the operation possible and the trigger decides when it is allowed (ADR-0003, ADR-0007).
--
-- Not on `invoice` or `customer`. Neither is ever deleted: an invoice is cancelled and keeps
-- its number (`AR-05`), and a customer is archived because an invoice names it for as long as
-- the invoice exists.
GRANT DELETE ON invoice_line TO cfokit_app;
