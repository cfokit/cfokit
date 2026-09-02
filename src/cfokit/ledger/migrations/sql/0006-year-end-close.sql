-- Fiscal year-end close (`LED-12`, ADR-0027).
--
-- "At fiscal year end, income and expense balances are closed to retained earnings so the new
-- year opens with them at zero. The closing entries are ordinary postings and are identifiable
-- as such."
--
-- `entry_kind = 'closing'` already exists on ledger_transaction from 0001 and is what makes
-- them identifiable. What was missing is *where* they close to: `LED-12` names retained
-- earnings, which is a particular account in this entity's own chart.
--
-- Nullable, because an entity is created before it has any accounts (`IAM-06`) and cannot name
-- one until it does. A year close refuses while it is unset rather than guessing.

ALTER TABLE entity ADD COLUMN retained_earnings_account_id uuid REFERENCES account (id);

-- ADR-0027's staleness query: every posted transaction in a fiscal year, by when it was
-- recorded rather than when it occurred. A closing entry is stale when something in its year
-- was recorded after it, which is a query rather than a flag anyone maintains.
CREATE INDEX ledger_transaction_kind_idx
    ON ledger_transaction (entity_id, entry_kind, transaction_date);
