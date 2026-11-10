-- Money on account: received or paid ahead of any obligation (`AR-12`, ADR-0080 § 2).
--
-- A payment beyond what it settles, or one settling nothing, leaves money that no invoice or
-- bill takes. The books hold it for the counterparty, as every system does: an obligation owed
-- back, carried by the same account, signed as its posting there. A customer's credit is
-- therefore negative on a receivable, and a deposit with a vendor positive on a payable.
--
-- **The mark is what the cash view reads**, and it is stored rather than inferred. An ordinary
-- obligation waits for its settlements; money on account has already moved, so a cash-basis
-- report recognizes it on receipt, on a line of its own, and takes it off that line again when
-- it is applied or refunded. Inferring which credits on a receivable are payments would make a
-- journal entry to receivables look like one (ADR-0037 § 3).
--
-- Every obligation recorded before this one was raised by an invoice or a bill, so `false` is
-- the true value for each of them rather than a guess.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

ALTER TABLE obligation ADD COLUMN on_account boolean NOT NULL DEFAULT false;
