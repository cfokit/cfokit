-- Account statements, as the source stated them (`BKP-03`, `BKP-19`, `BKP-21`, ADR-0046).
--
-- **These tables are not the ledger's.** `cfokit.activity` owns them. They live in this schema
-- and this sequence for the reason 0010 and 0012 give: a module is a sibling in the same
-- deployable, sharing one database (ADR-0022 § 3, ADR-0023).
--
-- **What is stored is what the statement said, not what the books did with it.** A line here is
-- the source's claim; the transaction coded from it is the ledger's, and names this line in its
-- `derived_from`. Keeping the two apart is what lets the books be compared against the statement
-- rather than against themselves.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- One statement: the account it covers, the period, and the balances it states.
--
-- **The period is `BKP-21`'s coverage.** A statement says what it was expected to cover as well
-- as what it delivered, so a month with no activity is a statement with no lines — which is
-- distinguishable from a month nobody supplied, because the second has no row here at all.
-- ---------------------------------------------------------------------------
CREATE TABLE account_statement (
    id               uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid           NOT NULL REFERENCES entity (id),
    account_id       uuid           NOT NULL REFERENCES account (id),
    -- Both inclusive, as a bank prints them.
    period_start     date           NOT NULL,
    period_end       date           NOT NULL,
    -- Signed as a posting is signed: positive is a debit. A card statement's balance owed is a
    -- credit, so it is negative here. One convention for every figure is what lets the proof
    -- below be one line of arithmetic rather than a case per account type.
    opening_balance  numeric(28,10) NOT NULL,
    closing_balance  numeric(28,10) NOT NULL,
    commodity        text           NOT NULL,
    -- How the statement reached us. Only an upload today; a fetched statement is the second
    -- producer ADR-0045 names, and a value nobody writes is one every reader has to ask about.
    source_kind      text           NOT NULL CHECK (source_kind IN ('upload')),
    -- sha256 over a canonical rendering of everything above and every line. The same statement
    -- sent twice is a replay; a different one for the same period is a refusal. Without this
    -- the two are indistinguishable.
    content_digest   text           NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    recorded_by      text           NOT NULL CHECK (length(trim(recorded_by)) > 0),
    recorded_at      timestamptz    NOT NULL DEFAULT now(),

    CONSTRAINT period_is_ordered CHECK (period_start <= period_end)
);

-- The overlap check and the predecessor lookup both walk one account's statements by date.
CREATE INDEX account_statement_account_period_idx
    ON account_statement (entity_id, account_id, period_start, period_end);

-- ---------------------------------------------------------------------------
-- One line, as printed.
--
-- **`BKP-20`: none of this was authored by the organisation.** The payee and description are a
-- third party's text, and a model read them out of a document. They are stored as data and
-- never interpreted as anything else; the table they sit in is the marking, and `source_kind`
-- on the statement says how they arrived.
-- ---------------------------------------------------------------------------
CREATE TABLE account_statement_line (
    id               uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid           NOT NULL REFERENCES entity (id),
    statement_id     uuid           NOT NULL REFERENCES account_statement (id),
    -- Position on the statement, from 1. **This is the line's identity**, and the reason two
    -- identical coffees are two lines: the source reference a transaction carries is built from
    -- it, never from the line's content (ADR-0029).
    line             integer        NOT NULL CHECK (line > 0),
    transaction_date date           NOT NULL,
    payee            text           NOT NULL CHECK (length(trim(payee)) > 0),
    description      text,
    -- Signed as a posting is signed. Never zero: a line that moves nothing is not a line.
    amount           numeric(28,10) NOT NULL CHECK (amount <> 0),

    UNIQUE (statement_id, line)
);

-- ---------------------------------------------------------------------------
-- Append-only (ADR-0007). A statement that was wrong is not corrected here — the bank issued
-- what it issued — and a line that was misread is caught by the proof before it is stored.
-- ---------------------------------------------------------------------------
CREATE TRIGGER account_statement_append_only
    BEFORE UPDATE OR DELETE ON account_statement
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER account_statement_line_append_only
    BEFORE UPDATE OR DELETE ON account_statement_line
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

ALTER TABLE account_statement      ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_statement_line ENABLE ROW LEVEL SECURITY;

CREATE POLICY account_statement_entity_isolation ON account_statement
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY account_statement_line_entity_isolation ON account_statement_line
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT ON account_statement, account_statement_line TO cfokit_app;
