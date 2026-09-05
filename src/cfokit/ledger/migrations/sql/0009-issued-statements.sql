-- Issued statements (`RPT-17`, `SOC1-20`).
--
-- `RPT-17`: "A statement can be marked issued, fixing what was reported, to whom, and when."
-- `SOC1-20`: "Where a correction posted after a statement was issued changes that statement's
-- figures, the issued statement is marked superseded, and both what was reported and what is
-- now true remain retrievable."
--
-- **Supersession is detected, not remembered**, the same way a stale year-end close is
-- (ADR-0027). The watermark is what the statement was produced at, and a posting that entered
-- the books after it and falls inside the statement's window changes its figures. That is a
-- query rather than a flag anyone maintains and can forget to.
--
-- **The figures are stored, and this is not a second source of truth about the books.** An
-- issued statement is a record of what was said to somebody outside — a document a lender
-- holds. `RPT-11` makes the books reproducible at the watermark, but reproducing them assumes
-- the presentation never changes, and it will: `RPT-12`'s display scale registry does not exist
-- yet and arrives later. What the recipient was told has to survive that.

CREATE TABLE issued_statement (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id    uuid        NOT NULL REFERENCES entity (id),
    report       text        NOT NULL
                             CHECK (report IN ('trial_balance', 'profit_and_loss', 'balance_sheet')),
    -- The window the statement covers. `since` is null for an as-of report, which has no start.
    since        date,
    as_of        date        NOT NULL,
    -- What the books stood at when it was produced (`RPT-11`). Re-running the report at this
    -- moment reproduces it, and a posting recorded after it may supersede it.
    watermark    timestamptz NOT NULL,
    -- IAM-13's shape: who did it, and when.
    issued_by    text        NOT NULL,
    issued_at    timestamptz NOT NULL DEFAULT now(),
    -- Free text: a lender, a board, an accountant. Not an identity — the recipient is usually
    -- not a principal of this deployment, and inventing one for them would be wrong.
    issued_to    text        NOT NULL,
    figures      jsonb       NOT NULL
);

CREATE INDEX issued_statement_lookup_idx ON issued_statement (entity_id, as_of);

-- ---------------------------------------------------------------------------
-- A statement was issued or it was not. Nothing edits or removes the record.
-- ---------------------------------------------------------------------------
CREATE TRIGGER issued_statement_append_only
    BEFORE UPDATE OR DELETE ON issued_statement
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

ALTER TABLE issued_statement ENABLE ROW LEVEL SECURITY;

CREATE POLICY issued_statement_entity_isolation ON issued_statement
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT ON issued_statement TO cfokit_app;
