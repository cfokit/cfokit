---
status: "draft"
kind: "requirement-driven"
date: 2026-08-31
decision-makers: [Geoff]
---

# ADR-0027: Reopening does not cascade; a stale year-end close is re-run

**Requirements served:** `LED-11`, `LED-12`, `SOC1-16`, `SOC1-20`.

## Context and Problem Statement

ADR-0030 makes a closed period reopenable and nothing else. It leaves one question unanswered, and
close cannot ship without it: **when March is reopened, what happens to April?**

NetSuite answers by cascading — reopening a period reopens every subsequent closed period. That is
the right answer *for NetSuite*, and the reason is architectural rather than accounting. NetSuite
materialises period balances, so April's opening figures are stored values derived from March's
closing state. Change March and the stored April figures are wrong, so April must be reopened to be
recomputed.

**CFOKit does not have that problem.** ADR-0003 chose Postgres partly so that balances are `SUM()`
over postings, and rejected materialised balances explicitly; ADR-0006 rejected them again as a
correctness mechanism. There is no stored April opening balance to invalidate. Post into March and
April's trial balance simply computes a different, correct answer the next time it is asked for.

So the naive cascade would be ceremony imported from a system with a constraint we do not share.

**But one thing genuinely does chain, and it is not the monthly close.** `LED-12` closes income and
expense to retained earnings at fiscal year end, and states that the closing entries are ordinary
postings. An ordinary posting has a fixed amount. That amount was computed from the income and
expense balances as they stood when the close ran — so a posting that lands in the fiscal year
afterwards makes the closing entry **stale**: it moved the wrong amount to retained earnings, and
the new year no longer opens with income and expense at zero.

That is a real dependency, and it is the only one.

## Decision Drivers

* Balances are derived, not stored, so reopening for recomputation's sake achieves nothing
  (ADR-0003).
* `LED-12`'s acceptance is checkable and must stay true: the trial balance on the first day of a
  fiscal year shows every income and expense account at zero.
* Reopening must stay cheap enough for a single operator to use (ADR-0030, `NFR-19`), so any
  cascade must be the smallest one that is actually required.
* `SOC1-20` requires an issued statement whose figures a later correction changes to be marked
  superseded.
* No hard date floor (ADR-0013), so this must remain possible however far back it reaches.

## Considered Options

* No cascade across periods; re-run a year-end close that a later posting made stale
* Full cascade, NetSuite's model: reopening a period reopens every subsequent closed period
* No cascade and no re-run: accept the stale closing entry
* Refuse to reopen a period inside a fiscal year whose close has run
* Post a compensating entry to retained earnings instead of re-running the close
* Materialise period balances, making the full cascade necessary and honest

## Decision Outcome

Chosen option: **reopening a period reopens that period and no other. A fiscal year close that a
later posting makes stale is reversed and re-run.**

> Reopening March reopens March. April stays closed, and its figures recompute because they were
> never stored. If the fiscal year containing March has already been closed, that close is stale
> and must be re-run before the year is closed again.

Three consequences follow.

**Staleness is detected, not remembered.** A closing entry is identifiable as such (`LED-12`) and
records the `recorded_at` watermark it was computed at. Any posting into the year with a later
`recorded_at` makes it stale, and that is a query rather than a flag anyone has to maintain — which
is the same property ADR-0013 got free from append-only.

**Re-running a close is a reversal and a re-post, not an edit.** The original closing entries are
reversed and new ones posted, both remaining visible (`LED-08`). What retained earnings was
believed to be, and what it is now, are both retrievable.

**Staleness chains through year-end closes only, one hop per year.** Retained earnings at the end of
FY2027 derives from postings that include FY2026's closing entries, so re-running FY2026's close
makes FY2027's stale in turn. With three closed years and a posting into the earliest, three closes
re-run — not thirty-six months reopened.

**The default remains not to reopen at all.** ADR-0030 rule 4 already sends a correction discovered
after close into the current open period, which is the prior-period-adjustment treatment accounting
expects. Reopening a prior fiscal year is deliberate and rare, and the cost above is the reason.

### Consequences

* Good, because the common case — a late receipt for last month, inside the current fiscal year — is
  one reopen, one posting, one re-close, and touches nothing else.
* Good, because `LED-12`'s acceptance stays true by construction rather than by hoping nobody posts
  into a closed year.
* Good, because the expensive case is expensive in proportion to what it actually disturbs.
* Bad, because reopening across a year-end is a genuinely larger operation than the operator will
  expect, and it must be explained at the point of use rather than discovered.
* Bad, because retained earnings acquires reversal chains that reporting has to aggregate across.
* Neutral, because an entity that never closes a fiscal year never meets any of this.

### Confirmation

A test posts into a fiscal year after its close, and asserts that the close is reported stale and
that the first-day trial balance shows income and expense at zero only after the close is re-run.
`LED-12`'s acceptance criterion is the assertion.

## Pros and Cons of the Options

### No cascade; re-run a stale year-end close

* Good, because it cascades exactly as far as the dependency reaches and no further.
* Good, because it needs no new state — staleness is derivable from the watermark a closing entry
  already carries.
* Bad, because "reopening March may require re-running FY2026's close" is a harder sentence to
  explain than "reopening March reopens everything after it."

### Full cascade, NetSuite's model

The obvious answer, and the one a reader who knows NetSuite will propose.

* Good, because it is simple to state and impossible to get subtly wrong.
* Good, because it matches what an accountant arriving from an enterprise ledger expects.
* Bad, because it solves a problem CFOKit does not have. The cascade exists to recompute stored
  balances, and CFOKit stores none (ADR-0003).
* Bad, because it makes an ordinary correction enormous. A late receipt for March would reopen every
  month since, and a sole operator would face a wall of open periods to re-close — which `NFR-19`
  forbids and which would train people to avoid closing at all.

### No cascade and no re-run

* Good, because it is the cheapest possible answer and the monthly case is already correct.
* Bad, because it breaks `LED-12`'s acceptance directly: the new year would not open with income and
  expense at zero, and the trial balance would not tie. This is not a policy preference; it is a
  wrong number.

### Refuse to reopen inside a closed fiscal year

Effectively a hard floor at each year end, which is close to Sage Intacct's separate *lock*.

* Good, because it is simple, and it makes a closed year genuinely final.
* Good, because it removes the stale-close problem by construction.
* Bad, because ADR-0013 rejected a hard floor: it forbids legitimate late adjustments and gets
  worked around. A jurisdiction that reopens a prior year for an amended return is ordinary.
* Neutral, because a deliberate irreversible seal remains worth having later — Intacct has one — but
  as an explicit act an operator chooses, not as a side effect of the year rolling over.

### A compensating entry to retained earnings instead of re-running the close

Leave the original closing entries alone and post the difference.

* Good, because it is less work and leaves the original close untouched.
* Bad, because the closing entries would no longer be the entries that closed the year. `LED-12`
  says they are identifiable as such, and an examiner reading them would find they did not agree
  with the income and expense they claim to close.
* Bad, because it hides the event. Re-running says the year was reopened and re-closed; a
  compensating entry looks like an ordinary adjustment and the reopening becomes invisible in the
  place it matters most.

### Materialise period balances

Store opening balances per period, making the full cascade necessary and therefore honest.

* Good, because it would make period reports cheaper on large ledgers.
* Bad, because ADR-0003 and ADR-0006 both rejected materialised balances, the second on the grounds
  that a stored value can disagree with the postings it summarises. Introducing them to justify a
  cascade would be adopting a constraint in order to obey it.
* Bad, because materialisation belongs behind profiler evidence, and there is none.

## More Information

**Follow-on obligations.**

- A closing entry records the `recorded_at` watermark it was computed at, from the first migration
  that introduces close.
- Staleness is a query over postings, not a stored flag.
- Re-running a close reverses the original entries and posts new ones; both remain visible.
- An issued statement covering a period whose figures changed is marked superseded (`SOC1-20`).
- The reopen flow states, before the operator confirms, how far the consequence reaches — one period,
  or a period plus one or more year-end closes.
- The accounting period is a first-class record (`SOC1-16`), which is what makes "is this period
  closed" and "which close covers this posting" answerable without deriving date ranges per query.

**Reversal cost. Low.** This is service-layer behaviour over a data model that does not change. Moving
to a full cascade later is a policy change; moving to a hard year-end seal is an additional capability
rather than a replacement.

## Revisit when

- Lot tracking activates (`LED-18`). A backdated acquisition changes downstream cost basis, which is
  a second thing that genuinely chains, and it is the `rebook` operation ADR-0013 already defers.
- Re-running closes becomes routine rather than exceptional, which would mean corrections are
  reaching prior years often enough that the default of posting into the current period is not being
  taken, and the question is why.
- An entity wants a year sealed irreversibly — after an audit or a filing — which is the Intacct lock
  and needs its own record.
