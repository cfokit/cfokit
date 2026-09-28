---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-28
decision-makers: [Geoff Scott]
---

# ADR-0046: Account activity is a module, and a statement is recorded only if it accounts for its own balances

**Requirements served:** `BKP-03`, `BKP-19`, `BKP-21`, `NFR-01`.

## Context and Problem Statement

`BKP-03` requires that an operator can supply transactions by uploading a statement file, with no
third-party account and no credentials. The operator is a person with a PDF from their bank, and
the surface they hold it in is a Claude Desktop chat.

That surface decides the transport. [ADR-0041](0041-import-is-parsed-where-the-file-is.md) § 6
measured it: skill code in Desktop runs in a sandbox that cannot reach CFOKit, so the model is the
only bridge between the file and the MCP server that can write. Every figure on the statement is
therefore read out of a document and retyped by a model.

Bank statements do not share a layout. A reader per bank is a reader per bank, and a generic
extractor over PDF text gets columns wrong in ways nothing notices. The model reads the document
natively, and reads it well — and a statement that is read wrongly and booked produces books that
are wrong by exactly the misreading, with nothing in the path able to say so.

Assignment ([ADR-0045](0045-assignment-is-stored-rules.md)) codes a candidate to an account, and
deliberately stores no incoming transactions: whichever module receives account activity produces
the candidates. Two properties of what it received were never settled, and both fail on a
statement. Its idempotency key was derived from the candidate's content, so two identical coffees
on one statement shared a key and the second was replayed as the first — the case
[ADR-0029](0029-mandatory-idempotency-keys.md) names as the reason content must never decide
identity. And a derived transaction's `derived_from` named the payee and nothing that `BKP-19`
could follow back to a source.

## Decision Drivers

* A misread figure must be caught before it reaches the books, and `NFR-01` allows no tolerance.
* The check must not be the model's own arithmetic — agreement with itself is not evidence.
* `BKP-19`: a transaction must name what it came from, for its whole life.
* `BKP-21`: what a source was expected to cover must be recorded, not inferred from what arrived.
* Assignment and the module feeding it may not depend on each other (ADR-0022).
* No layout-specific reader, and nothing that has to be taught about each bank.

## Considered Options

* A module that records the statement as stated, refusing it unless it accounts for its balances
* Send lines straight to assignment, and reconcile the account afterwards
* Parse the PDF in the sandbox with a script, and post what it emits
* Keep statements inside assignment

## Decision Outcome

Chosen option: "A module that records the statement as stated, refusing it unless it accounts for
its balances", because a bank prints its own check on every statement, and using it catches a
misreading at the one point where nothing has yet been written.

> Account activity is `cfokit.activity`, an in-process module. A statement is its account, its
> period, its opening and closing balance and its lines in printed order, all signed as postings
> are. It is stored only if opening plus every line equals closing exactly. Each line's identity
> is its position, and the reference a transaction carries is built from that — never from the
> line's content.

### 1. The statement's own arithmetic is the check

Opening balance plus every line equals closing balance. The bank computed it; the model
transcribed all of it; `prove` compares the two. A misread amount, a dropped line and a line read
twice each break the identity, and a single misreading shows up as exactly its own error — which
is what the refusal reports, because it is the most useful thing a person correcting it can be
told.

This is [ADR-0041](0041-import-is-parsed-where-the-file-is.md)'s § 6 argument applied to a
statement: the transcription risk is real, and it is not silent, because the source states figures
for itself that the transcription must agree with. Two paths through one document.

**Every figure is signed as a posting is signed.** A card's balance owed is negative, a deposit
positive. One convention for every account type is what keeps the proof one line of arithmetic.

### 2. The module is named for the capability, and stores what the source said

`activity`, for account activity (`BKP-`). Not `statements`, which is the artifact of two of the
three producers ADR-0045 § 1 names and not of a feed; not `upload`, which is a mechanism
(ADR-0031). In-process by ADR-0022 § 3's default: it holds no credential and runs on no schedule.

What is stored is the statement as stated, append-only: the lines are the source's claim, and the
transactions coded from them are the ledger's. Keeping them apart is what lets the books be
compared against the statement rather than against themselves.

### 3. A line's identity is its position, and assignment carries it opaquely

The reference is `account-statement:{statement}:{line}`. A candidate carries it as `source_ref`;
assignment derives its idempotency key from it, writes it into `derived_from`, and stores it on the
decision. Assignment never learns what it names, so neither module imports the other — the caller
passes the candidates `record_account_statement` returned to `run_assignment`, unchanged.

The reference also settles two things ADR-0045 left open:

* **A line coded once stays coded.** Running it again reports the decision that coded it rather
  than deciding again under whatever rule is now in force — `BKP-11`, applied to a re-run.
* **An answer supersedes its question.** A line no rule resolved is a one-legged draft under a key
  of its own; once the operator approves a rule, the next run is a different write, and its
  decision names the unanswered one in `supersedes_decision_id`. The fingerprint could not find
  that earlier decision, because it is the content, and the content is what two coffees share.

### 4. A statement's identity is its content, and overlap is refused

The same statement sent twice replays. Its identity is account, period and content digest — which
ADR-0029 forbids for a transaction, and which is right for a statement, because two statements over
the same days of one account are never both genuine. A different statement overlapping a recorded
period is refused with `statement_overlaps`. Telling a line printed on both from two genuinely
identical lines is matching against what the books hold, which is `BKP-13`'s.

### 5. Coverage is the period, and continuity is reported

`BKP-21`'s acceptance is that a skipped period is "detected against the coverage it was expected to
supply". The period is that coverage: a month with no activity is a statement with no lines, and a
month nobody supplied has no row. Each recorded statement reports how it follows the previous one
for its account — contiguous or not, opening where the last one closed or not. Reported rather than
refused, because the first statement follows nothing and a gap is a finding for the operator, not
a reason to lose the month somebody did supply.

### 6. The books are compared with the statement once posted

`account_statement_agreement` sets the statement's opening and closing balances beside the
ledger's own posted balances for the account over the period, read through `account_detail`. The
proof checks the transcription against the statement; this checks the books against both. Drafts
are not in the books (`LED-07`), so a statement whose lines await posting disagrees by exactly what
is waiting.

### Consequences

* Good, because a misread statement is refused whole, before anything is stored or drafted.
* Good, because no bank needs a reader, and no layout needs to be known.
* Good, because two identical lines are two transactions, and a statement sent twice books once.
* Good, because every transaction coded from a statement names its line for life (`BKP-19`).
* Good, because an unanswered line becomes answerable by the ordinary route — approve a rule, run
  the statement again.
* Bad, because the model emits every figure twice: once to record the statement and once, copied
  from the reply, to run assignment. The second copy is not re-proved; a line altered between the
  two is caught only by the agreement after posting.
* Bad, because the proof cannot catch compensating errors — two misreadings that cancel, or a
  payee misread. The amounts it checks are the ones that move the books.
* Bad, because overlap is refused rather than reconciled, so a bank whose statements share a
  boundary day cannot be recorded as printed.
* Neutral, because the agreement compares the account's balance across every commodity it holds,
  which is the printed figure for an account held in one.

### Confirmation

`tests/test_activity.py` holds the proof without infrastructure: worked statements whose expected
outcome is computed by hand in their docstrings, and a property test that perturbing any one line
of any balanced statement by any non-zero amount is refused. `tests/integration/test_account_statements.py`
covers storage, replay, overlap, entity isolation and the whole Desktop path over MCP — recorded,
coded, drafted, posted, agreed — with each transaction's `derived_from` naming a distinct line.
`tests/integration/test_assignment.py` holds the identity rules: two identical lines are two
transactions, a re-run books nothing new, an answer supersedes its question, and a coded line is
not recoded.

`import-linter` holds that `cfokit.activity` and `cfokit.assignment` do not depend on each other,
and that the ledger depends on neither.

Not gated: nothing prevents a caller altering a candidate between `record_account_statement` and
`run_assignment`. The agreement after posting is what reports it.

## Pros and Cons of the Options

### A module that records the statement as stated, refusing it unless it accounts for its balances

* Good, because the check is the source's arithmetic, not the model's.
* Good, because lineage, coverage and identity all have somewhere to live that is not assignment.
* Bad, because it is a fifth module and two more tables.

### Send lines straight to assignment, and reconcile the account afterwards

The smallest change: `run_assignment` already accepts `source_kind: upload`.

* Good, because it needs no new module.
* Bad, because a misreading is found only after it has been drafted, coded and posted, and then
  as a difference with no line attached to it.
* Bad, because there is nowhere for `BKP-21`'s coverage or `BKP-19`'s source to live — assignment
  stores no incoming transactions, by ADR-0045's design.

### Parse the PDF in the sandbox with a script, and post what it emits

* Good, because a script transcribes deterministically.
* Bad, because the sandbox cannot reach CFOKit (ADR-0041 § 6), so the model carries the figures
  anyway and the script buys nothing on the transport.
* Bad, because PDF text extraction needs a library and a layout; a statement's columns are
  positional, and a reader per bank is exactly what `NFR-12` asks us not to ship.

### Keep statements inside assignment

* Good, because the candidate and the line it came from would share a schema.
* Bad, because ADR-0045 § 1 and its follow-on obligations say the opposite in terms: "Whatever
  module receives account activity produces a `Candidate`. It must not be this one."

## Revisit when

* A fetched statement or a feed arrives, which is the second producer of candidates and tests
  whether `source_ref` and the statement shape are neutral or an upload's shape with the labels
  filed off.
* `BKP-13` lands, which is what could accept an overlapping statement by matching its lines to
  what the books already hold.
* An operator's bank prints statements that share a boundary day.
* `BKP-15` lands, which makes the agreement a durable reconciliation rather than a read.
