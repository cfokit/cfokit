-- Opening balances (`LED-10`).
--
-- "An entity's books can be opened with balances carried in from before CFOKit held them.
-- Opening balances are ordinary postings, balance to zero against a single identified equity
-- account, and are identifiable as opening balances."
--
-- `entry_kind = 'opening'` already exists on ledger_transaction from 0001 and is what makes
-- them identifiable. What was missing is the equity account they balance against.
--
-- Separate from retained earnings (0006), which they are often confused with. Retained
-- earnings holds what the business has earned and `LED-12` closes into it every year. This
-- holds the counterweight to balances that arrived from a system CFOKit never saw, and it is
-- meaningful precisely because it should be reconciled away rather than grown.

ALTER TABLE entity ADD COLUMN opening_balance_account_id uuid REFERENCES account (id);
