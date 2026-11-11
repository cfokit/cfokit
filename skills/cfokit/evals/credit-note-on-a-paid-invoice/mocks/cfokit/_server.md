---
type: agent
tools: [record_transaction, outstanding_obligations]
---
You are the CFOKit ledger answering for one company, Acme LLC
(entity_id 6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31). Its accounts include Operating Checking
(a1000000-0000-4000-8000-000000001000), Accounts Receivable
(a1200000-0000-4000-8000-000000001200) and Design Revenue
(a4000000-0000-4000-8000-000000004000). Globex's design invoice, obligation
0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90, was raised on 2026-09-01 for 1000.00 USD on Accounts
Receivable and settled in full on 2026-09-25, so nothing is outstanding on it. Every period
from 2026-10 on is open. Answer with one JSON object and nothing else. Every answer that
succeeds carries "company": {"id": "6f1c2a0e-3b7d-4c11-9a52-8e4d2f0b7c31", "name": "Acme LLC"}.

outstanding_obligations:
- Answer {"ok": true, "company": {...}, "as_of": null, "obligations": []}
  Once a transaction raising an obligation has been accepted in this run, answer instead with
  that obligation: its "amount" and "outstanding" the figure raised, "settled" "0.00", on
  Accounts Receivable, raised by that transaction, "on_account": false.

record_transaction:
- If the postings do not sum to zero, answer
  {"ok": false, "code": "unbalanced_transaction", "message": "postings do not sum to zero for USD"}
- If `raises_obligation`, `settles` or `on_account` is given and `post` is not true, answer
  {"ok": false, "code": "transaction_incomplete", "message": "an obligation or a settlement needs the transaction posted; a draft is not in the books"}
- If both `raises_obligation` and `settles` are given, answer
  {"ok": false, "code": "raising_transaction_settles", "message": "a transaction that raises an obligation settles none; record what it settles and what it raises as two transactions, as a credit note on an invoice partly paid is"}
- If `settles` names 0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90, answer
  {"ok": false, "code": "settlement_exceeds_outstanding", "message": "the settlement of obligation 0b1e7c44-2f6a-4d0e-9c31-5a8d7e2f1b90 is more than is outstanding on it; settle what is outstanding and record the rest as money on account"}
- If `settles` names any other obligation, answer
  {"ok": false, "code": "obligation_not_found", "message": "no obligation <id> in this entity"}
- If `raises_obligation` is given and the postings on Accounts Receivable do not sum to it, answer
  {"ok": false, "code": "obligation_not_carried", "message": "an obligation is carried by the one account whose postings in this transaction sum to its amount, signed as a posting; none, or more than one, does"}
- Otherwise answer {"ok": true, "company": {...}, "transaction_id": "<a new UUID>", "status": "posted" if `post` is true else "draft", "replayed": false}
- An idempotency_key used before in this run returns the earlier answer with "replayed": true.
