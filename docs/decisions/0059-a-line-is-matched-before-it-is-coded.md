---
status: "accepted"
kind: "requirement-driven"
date: 2026-10-05
decision-makers: [Geoff Scott]
---

# ADR-0059: An incoming transaction is matched to what the books already hold before any rule codes it, and only a sole exact counterpart is acted on

**Requirements served:** `BKP-13`, `BKP-14`, `AR-13`, `LED-17`.

## Context and Problem Statement

Assignment ([ADR-0045](0045-assignment-is-stored-rules.md)) turns every incoming line into a new
transaction: the line's own account on one leg, the account a rule chose on the other, or a
one-legged draft and a question when no rule resolves it. That is right for a line nothing else
describes, and wrong for three kinds of line that are common in any month:

* **A payment the books already expect.** An issued invoice raised an obligation (`LED-17`); the
  customer's deposit arrives on the bank feed. Coded by a rule to income, it books the revenue a
  second time and leaves the invoice open. `AR-13` requires the deposit to be applied to the invoice
  it settles, and [ADR-0037](0037-accounting-basis-is-a-presentation-property.md) § 3 requires that
  application to be a stored link, never inferred.
* **A transaction entered ahead of the feed.** A person records the rent they paid, a check they
  wrote, or books imported from the previous system cover days a feed then delivers again. `BKP-13`
  requires the line to be matched to that record "rather than creating a duplicate".
* **A transfer between two of the entity's own accounts.** It arrives as two lines — out of
  checking, into savings — or as one, when only one side has a feed. `BKP-14` requires one transfer
  either way, and its acceptance is that total income and total expense are unchanged.

None of these is decidable from the line alone. A rule matches on the line's facts (ADR-0045 § 5);
whether a counterpart exists is a fact about the books at the moment the line arrives. Whatever
decides it has to keep what assignment already guarantees: one recorded fate per line, the same
answer on every run (`BKP-06`), a question rather than a guess where the answer is not determined
(`BKP-12`), and a replay able to fail.

The question also bears on [ADR-0047](0047-an-uploaded-line-is-drafted.md): a line read from an
uploaded document is never posted by the session that read it, and a match must not become a way
round that.

## Decision Drivers

* No duplicate: a movement the books already hold is not booked again.
* Nothing guessed (`BKP-12`, `NFR-16`). Where two records fit equally, no order among them is
  stated, so choosing one is choosing whichever was found first — what `BKP-08` forbids for rules.
* No tolerance. A match with a difference has to put the difference somewhere, and a holding
  account is what `BKP-12` rules out.
* A line's fate is one record, written in the same commit as anything it writes (ADR-0022 § 3), and
  replay re-decides all of it.
* The ledger learns nothing about lines, payees or banks (ADR-0022 § 1).
* No caller can skip the check, because the caller that skips it is the one that duplicates.

## Considered Options

* Assignment searches the books for a counterpart before consulting any rule
* A separate module matches lines before the caller passes the rest to assignment
* Matching as a kind of rule, ordered among the others
* Suggest matches, and a person confirms each one
* Matching in the ledger

## Decision Outcome

Chosen option: "Assignment searches the books for a counterpart before consulting any rule",
because a line's fate is one decision and the counterpart is what decides it.

> Every line `apply_rules` receives is first searched against the books for a counterpart, in the
> same transaction as the write. Exactly one counterpart: the line is matched to it and no rule is
> consulted — unless the line was uploaded and the counterpart is an obligation, which a person
> confirms. Two or more: the line is a question. None: the rules decide, as they do now. The
> facts compared are exact, the windows are constants of the pure engine, and what the search saw
> is stored on the decision.

### 1. In assignment, and before the rules

`BKP-06` names the capability "assignment of an incoming transaction", and deciding that a line *is*
an existing record is assigning it — so the search is assignment's, not a sixth capability's.
`matching` would be a mechanism name (ADR-0031); rules match too. The ledger supplies the reads,
as it already does for the rule set, and learns nothing about what a line is.

It runs first because a rule cannot see the books, and the line a counterpart explains is often one
a rule would happily code: the customer's deposit to income, the transfer's outbound side to
whatever account its payee resembles. A counterpart, where there is one, is better evidence than a
pattern.

The search and the write are one transaction under the entity's lock (ADR-0011), so two runs cannot
claim one counterpart. A unique index on the decision's transaction and the line's account is the
second enforcement point: **a leg is claimed by at most one line**.

### 2. What counts as a counterpart

Three kinds, each compared on the line's account, amount and commodity, exactly. A line and its
counterpart are signed as postings are, so a deposit of 1,200.00 meets a receivable of 1,200.00.

| Kind | The record | Date |
|---|---|---|
| **An open obligation** | An obligation (`LED-17`) whose outstanding amount equals the line's, in its commodity | The line is not dated before the obligation arose |
| **A recorded transaction** | A transaction, draft or posted, with a posting on the line's account equal to the line's amount, which no line has claimed and which is neither reversed nor a reversal. Covers an entry made by hand, an imported one, and a transfer coded from its other side | Within 30 days either side of the line |
| **The other side of a transfer** | Another line's one-legged draft, still unanswered, on a different account of the entity, for exactly the negated amount | Within 7 days either side of the line |

The windows differ because the evidence does. A check clears weeks after it was entered, and an
exact amount on one account, unclaimed, is strong evidence across a month; once each of a series of
equal monthly payments is claimed, it drops out, so recurring amounts do not collide. Two unexplained
lines on two accounts are weaker evidence, and a transfer between banks settles within days. Both
windows are part of the matcher's semantics, covered by `EVALUATOR_VERSION`, so changing either needs
a record (ADR-0045).

Partial payments, one deposit across several invoices, and amounts that differ are not counterparts.
`AR-12` represents all of them, through the ledger's ordinary settlement path; once a person has
recorded that, the line finds it as a recorded transaction.

A leg already claimed by a line is never a counterpart. Identical facts are not an identical
movement — two coffees on one statement are two lines (ADR-0029) — so `candidate_fingerprint`, which
was stored for this question, is not what answers it. It is removed.

### 3. What a match produces

* **An open obligation** — one new transaction: the line's account on one leg, the obligation's
  account on the other, settling the obligation for the line's amount. This is the link `AR-13` and
  ADR-0037 § 3 require, recorded where the payment is. The obligation records the account that
  carries it, signed as its posting there, because a settling leg cannot be inferred from an
  obligation that does not say.
* **A recorded transaction** — nothing new in the books. The decision names the existing
  transaction, which is the line's link to it; `derived_from` stays as the entry was written,
  because the entry was not derived from the line and is never altered. `RPT-08`'s trail runs from
  the posting through the decision to the line. A matched draft stays a draft for whoever owns it.
  An uploaded line is matched this way too: nothing is written to the books, so there is nothing
  for a person to authorize.
* **The other side of a transfer** — one new transaction with both lines' legs, and two decisions:
  the arriving line's, and the earlier line's, superseding its unanswered one and closing its
  question. The earlier one-legged draft stays unposted, as every answered question's draft does.
  If either line was uploaded, the transfer is a draft a person posts, as ADR-0047 makes every
  uploaded line's transaction — a two-legged draft needs nothing the ledger lacks, so it takes no
  rule of its own.

A transaction a match writes carries `actor_class` `rule` — deterministic and re-derivable, which is
what that class records (ADR-0033 § 3) — and its legs name no rule version, because none chose them.

**An uploaded line never settles an obligation by itself.** A settlement needs its transaction
posted, and ADR-0047 forbids posting what the session that read the document asked for. So an
uploaded line whose sole counterpart is an open obligation is a question, recorded as `proposed`
with the obligation named: the same `unresolved_transaction` notification and questions page as
any other (§ 4). A person confirming it is their own act
([ADR-0042](0042-person-only-acts-are-a-capability.md)), and writes the settling transaction
posted, with its settlement, in one transaction. That satisfies `PLT-23`, because a person — not the
session that read the document — decided the payment happened. A feed line matching an obligation
settles it automatically, posted.

### 4. Ambiguity is a question, answered by a person

Two or more counterparts, of any kinds together, and the line is a question, recorded as
`ambiguous`: a one-legged draft the
ledger cannot post, as an unresolved line is, and a decision recording every counterpart found. It
raises the same notification an unresolved line does — class `unresolved_transaction`, subject the
line's reference, linked to the questions page — because to the person it is the same question:
what is this line? A `proposed` line is the same question with one candidate answer.

A person answers any question about a line by naming one counterpart, or, for an ambiguous or
proposed one, none, after which the rules decide. The choice is held to the same exact facts as the
search but not to its windows, so a check that cleared after six weeks is answered by choosing the
entry. It is a person's own act (ADR-0042), as approving a rule is, because nothing but the person
stands behind it. A transaction it writes is posted, unless it pairs a transfer with an uploaded
line, which § 3 drafts. The decision it writes supersedes the question
and closes the notification (ADR-0056 § 1), as does a later run that finds exactly one counterpart.

`BKP-09` is not engaged by an automatic match. What it asks a person to approve is a coding pattern,
and a counterpart is not a pattern: it is a record somebody with authority already made.

### 5. Replay covers the search

The decision's `outcome` gains `matched`, `proposed` and `ambiguous` beside `assigned` and
`unmatched`. Every decision stores the counterparts found — one for `matched` and `proposed`, all of
them for `ambiguous`, none otherwise — and a sha256 over them, beside the rule-set digest it already stores.

Everything the search reads is append-only and timestamped — obligations, settlements, postings,
reversals, and the decisions that claim legs — so the counterparts as they stood at `decided_at`
are a reconstruction, as the rule set is (ADR-0045 § 2). Replay rebuilds them, compares the digest,
and where it agrees re-decides the whole fate: search, then rules. Where it does not, the decision
is counted as the books having changed, not compared. That is what makes `BKP-06`'s acceptance able
to catch the failure this record exists for: a line booked by a rule while a counterpart sat in the
books.

A decision written on a person's choice records the person and is not re-decided, because a choice
is not a function of the inputs. Replay counts those separately.

### Consequences

* Good, because an expected payment, an entry made ahead of the feed and a transfer's second side
  each reach the books once.
* Good, because a transfer's first unexplained side is answered by its second arriving, with no
  question left behind.
* Good, because nothing is chosen among equals; a tie reaches a person with every candidate listed.
* Good, because replay checks the search as well as the rules, so a duplicate is a replay
  divergence rather than an invisible figure.
* Bad, because a counterpart outside its window is not found, and if a rule then codes the line the
  movement is in the books twice. The statement agreement ([ADR-0046](0046-a-statement-proves-itself.md)
  § 6) reports the difference; nothing prevents it.
* Bad, because two unrelated lines of mirrored amounts on two accounts within a week are booked as a
  transfer, unasked. Total income and expense are still right; the gross figures are not.
* Bad, because every uploaded payment of an invoice is a question, even when it has exactly one
  counterpart. That is ADR-0047's cost, paid once per payment rather than once per line.
* Bad, because the ledger changes: an obligation records the account that carries it. It is a
  change to the write path, which `CLAUDE.md` reserves for human review.
* Neutral, because one movement delivered through two sources, under two references, is two lines;
  a claimed leg is never a counterpart.

### Confirmation

`tests/test_assignment_engine.py` holds the matcher without infrastructure: the outcome is invariant
to the order counterparts arrive in; one counterpart matches, two are `ambiguous`, none fall through
to the rules; and each window's boundary is inclusive, with worked cases computed by hand from the
table in § 2 rather than by running the engine (ADR-0036 § 5).

`tests/integration/test_assignment.py` holds the rest against real books: a deposit equal to an open
obligation settles it and no income is booked; a line equal to a hand-entered entry writes no
transaction; two mirrored feed lines leave total income and total expense unchanged — `BKP-14`'s
acceptance executed — and close the first line's question; two equal counterparts raise one
`unresolved_transaction` notification per holder and post nothing; a second line cannot claim a
claimed leg; and replay re-decides matched lines and reports a divergence when a counterpart is
removed from what the search sees.

`tests/integration/test_account_statements.py` asserts, over MCP, that an uploaded line equal to an
open obligation raises an `unresolved_transaction` question naming the obligation and writes no
settlement; that a delegated agent cannot confirm it; and that a person confirming it posts the
settling transaction and settles the obligation in one commit.

The unique index on a decision's transaction and the line's account is the schema's half of "a leg
is claimed once". Not gated: nothing stops a change to either window except `EVALUATOR_VERSION`,
which rests on discipline as ADR-0045 says.

## Pros and Cons of the Options

### Assignment searches the books for a counterpart before consulting any rule

* Good, because one decision explains each line, whatever became of it.
* Good, because no caller can reach the rules without the search having run.
* Bad, because assignment now reads the books as well as the line, and its decisions grow a second
  digest.

### A separate module matches lines before the caller passes the rest to assignment

Attractive, because assignment would stay a function of the line and the rule set alone.

* Good, because ADR-0045's decision shape would be untouched.
* Bad, because the two modules may not depend on each other (ADR-0022), so the hand-off is the
  caller's, and the caller that skips it is the one that books the duplicate.
* Bad, because a line's fate would be two records in two modules, and replay of either alone could
  not tell whether a rule should have run at all.

### Matching as a kind of rule, ordered among the others

One mechanism, with `BKP-08`'s order already built.

* Good, because the operator would see matching in the same list as every other rule.
* Bad, because a rule's outcome is pinned by the rule set and the line; a match depends on the
  books, so the rule-set digest would no longer say whether a decision should reproduce.
* Bad, because no precedence can choose between two equal counterparts, which is the case that most
  needs a person.
* Bad, because a person would be asked to approve "settle open invoices", which is not a pattern
  anyone holds an opinion about.

### Suggest matches, and a person confirms each one

What the incumbents do, and familiar to every bookkeeper.

* Good, because no match ever happens unseen.
* Bad, because a sole exact counterpart on the line's own account leaves the person nothing to
  decide, and asking per transaction is the recurring cost `BKP-09` exists to remove.
* Bad, because an uploaded line already reaches a person — through ADR-0047's draft, or as a
  question where it would settle an obligation — so the safety it adds is where safety is already
  present.

### Matching in the ledger

* Good, because obligations and postings are the ledger's, so the search would read its own tables.
* Bad, because the ledger would learn what an incoming line is, which is ADR-0022's own test for the
  boundary having moved wrongly.

## More Information

**Reversal cost.** Medium. The search and the new outcomes are additive in assignment and could be
removed, but settlements written by matches and the obligation's account are in the ledger, and books matched under this decision would carry its links for life.

Related: [ADR-0045](0045-assignment-is-stored-rules.md), which reserved the outcome set for this;
[ADR-0046](0046-a-statement-proves-itself.md) § 4, which left the line printed twice to this
record; [ADR-0037](0037-accounting-basis-is-a-presentation-property.md) § 3, the stored link;
[ADR-0056](0056-a-notification-is-open-until-answered-or-dismissed.md), how a question closes.

## Revisit when

* A feed arrives, which is the first test of the windows against real bank dates rather than
  reasoning about them.
* Operators answer ambiguous matches by choosing the oldest counterpart nearly every time, which is
  the case for stating an order.
* Accounts payable enters scope, which makes bills obligations and doubles the obligation kind's
  traffic.
* A transfer is booked between two lines that were not one, which is the case for asking before
  pairing two unexplained lines.
