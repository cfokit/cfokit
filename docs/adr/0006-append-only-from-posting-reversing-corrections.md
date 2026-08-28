# ADR-0006: Records become immutable at posting; corrections are reversing entries

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

## Context

CFOKit's value proposition is that the books are correct and defensible. That makes the
mutability of a financial record a product decision, not an implementation detail.

**The provenance of "append-only" needed checking, and it is not what it appeared to be.**
It does not come from Beancount: a Beancount ledger is a plain-text file its owner edits
freely, and whatever immutability such a ledger has comes from putting it in git, not from
Beancount's model. Nor is it a legacy convention. It comes from double-entry bookkeeping
itself, where the professional standard is to correct an error by *recording more data*, never
by erasing history — an auditor must be able to see the original error in order to rule out
fraud, and altering records can lead a tax authority to reject an accounting record entirely.

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
   product (REQ-B1, REQ-C1). The account a posting hits is unambiguously a financial field, so
   a rule of "no `UPDATE` on financial fields" applied from arrival makes routine
   categorisation a three-line reversing entry.
2. **The bookkeeper is an agent, not a person.** Neither QuickBooks nor NetSuite was designed
   for a non-human making most of the entries. An agent that can edit what it already posted
   can quietly revise its own mistakes, and no audit-log retention window makes that
   acceptable.

## Decision

**Posting is the point of no return.**

- A **draft** record is freely mutable. Assigning an account, fixing an amount, correcting a
  date, and splitting a transaction are ordinary edits with no reversal.
- A **posted** record is immutable. No `UPDATE` to any financial field, no `DELETE`, ever.
  Corrections are new reversing entries.
- **Annotations are append-only rather than mutable.** Notes, tags, and attachments are added
  as new rows and never rewritten, so nothing anywhere in a posted transaction is overwritten.

**Financial fields**, for the avoidance of the argument that will otherwise recur: amount,
commodity, account, transaction date, and entity. Changing any of them on a posted record is
forbidden, in the schema and in the repository layer, not merely by convention.

**Period close is a second and deliberately weaker boundary.** It is advisory: it marks a
period as reviewed and is a workflow signal, not the mechanism that guarantees auditability.
Append-only posting already provides that guarantee, which is precisely why close does not
need to be hard. See ADR-0013 for whether backdating into a closed period is permitted.

**Agent postings are drafts by default.** The agent proposes; confirmation posts. This keeps
the trust property without filling the ledger with the agent's corrected guesses.

## Alternatives rejected

### Editable posted records with an audit log (the QuickBooks and Xero model)

The strongest alternative, and the one CFOKit's largest audience already expects. A typo is
one gesture rather than three lines; categorisation needs no special state; there are no
reversal entries cluttering a register; and the audit log preserves history for anyone who
looks. It is also, demonstrably, sufficient for millions of businesses.

Rejected on three counts.

1. **The guarantee expires.** With mutable records the audit log is the *only* evidence that
   nothing was silently changed, and QuickBooks' log is retention-limited with export as the
   documented workaround. A correctness property that depends on the user having remembered to
   export a CSV is not a property of the software.
2. **The default is unprotected.** The closing date is opt-in, so the modal QuickBooks user
   has an editable ledger with a log that ages out. CFOKit cannot ship a weaker default than
   the claim it makes about correctness.
3. **Reviewability does not survive agent-rate mutation.** The audit-log-as-safety-net model was
   designed for a human bookkeeper making a handful of corrections a month, which is a volume a
   person can review. An agent processing hundreds of transactions could make hundreds of silent
   revisions, and a log nobody can read is not a control. This is the one objection that is
   genuinely new rather than inherited — it did not apply before the bookkeeper was software.

   Stated carefully, because the overreaching version is checkably false: QuickBooks and Xero *do*
   record edits, and their audit logs cannot be disabled. The claim is not that edits are invisible
   elsewhere. It is that a correction here is an entry in the books rather than an event in a
   retention-limited log, and that the difference matters at agent volume rather than human volume.

### Immutable from ingestion, with no draft state

Attractive because it is the simplest possible rule: one state, no boundary to place wrongly,
no possibility of a write path checking the wrong side of it.

Rejected because categorising an incoming bank-feed transaction would require a reversing
entry, tripling the row count on the most frequent operation in the product and burying
genuine corrections in the noise of routine categorisation. There is no way to carve out
categorisation as an exception, because the account is a financial field — the exception would
swallow the rule.

### Period close as the only boundary (Xero's lock date)

Attractive because it gives users a full open period in which to work freely, which is what
they expect, and it needs no second record state.

Rejected because it makes auditability contingent on somebody remembering to close a period,
and because within the open period an agent could silently rewrite its own mistakes — the one
thing that must remain visible. It also leaves any statement shared mid-period provisional
until close, which is the version problem this decision exists to prevent.

### Soft delete or tombstones instead of reversing entries

Attractive for query simplicity — filter on a flag — and a familiar pattern outside accounting.

Rejected because a tombstoned transaction has no reversing posting, so a trial balance taken
between the deletion and any compensating entry does not tie. It is also not a recognised
accounting correction: an auditor sees an entry that vanished rather than a documented
reversal, which is the appearance the professional standard exists to avoid.

### Event sourcing with rebuilt projections

Attractive because it maximises fidelity and would make historical report reproduction
natural.

Rejected as redundant. In a double-entry system the postings **are** the event log; layering a
separate event stream over an already append-only ledger duplicates it. Rebuilding projections
also pulls toward materialised balances, whereas balances are derived by aggregation over
postings (ADR-0002).

### Configurable per entity — hard for CFO-managed books, soft for founders

Genuinely tempting, because it matches the audience split exactly and lets each user have the
posture they expect.

Rejected because it makes the correctness story conditional. Every downstream guarantee —
reproducible statements, audit defence, "the agent cannot rewrite your books" — would have to
be qualified by which mode an entity is in, and support answers would begin with "it depends".
The draft state already gives founders the latitude they actually need, which is room to fix
things *before* they count.

## Consequences

**Accepted costs.**
- Two record states and a transition between them. Every write path must know which side of
  the boundary it is on, and getting that wrong is a correctness bug rather than a nuisance.
- Corrections triple the rows involved, and reporting must aggregate across a transaction and
  its reversal.
- The agent's mistakes are in the ledger permanently once posted. Draft-by-default limits how
  often that happens; it does not eliminate it.
- Users arriving from QuickBooks will find CFOKit stricter and will ask for edits. The answer
  is the draft state, and it will not always satisfy them.

**Follow-on obligations.**
- Schema-level enforcement: posted rows reject `UPDATE` on financial fields and reject
  `DELETE` outright. A `CLAUDE.md` rule alone is insufficient for a guarantee this load-bearing.
- The zero-sum constraint (ADR-0005) applies **at posting**, not at draft creation — a draft is
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
- ADR-0013 must settle backdating. A backdated posting into a soft-closed period is
  permissible under this ADR, but it changes an already-issued statement and therefore has to
  be surfaced rather than merely recorded.

**Reversal cost. High — close to a one-way door.** The schema, every write path, and the
reporting model all assume it. Moving to editable records later would mean abandoning
reproducible historical statements and introducing a retention-managed audit log to replace the
guarantee. Moving the other way, from editable to append-only, is worse still, because existing
data would carry no reversal history. This is the reason the decision is made before the
booking engine rather than discovered during it.

## Revisit when

- Users routinely post and then immediately reverse. That pattern would indicate the
  draft/posted boundary sits in the wrong place — most likely that confirmation is being
  demanded too early — and it is the signal to move the boundary, not to abandon immutability.
- A jurisdiction requires a correction mechanism this forbids.
- An audit or review finds that reversal chains are unreadable in practice, which would be a
  reporting problem to solve rather than grounds to permit edits.

Row count and storage cost are explicitly **not** revisit triggers. More rows is the price, and
it was accepted knowingly.
