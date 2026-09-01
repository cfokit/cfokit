---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0007: Records become immutable at posting; corrections are reversing entries

**Requirements served:** `LED-07`, `LED-08`, `NFR-02`.

## Context and Problem Statement

CFOKit's value proposition is that the books are correct and defensible. That makes the
mutability of a financial record a product decision, not an implementation detail.

**Append-only comes from double-entry bookkeeping itself**, where the professional standard is
to correct an error by *recording more data*, never by erasing history — an auditor must be able
to see the original error in order to rule out fraud, and altering records can lead a tax
authority to reject an accounting record entirely. It is not a Beancount inheritance and not a
legacy convention: a Beancount ledger is a plain-text file its owner edits freely, and whatever
immutability such a ledger has comes from putting it in git.

**The market splits by segment, not by era.** This is the fact that matters most, because it
shows the choice is about audience rather than technology.

| | Posted records | Correction path | Guard |
|---|---|---|---|
| NetSuite, Sage Intacct, Dynamics BC | Immutable | Reverse. Intacct requires reopening the books to touch a closed period | Structural |
| QuickBooks Online, Xero | Editable | Edit in place | Always-on audit log, plus an *optional* closing date or lock date |

So the enterprise ledgers are already append-only-at-posting. It is the SMB tools that permit
edits, and they do so because their data model allows it and their interface metaphor invites
it — QuickBooks descends from Quicken's checkbook register, where editing a line is the
natural gesture.

Two facts about the SMB guard bear on how much protection it actually provides. QuickBooks'
audit log is retention-limited — commonly reported as two years, with periodic export as the
documented mitigation — so the guarantee expires. And "Close the books" is **off by default**,
meaning the protection most users have is none.

**CFOKit's audiences straddle the split.** Solo founders arrive with SMB expectations and want
to fix a typo. Fractional CFOs arrive with ERP expectations and want immutability.

**Two facts specific to this system push harder than either precedent.**

1. **Ingestion produces uncategorised candidates.** Bank and card feeds deliver transactions
   with no account assigned, and categorising them is the single most common operation in the
   product (BKP-01, BKP-12). The account a posting hits is unambiguously a financial field, so
   a rule of "no `UPDATE` on financial fields" applied from arrival makes routine
   categorisation a three-line reversing entry.
2. **The bookkeeper is an agent, not a person.** Neither QuickBooks nor NetSuite was designed
   for a non-human making most of the entries. An agent that can edit what it already posted
   can quietly revise its own mistakes, and no audit-log retention window makes that
   acceptable.

## Decision Drivers

* The correctness claim must not be contingent on a user's configuration or on their having
  exported a log before it aged out.
* Routine categorisation is the most frequent operation in the product and must not cost a
  reversing entry.
* An agent making entries at machine volume must not be able to silently revise its own
  mistakes.
* One posture for all entities, so no downstream guarantee needs qualifying by mode.

## Considered Options

* Immutable at posting, with a freely mutable draft state before it
* Editable posted records with an audit log (the QuickBooks and Xero model)
* Immutable from ingestion, with no draft state
* Period close as the only boundary (Xero's lock date)
* Soft delete or tombstones instead of reversing entries
* Event sourcing with rebuilt projections
* Configurable per entity — hard for CFO-managed books, soft for founders

## Decision Outcome

`LED-07` obliges a draft to be freely editable and a posted record to be permanent. `LED-08`
obliges a posted transaction never to be altered or removed, with corrections as reversing entries
that leave both visible. `NFR-02` forbids silent alteration at any layer. Those are the rules and
they are stated in `requirements.md`. This record decides three things they do not settle.

**Enforcement is in the schema, not the service layer.** Posted rows reject `UPDATE` on financial
fields and reject `DELETE` outright, at the database. A rule the application honours is only as
good as every future write path — the bulk import, the backfill, the repair script written at 2am
— and this is the guarantee the product is sold on. It does not get to depend on discipline.

**Financial fields, enumerated, to end the argument that will otherwise recur:** amount, commodity,
account, transaction date, and entity. Those are sealed on a posted record. Everything else is not:
notes, tags and attachments are added as new rows, never rewritten, so nothing is overwritten
anywhere — but adding a note to a posted transaction is not a change to the books and is not
treated as one. This is the same line NetSuite draws between general-ledger-impacting changes and
everything else.

**Agent postings are drafts by default.** The agent proposes; a person's confirmation posts. This
is what makes an agent bookkeeper trustworthy without filling the ledger with its corrected
guesses, and it is the reason the draft state exists at all.

**Period close is a hard boundary.** `LED-11` requires that no posting enter a closed period
except through a recorded reopening. Append-only posting and a hard close answer different
questions — append-only guarantees nothing is destroyed, while a hard close makes entry into a
reported period a deliberate, evidenced act. ADR-0030 holds the reopen model and the reasoning
behind it.

### Consequences

* Good, because the audit guarantee is structural rather than contingent on retention windows
  or opt-in settings.
* Good, because the draft state gives founders the latitude they actually need — room to fix
  things *before* they count — without weakening the posted guarantee.
* Good, because an agent's posted mistakes remain visible, which is the property that makes an
  agent bookkeeper trustworthy at all.
* Bad, because there are two record states and a transition between them. Every write path must
  know which side of the boundary it is on, and getting that wrong is a correctness bug rather
  than a nuisance.
* Bad, because corrections triple the rows involved, and reporting must aggregate across a
  transaction and its reversal.
* Bad, because the agent's mistakes are in the ledger permanently once posted. Draft-by-default
  limits how often that happens; it does not eliminate it.
* Bad, because users arriving from QuickBooks will find CFOKit stricter and will ask for edits.
  The answer is the draft state, and it will not always satisfy them.

### Confirmation

Schema-level enforcement: posted rows reject `UPDATE` on financial fields and reject `DELETE`
outright. A `CLAUDE.md` rule alone is insufficient for a guarantee this load-bearing.

## Pros and Cons of the Options

### Immutable at posting, with a mutable draft state

* Good, because it matches the enterprise ledgers CFO users expect while leaving room for the
  SMB gesture of fixing something before it counts.
* Good, because categorisation happens in draft, so the most frequent operation costs nothing.
* Bad, because the boundary has to be placed correctly and enforced on every write path.

### Editable posted records with an audit log (the QuickBooks and Xero model)

The strongest alternative, and the one CFOKit's largest audience already expects.

* Good, because a typo is one gesture rather than three lines.
* Good, because categorisation needs no special state and no reversal entries clutter a register.
* Good, because it is demonstrably sufficient for millions of businesses.
* Bad, because **the guarantee expires.** With mutable records the audit log is the *only*
  evidence that nothing was silently changed, and QuickBooks' log is retention-limited with
  export as the documented workaround. A correctness property that depends on the user having
  remembered to export a CSV is not a property of the software.
* Bad, because **the default is unprotected.** The closing date is opt-in, so the modal
  QuickBooks user has an editable ledger with a log that ages out. CFOKit cannot ship a weaker
  default than the claim it makes about correctness.
* Bad, because **reviewability does not survive agent-rate mutation.** That model was designed
  for a human bookkeeper making a handful of corrections a month, a volume a person can review.
  An agent processing hundreds of transactions could make hundreds of silent revisions, and a log
  nobody can read is not a control. This is the one objection that is genuinely new rather than
  inherited — it did not apply before the bookkeeper was software.

  Stated carefully, because the overreaching version is checkably false: QuickBooks and Xero *do*
  record edits, and their audit logs cannot be disabled. The claim is not that edits are invisible
  elsewhere. It is that a correction here is an entry in the books rather than an event in a
  retention-limited log, and that the difference matters at agent volume rather than human volume.

### Immutable from ingestion, with no draft state

* Good, because it is the simplest possible rule: one state, no boundary to place wrongly, no
  possibility of a write path checking the wrong side of it.
* Bad, because categorising an incoming bank-feed transaction would require a reversing entry,
  tripling the row count on the most frequent operation in the product and burying genuine
  corrections in the noise of routine categorisation.
* Bad, because there is no way to carve out categorisation as an exception — the account is a
  financial field, so the exception would swallow the rule.

### Period close as the only boundary (Xero's lock date)

* Good, because it gives users a full open period in which to work freely, which is what they
  expect, and it needs no second record state.
* Bad, because it makes auditability contingent on somebody remembering to close a period.
* Bad, because within the open period an agent could silently rewrite its own mistakes — the one
  thing that must remain visible.
* Bad, because any statement shared mid-period is provisional until close, which is the version
  problem this decision exists to prevent.

### Soft delete or tombstones instead of reversing entries

* Good, because queries stay simple — filter on a flag — and it is a familiar pattern outside
  accounting.
* Bad, because a tombstoned transaction has no reversing posting, so a trial balance taken
  between the deletion and any compensating entry does not tie.
* Bad, because it is not a recognised accounting correction: an auditor sees an entry that
  vanished rather than a documented reversal, which is the appearance the professional standard
  exists to avoid.

### Event sourcing with rebuilt projections

* Good, because it maximises fidelity and would make historical report reproduction natural.
* Bad, because it is redundant. In a double-entry system the postings **are** the event log;
  layering a separate event stream over an already append-only ledger duplicates it.
* Bad, because rebuilding projections pulls toward materialised balances, whereas balances are
  derived by aggregation over postings (ADR-0003).

### Configurable per entity — hard for CFO-managed books, soft for founders

Genuinely tempting, because it matches the audience split exactly.

* Good, because each user gets the posture they expect.
* Bad, because it makes the correctness story conditional. Every downstream guarantee —
  reproducible statements, audit defence, "the agent cannot rewrite your books" — would have to
  be qualified by which mode an entity is in, and support answers would begin with "it depends".
* Bad, because the draft state already gives founders the latitude they actually need.

## More Information

**Follow-on obligations.**

- Schema-level enforcement of immutability on posted rows.
- The zero-sum constraint (ADR-0006) applies **at posting**, not at draft creation — a draft is
  permitted to be unbalanced while someone is still working on it.
- Draft records need either separate storage or a posted marker whose transition is one-way and
  constrained.
- Reversing a posted entry must be a first-class operation, not something a user assembles by
  hand, or the policy will be worked around.
- Reports must be renderable against a past ledger version; that is what makes an issued
  statement reproducible and is what closes the report-versioning question.
- Period close needs a representation, and closing writes an `audit_log` row like any other
  state change.
- Correction mechanics stated as requirements in `docs/product/requirements.md`.
- Backdating is settled in ADR-0013 and ADR-0030. A posting dated into a period already reported
  on changes an already-issued statement, so it is surfaced rather than merely recorded, and a
  closed period admits it only through a recorded reopening.

**Reversal cost. High — close to a one-way door.** The schema, every write path, and the
reporting model all assume it. Moving to editable records later would mean abandoning reproducible
historical statements and introducing a retention-managed audit log to replace the guarantee.
Moving the other way, from editable to append-only, is worse still, because existing data would
carry no reversal history. This is the reason the decision is made before the booking engine
rather than discovered during it.

## Revisit when

- Users routinely post and then immediately reverse. That pattern would indicate the
  draft/posted boundary sits in the wrong place — most likely that confirmation is being demanded
  too early — and it is the signal to move the boundary, not to abandon immutability.
- A jurisdiction requires a correction mechanism this forbids.
- An audit or review finds that reversal chains are unreadable in practice, which would be a
  reporting problem to solve rather than grounds to permit edits.

Row count and storage cost are explicitly **not** revisit triggers. More rows is the price, and it
was accepted knowingly.
