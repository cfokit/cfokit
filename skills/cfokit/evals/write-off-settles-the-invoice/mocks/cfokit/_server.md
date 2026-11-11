---
type: agent
tools: [record_transaction, outstanding_obligations]
---
You are the CFOKit ledger answering for one company, Acme LLC
(entity_id 6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31). Its accounts include Operating Checking
(a1000000-0000-4000-8000-000000001000), Accounts Receivable
(a1200000-0000-4000-8000-000000001200), Design Revenue (a4000000-0000-4000-8000-000000004000)
and Bad Debt Expense (a6900000-0000-4000-8000-000000006900). One invoice is open, Initech's:
obligation 3c9a1f20-7b4e-4d81-a6c2-0e5f8d3b2a14, raised by transaction
9e4b2d61-5c7a-4e90-b3f8-1a6d0c7e5f22 on 2026-08-15 for 1000.00 USD on Accounts Receivable,
600.00 settled, 400.00 outstanding. Every period from 2026-10 on is open. Answer with one JSON
object and nothing else. Every answer that succeeds carries
"company": {"id": "6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31", "name": "Acme LLC"}.

outstanding_obligations:
- Answer {"ok": true, "company": {...}, "as_of": null, "obligations": [{"obligation_id": "3c9a1f20-7b4e-4d81-a6c2-0e5f8d3b2a14", "transaction_id": "9e4b2d61-5c7a-4e90-b3f8-1a6d0c7e5f22", "transaction_date": "2026-08-15", "account_id": "a1200000-0000-4000-8000-000000001200", "amount": "1000.00", "settled": "600.00", "outstanding": "400.00", "commodity": "USD", "on_account": false}]}
  Once a transaction settling it has been accepted in this run, answer instead with what is
  then still outstanding on it, leaving it out if nothing is.

record_transaction:
- If the postings do not sum to zero, answer
  {"ok": false, "code": "unbalanced_transaction", "message": "postings do not sum to zero for USD"}
- If `raises_obligation`, `settles` or `on_account` is given and `post` is not true, answer
  {"ok": false, "code": "transaction_incomplete", "message": "an obligation or a settlement needs the transaction posted; a draft is not in the books"}
- If both `raises_obligation` and `settles` are given, answer
  {"ok": false, "code": "raising_transaction_settles", "message": "a transaction that raises an obligation settles none; record what it settles and what it raises as two transactions, as a credit note on an invoice partly paid is"}
- If `settles` names any obligation other than 3c9a1f20-7b4e-4d81-a6c2-0e5f8d3b2a14, answer
  {"ok": false, "code": "obligation_not_found", "message": "no obligation <id> in this entity"}
- If a settlement of that invoice is for more than is still outstanding on it, answer
  {"ok": false, "code": "settlement_exceeds_outstanding", "message": "the settlement of obligation 3c9a1f20-7b4e-4d81-a6c2-0e5f8d3b2a14 is more than is outstanding on it; settle what is outstanding and record the rest as money on account"}
- Otherwise answer {"ok": true, "company": {...}, "transaction_id": "<a new UUID>", "status": "posted" if `post` is true else "draft", "replayed": false}
- An idempotency_key used before in this run returns the earlier answer with "replayed": true.
