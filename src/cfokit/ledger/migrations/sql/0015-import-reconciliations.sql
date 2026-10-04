-- An import's reconciliation, as it stood when the import finished (`IMP-08`, ADR-0058).
--
-- **These tables are not the ledger's.** `cfokit.imports` owns them. They live in this schema
-- and this sequence for the reason 0010 and 0012 give: a module is a sibling in the same
-- deployable, sharing one database (ADR-0022 § 3, ADR-0023).
--
-- **What is stored is the comparison as it was run**: the figures the source stated for itself,
-- ours beside them, and nothing derived from the two. Whether a figure agrees, and whether a set
-- of differences nets to zero, is arithmetic on what is here and is done when it is read. The
-- books keep changing after an import; this is what a person was shown when it finished, so a
-- later conversation explains that rather than a figure recomputed against different books.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- One reconciliation of one import. An import reconciled twice has two rows; the later one is
-- the current answer, and the earlier one is what was shown before it.
-- ---------------------------------------------------------------------------
CREATE TABLE import_reconciliation (
    id               uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid           NOT NULL REFERENCES entity (id),
    -- Derived from the file's fingerprint, never stored elsewhere (ADR-0029).
    import_id        text           NOT NULL CHECK (length(trim(import_id)) > 0),
    -- The period the source's statements cover. Null is "all dates", as the source ran them.
    since            date,
    as_of            date,
    -- The journal total the source printed, and ours. All four, or none where it printed none.
    stated_debits    numeric(28,10),
    stated_credits   numeric(28,10),
    our_debits       numeric(28,10),
    our_credits      numeric(28,10),
    recorded_by      text           NOT NULL CHECK (length(trim(recorded_by)) > 0),
    recorded_at      timestamptz    NOT NULL DEFAULT now(),

    CONSTRAINT journal_total_is_whole CHECK (
        (stated_debits IS NULL) = (stated_credits IS NULL)
        AND (stated_debits IS NULL) = (our_debits IS NULL)
        AND (stated_debits IS NULL) = (our_credits IS NULL)
    )
);

CREATE INDEX import_reconciliation_entity_idx
    ON import_reconciliation (entity_id, recorded_at DESC);

-- ---------------------------------------------------------------------------
-- One comparison inside it: the stated balances, or one statement the source printed.
-- ---------------------------------------------------------------------------
CREATE TABLE import_reconciliation_comparison (
    id                 uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id          uuid    NOT NULL REFERENCES entity (id),
    reconciliation_id  uuid    NOT NULL REFERENCES import_reconciliation (id),
    -- The stated balances first, then the statements in the order the source printed them.
    position           integer NOT NULL CHECK (position > 0),
    report             text    NOT NULL
                               CHECK (report IN ('balances', 'profit_and_loss', 'balance_sheet')),
    -- The basis the source ran it on, and ours. Null for the stated balances, which carry none.
    their_basis        text,
    our_basis          text,
    -- Accounts that agreed exactly. The ones that did not are lines below.
    agreed             integer NOT NULL CHECK (agreed >= 0),

    UNIQUE (reconciliation_id, report),
    UNIQUE (reconciliation_id, position)
);

-- ---------------------------------------------------------------------------
-- One account that did not simply agree: a divergence with both figures, an account on one
-- side only, or a row the reader could not resolve. Reported rather than dropped, because a line
-- silently missing from a comparison is a difference that reads as agreement.
-- ---------------------------------------------------------------------------
CREATE TABLE import_reconciliation_line (
    id                 uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id          uuid           NOT NULL REFERENCES entity (id),
    comparison_id      uuid           NOT NULL REFERENCES import_reconciliation_comparison (id),
    kind               text           NOT NULL
                                      CHECK (kind IN ('divergence', 'only_ours', 'only_theirs',
                                                      'unmatched')),
    account_code       text           NOT NULL,
    -- Signed as the comparison was made: as a posting for the stated balances, as printed for a
    -- statement. Both present for a divergence, and absent otherwise.
    ours               numeric(28,10),
    theirs             numeric(28,10),

    CONSTRAINT figures_only_for_a_divergence CHECK (
        (kind = 'divergence') = (ours IS NOT NULL AND theirs IS NOT NULL)
        AND (kind = 'divergence' OR (ours IS NULL AND theirs IS NULL))
    )
);

-- Append-only (ADR-0007): a reconciliation is what was shown, and a later one sits beside it.
CREATE TRIGGER import_reconciliation_append_only
    BEFORE UPDATE OR DELETE ON import_reconciliation
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER import_reconciliation_comparison_append_only
    BEFORE UPDATE OR DELETE ON import_reconciliation_comparison
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER import_reconciliation_line_append_only
    BEFORE UPDATE OR DELETE ON import_reconciliation_line
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

ALTER TABLE import_reconciliation            ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_reconciliation_comparison ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_reconciliation_line       ENABLE ROW LEVEL SECURITY;

CREATE POLICY import_reconciliation_entity_isolation ON import_reconciliation
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY import_reconciliation_comparison_entity_isolation
    ON import_reconciliation_comparison
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY import_reconciliation_line_entity_isolation ON import_reconciliation_line
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT
    ON import_reconciliation, import_reconciliation_comparison, import_reconciliation_line
    TO cfokit_app;
