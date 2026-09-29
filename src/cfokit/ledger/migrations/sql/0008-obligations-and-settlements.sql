-- Obligations and their settlements (`LED-17`, ADR-0037).
--
-- "An obligation and its settlement are recorded as two related events rather than one. An
-- invoice raised in one period and paid in another is recoverable as either, depending on the
-- basis in force."
--
-- **The link is stored, never inferred.** ADR-0037 § 3 calls this the decision's whole
-- substance: the alternative is deriving the relationship from account and transaction type at
-- report time, which is what the incumbents do and is observably unreliable — a journal entry
-- or a check touching receivables still lands in a cash-basis report there. Storing the link
-- makes that failure impossible rather than rare.
--
-- **An obligation is marked, not guessed.** Without a record saying so, an unsettled invoice
-- and an ordinary cash sale look the same to a cash view: both credit income. Which of them is
-- recognized depends on a fact about the event, and a fact has to be recorded.

CREATE TABLE obligation (
    id             uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id      uuid           NOT NULL REFERENCES entity (id),
    -- The transaction that raised it. An issued invoice credits income and debits receivables
    -- at issue (`AR-03`), whatever basis the entity declared (ADR-0037 § 1).
    transaction_id uuid           NOT NULL REFERENCES ledger_transaction (id),
    amount         numeric(28,10) NOT NULL CHECK (amount <> 0),
    commodity      text           NOT NULL,
    created_at     timestamptz    NOT NULL DEFAULT now(),
    -- One transaction raises at most one obligation. Two would make "how much is outstanding"
    -- ambiguous without a rule nobody has written down.
    UNIQUE (transaction_id)
);

CREATE TABLE settlement (
    id             uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id      uuid           NOT NULL REFERENCES entity (id),
    obligation_id  uuid           NOT NULL REFERENCES obligation (id),
    -- The transaction that settled it. `AR-12`: a payment applies to one or more invoices, and
    -- an invoice is settled by more than one payment, so this is many-to-many by construction.
    transaction_id uuid           NOT NULL REFERENCES ledger_transaction (id),
    amount         numeric(28,10) NOT NULL CHECK (amount <> 0),
    commodity      text           NOT NULL,
    created_at     timestamptz    NOT NULL DEFAULT now(),
    -- One transaction settles one obligation once. Settling the same pair twice in one payment
    -- is two rows that should have been one, and the amounts would double.
    UNIQUE (obligation_id, transaction_id)
);

-- Outstanding is obligation.amount less what has been applied to it, so this is the join every
-- receivables question makes.
CREATE INDEX settlement_by_obligation_idx ON settlement (entity_id, obligation_id);
CREATE INDEX obligation_by_transaction_idx ON obligation (entity_id, transaction_id);

-- ---------------------------------------------------------------------------
-- Both are financial records: append-only, like everything else (ADR-0007).
-- ---------------------------------------------------------------------------
CREATE FUNCTION link_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'append_only_violated: %s rows are never changed or removed (id %)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER obligation_append_only
    BEFORE UPDATE OR DELETE ON obligation
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER settlement_append_only
    BEFORE UPDATE OR DELETE ON settlement
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

-- ---------------------------------------------------------------------------
-- Entity isolation, as for every other tenant table (ADR-0003).
-- ---------------------------------------------------------------------------
ALTER TABLE obligation ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlement ENABLE ROW LEVEL SECURITY;

CREATE POLICY obligation_entity_isolation ON obligation
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY settlement_entity_isolation ON settlement
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT ON obligation, settlement TO cfokit_app;
