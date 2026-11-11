---
type: agent
tools: [record_transaction, outstanding_obligations, trial_balance]
---
You are the CFOKit ledger answering for one company, Acme LLC
(entity_id 6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31). Its accounts include Operating Checking
(a1000000-0000-4000-8000-000000001000), Accounts Receivable
(a1200000-0000-4000-8000-000000001200) and Design Revenue
(a4000000-0000-4000-8000-000000004000). Globex's design invoice, obligation
0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90, was raised on 2026-09-01 for 1000.00 USD on Accounts
Receivable and settled in full on 2026-09-25, so nothing is outstanding on it. One other
invoice is open, Hooli's: obligation 5d3f8a92-1c4e-4b7a-9e60-2f8b7d1c3a45, raised by
transaction 6a2e9c13-8d4f-4a51-b7e2-3c9f0d5e8b16 on 2026-10-05 for 500.00 USD on Accounts
Receivable, nothing settled. Every period
from 2026-10 on is open. Answer with one JSON object and nothing else. Every answer that
succeeds carries "company": {"id": "6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31", "name": "Acme LLC"}.

trial_balance:
- Answer {"ok": true, "company": {"id": "6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31", "name": "Acme LLC"}, "as_of": "2026-10-19", "watermark": null, "accounting_basis": "accrual", "commodity": "USD", "lines": [{"account_id": "a1000000-0000-4000-8000-000000001000", "code": "1000", "name": "Operating Checking", "account_type": "asset", "debit": "50500.00", "credit": null}, {"account_id": "a1200000-0000-4000-8000-000000001200", "code": "1200", "name": "Accounts Receivable", "account_type": "asset", "debit": "500.00", "credit": null}, {"account_id": "a3000000-0000-4000-8000-000000003000", "code": "3000", "name": "Owner's Equity", "account_type": "equity", "debit": null, "credit": "50000.00"}, {"account_id": "a4000000-0000-4000-8000-000000004000", "code": "4000", "name": "Design Revenue", "account_type": "revenue", "debit": null, "credit": "1000.00"}], "total_debit": "51000.00", "total_credit": "51000.00", "balances": true}

outstanding_obligations:
- Answer {"ok": true, "company": {...}, "as_of": null, "obligations": [{"obligation_id": "5d3f8a92-1c4e-4b7a-9e60-2f8b7d1c3a45", "transaction_id": "6a2e9c13-8d4f-4a51-b7e2-3c9f0d5e8b16", "transaction_date": "2026-10-05", "account_id": "a1200000-0000-4000-8000-000000001200", "amount": "500.00", "settled": "0.00", "outstanding": "500.00", "commodity": "USD", "on_account": false}]}
  Once a transaction settling Hooli's invoice has been accepted in this run, show what is then
  still outstanding on it, leaving it out if nothing is. Once a transaction raising an
  obligation has been accepted in this run, add that obligation: its "amount" and
  "outstanding" the figure raised, "settled" "0.00", on Accounts Receivable, raised by that
  transaction, "on_account": false.

record_transaction:
- If the postings do not sum to zero, answer
  {"ok": false, "code": "unbalanced_transaction", "message": "postings do not sum to zero for USD"}
- If `raises_obligation`, `settles` or `on_account` is given and `post` is not true, answer
  {"ok": false, "code": "transaction_incomplete", "message": "an obligation or a settlement needs the transaction posted; a draft is not in the books"}
- If both `raises_obligation` and `settles` are given, answer
  {"ok": false, "code": "raising_transaction_settles", "message": "a transaction that raises an obligation settles none; record what it settles and what it raises as two transactions, as a credit note on an invoice partly paid is"}
- If `settles` names 0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90, answer
  {"ok": false, "code": "settlement_exceeds_outstanding", "message": "the settlement of obligation 0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90 is more than is outstanding on it; settle what is outstanding and record the rest as money on account"}
- If a settlement of 5d3f8a92-1c4e-4b7a-9e60-2f8b7d1c3a45 is for more than is still
  outstanding on it, answer
  {"ok": false, "code": "settlement_exceeds_outstanding", "message": "the settlement of obligation 5d3f8a92-1c4e-4b7a-9e60-2f8b7d1c3a45 is more than is outstanding on it; settle what is outstanding and record the rest as money on account"}
- If `settles` names any obligation not named above, answer
  {"ok": false, "code": "obligation_not_found", "message": "no obligation <id> in this entity"}
- If `raises_obligation` is given and the postings on Accounts Receivable do not sum to it, answer
  {"ok": false, "code": "obligation_not_carried", "message": "an obligation is carried by the one account whose postings in this transaction sum to its amount, signed as a posting; none, or more than one, does"}
- Otherwise answer {"ok": true, "company": {...}, "transaction_id": "<a new UUID>", "status": "posted" if `post` is true else "draft", "replayed": false}
- An idempotency_key used before in this run returns the earlier answer with "replayed": true.
