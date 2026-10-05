-- The obligation's carrying account, signed as its posting there (`LED-17`, ADR-0059 § 3).
--
-- A payment matched to an open obligation is settled against the account that carries it, and a
-- settling leg cannot be inferred from an obligation that does not say. That is a change to the
-- ledger's write path.
--
-- The write path finds the account among the raising transaction's own postings — the one
-- account whose postings there sum to the obligation's amount — and refuses an obligation no
-- single account carries. A receivable is a debit, so its amount is positive; a payable is a
-- credit, and negative. A settlement is signed as the obligation it settles.
--
-- Nothing is deployed, so the column takes no default: there is no population of obligations
-- predating it and no honest value to backfill.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

ALTER TABLE obligation ADD COLUMN account_id uuid NOT NULL REFERENCES account (id);
