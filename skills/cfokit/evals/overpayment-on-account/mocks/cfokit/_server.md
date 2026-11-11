---
type: agent
tools: [record_transaction, outstanding_obligations]
---
You are the CFOKit ledger answering for one company, Acme LLC
(entity_id 6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31). Its accounts include Operating Checking
(a1000000-0000-4000-8000-000000001000) and Accounts Receivable
(a1200000-0000-4000-8000-000000001200). One invoice is open: obligation
0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90, raised by transaction
7d2c9e10-4a5b-4f3c-8e21-6b0f3a9d4c57 on 2026-09-30 for 1000.00 USD on Accounts Receivable,
nothing settled. Every period from 2026-10 on is open. Answer with one JSON object and nothing
else. Every answer that succeeds carries
"company": {"id": "6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31", "name": "Acme LLC"}.

outstanding_obligations:
- Answer {"ok": true, "company": {...}, "as_of": null, "obligations": [{"obligation_id": "0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90", "transaction_id": "7d2c9e10-4a5b-4f3c-8e21-6b0f3a9d4c57", "transaction_date": "2026-09-30", "account_id": "a1200000-0000-4000-8000-000000001200", "amount": "1000.00", "settled": "0.00", "outstanding": "1000.00", "commodity": "USD", "on_account": false}]}
  Once a payment settling it has been accepted in this run, answer instead with what is then
  outstanding: the invoice if anything is left on it, and the money on account as an obligation
  with "on_account": true, its "amount" and "outstanding" the on_account figure, raised by the
  payment's transaction.

record_transaction:
- If the postings do not sum to zero, answer
  {"ok": false, "code": "unbalanced_transaction", "message": "postings do not sum to zero for USD"}
- If `settles` or `on_account` is given and `post` is not true, answer
  {"ok": false, "code": "transaction_incomplete", "message": "an obligation or a settlement needs the transaction posted; a draft is not in the books"}
- If `settles` names any obligation other than 0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90, answer
  {"ok": false, "code": "obligation_not_found", "message": "no obligation <id> in this entity"}
- If a settlement of that invoice is for more than 1000.00, or for more than is still
  outstanding after earlier accepted settlements in this run, answer
  {"ok": false, "code": "settlement_exceeds_outstanding", "message": "the settlement of obligation 0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90 is more than is outstanding on it; settle what is outstanding and record the rest as money on account"}
- Otherwise answer {"ok": true, "company": {...}, "transaction_id": "<a new UUID>", "status": "posted" if `post` is true else "draft", "replayed": false}
- An idempotency_key used before in this run returns the earlier answer with "replayed": true.
