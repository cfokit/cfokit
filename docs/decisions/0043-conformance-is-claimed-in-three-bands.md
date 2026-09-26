---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-26
decision-makers: [Geoff Scott]
---

# ADR-0043: Conformance is claimed in three bands, and accounting policy is not one of them

**Requirements served:** `NFR-01`, `RPT-09`, `BKP-12`.

## Context and Problem Statement

CFOKit says nothing about GAAP. A search of the corpus for `gaap`, `ifrs`, `fasb` or
`generally accepted` returns nothing at all, in code, requirements, vision or records.

That silence is not neutral, because the product already makes the claim in other words.
The vision promises statements "in a form a lender, a board, or an accountant will accept",
describes CFOKit as doing "bookkeeper **and controller** work", and separates the three jobs
itself: a bookkeeper records and reconciles, a controller closes the month and stands behind
the result, a CPA works from the closed year. Standing behind a close is a conformance claim
whether or not the letters G-A-A-P appear. An unstated claim is the worst kind, because the
reader supplies their own and it is always larger than the one we would have written.

Three constraints bound any answer.

**GAAP conformance is not a property software can hold.** It is a property of a particular
entity's financial statements for a particular period, and the thing that establishes it is an
opinion by a person who is liable for having given it. No ledger, however correct, is
"GAAP compliant", and a product that says it is has said something false.

**The evidence has to exist before the claim does.** `NFR-01` demands correctness against a
source CFOKit did not author, and ADR-0036 § 2 puts the conformance corpus in that role while
the differential oracle stays deferred to `LED-18`. The corpus has one case. ADR-0002 already
states the remedy — "the answer is more cases" — which makes the size of the claim a function
of how much corpus can actually be built.

**What can be built is decided by licensing.** Fixtures ship in an Apache 2.0 repository, so
every source must permit commercial derivative distribution. Redistributable worked answers
exist in quantity for recording mechanics and statement presentation, and essentially not at
all for modern recognition and measurement, which is uniformly standard-setter or publisher
copyright. ADR-0044 holds that analysis. Its effect here is that a claim about revenue
recognition could not be evidenced even if the boundary permitted one.

There is no accountant on the team and no budget to engage one, so nothing in the answer may
depend on professional judgement being available to write assertions.

## Decision Drivers

* A claim must be falsifiable by something in CI, or it is marketing.
* Never claim what the corpus can be made to evidence, only what it does evidence.
* The boundary must coincide with ADR-0022's — the ledger stays tiny — or it gets argued twice
  in two vocabularies.
* The reader who matters is a CPA deciding whether to put a client on this, and their first
  question is what CFOKit will *not* do.
* Where CFOKit declines to decide something, the decline has to be visible in the product,
  not only in a document nobody reads.

## Considered Options

* Three bands — mechanics enforced, presentation produced, accounting policy declined
* Claim GAAP conformance outright, and build the evidence behind it
* Claim nothing, and let each customer's accountant form their own view
* Claim the double-entry mechanics only, and say nothing about the statements

## Decision Outcome

Chosen option: "Three bands", because the only claim worth making is one a test can falsify,
and the three bands are exactly the boundaries at which the available evidence changes kind.

> CFOKit records and presents faithfully. It does not decide accounting policy and does not
> check yours.

**Band 1 — mechanics the ledger enforces.** Recording, balance, the draft/posted boundary,
reversal, period close, year-end close, opening balances, cut-off, allocation. `LED-01`
through `LED-15`, `LED-17`, `LED-20`. Evidenced by the conformance corpus against published
answers. Double-entry mechanics have not moved in a century, so public-domain sources serve
this band completely rather than partially.

**Band 2 — presentation the ledger produces.** Trial balance, profit and loss, balance sheet,
comparative profit and loss, account detail, and the articulation between them. `RPT-01`
through `RPT-12`. Evidenced by the corpus, with cases whose published answer is a statement
rather than a trial balance.

**Band 3 — recognition and measurement.** When revenue is earned, how a lease is classified,
what an asset is worth, what is material. **CFOKit declines this band.** It records what was
decided, exactly and permanently and attributably, and presents it. It does not originate the
decision and does not audit it.

Band 3 is a refusal the product already makes rather than a new one. `BKP-04` scopes accrual
and depreciation entries to operator entry. `BKP-12` requires that an unresolvable assignment
be asked about rather than guessed or parked. `requirements.md` disclaims materiality in terms
— "an accountant's judgement about a set of statements, not a setting the system holds". The
bookkeeper skill says it outright: "You do not decide accounting policy." What this record adds
is that the refusal is now a stated boundary with a document behind it, rather than a property
of the implementation that could erode without anyone noticing.

**The bands are published, not internal.** `docs/conformance/coverage.md` states them area by
area, including every area where the answer is that CFOKit does nothing. A conformance document
that lists only strengths is an advertisement.

### Consequences

* Good, because every clause of the claim is falsifiable: bands 1 and 2 by cases with citations,
  band 3 by the absence of any code that decides.
* Good, because the boundary is ADR-0022's boundary in different words, so the ledger staying
  tiny and the claim staying honest are now the same constraint and cannot drift apart.
* Good, because the coverage map answers a CPA's actual first question, and answering it in
  writing is cheaper than answering it once per prospect.
* Good, because declining band 3 costs nothing that was being delivered — the requirements
  already declined it, without saying so anywhere a customer could read.
* Bad, because a published map of gaps is a published map of gaps, and `RPT-04` cash flows and
  `BKP-06` assignment are both on it.
* Bad, because band 2's evidence depends on sources whose charts of accounts are a century old,
  so every case carries a classification note and some carry a recorded divergence.
* Neutral, because nothing about the ledger changes. This record describes what is already
  built and fixes what may be said about it.

### Confirmation

`docs/conformance/coverage.md` is the claim in machine-checkable form, and
`tests/test_conformance_corpus.py` enforces the relation between it, the corpus and the
requirements: every area marked `enforced` or `presented` carries at least one case, every case
maps to at least one area, and every requirement id either cites resolves in
`docs/product/requirements.md`. It is a static read of the fixtures, outside the integration
tier, so it gates every commit rather than only the runs with a stack up. The behavioural half
— whether a case's figures agree with its published answer — is
`tests/integration/test_conformance.py`.

Band 3's refusal is gated only where a capability enforces it. `PLT-23` is a capability
boundary and holds whatever a skill is told; the bookkeeper skill's "you do not decide
accounting policy" is prose in a prompt and holds only as far as a model follows it. Layer 4
evals assert on the records a turn leaves behind — that it drafted rather than posted, asked
rather than guessed — which is evidence about behaviour and not a guarantee of it. The vision
already grades these two kinds of guardrail against each other and says only one is
trustworthy; this record does not upgrade the weaker one.

Nothing gates the coverage map against the product drifting away from it. A capability could be
added that decides an accounting policy, and no check would fail. That is review, and the
reviewer is the same process as the author.

## Pros and Cons of the Options

### Three bands — mechanics enforced, presentation produced, accounting policy declined

* Good, because the band boundaries are where the evidence changes kind, so each band's claim
  is exactly as strong as the thing backing it.
* Good, because it can be written today and be true today, with one corpus case, and grow
  stronger without being rewritten.
* Good, because it coincides with the architectural boundary already in force, which means one
  argument defends both.
* Bad, because three bands is more to explain than one sentence, and the explanation is the
  part a prospect skims.

### Claim GAAP conformance outright, and build the evidence behind it

The honest version of the marketing answer, and it has the merit of setting a target rather
than describing the floor. Competitors make the claim with less behind it.

* Good, because it is what a buyer wants to hear and what the category is used to hearing.
* Bad, because the evidence cannot be built. Modern recognition and measurement answers are
  standard-setter and publisher copyright without exception, so the corpus cannot reach them
  in a distributable form, and no amount of effort changes that (ADR-0044).
* Bad, because the claim is false in kind and not merely in degree. Conformance attaches to
  statements and to an opinion about them, so a product asserting it has misdescribed what it
  is, and a CPA reads that in one line.
* Bad, because it invites reliance we have disclaimed everywhere else, including in the skill's
  own instructions.

### Claim nothing, and let each customer's accountant form their own view

Attractive because it is the status quo, costs nothing, and cannot be wrong.

* Good, because silence can never be falsified.
* Bad, because it is not actually silence. The vision promises statements an accountant will
  accept and describes the product as doing controller work, so the claim is made and only the
  boundary is missing.
* Bad, because the reader fills the gap with something larger. A buyer told nothing assumes an
  accounting product handles accounting, including the judgement.
* Bad, because it wastes the corpus. Evidence that exists and is not published is evidence
  nobody can rely on, and the corpus is the cheapest trust asset the project has.

### Claim the double-entry mechanics only, and say nothing about the statements

The narrowest defensible claim, and the one requiring least work.

* Good, because band 1 is the part public-domain sources evidence most thickly, and the claim
  would be unarguable.
* Good, because it keeps the conformance document to one page.
* Bad, because the statements are built, shipped, reachable over two protocols, and named in
  `RPT-09` as "defined, tested capabilities". Declining to claim what is already shipped
  understates the product and leaves `RPT-09` unserved.
* Bad, because a lender or a board reads a balance sheet, not a journal. The band a customer
  actually depends on would be the one with nothing said about it.

## More Information

**Follow-on obligations.**

* `docs/conformance/coverage.md` is maintained as areas gain and lose cases. A map that is
  stale is worse than none, because it is read as current.
* Band 3's refusal constrains `BKP-06` when it is built. The rule engine's approval surface is
  where accounting policy enters the system, and per `BKP-09` approval attaches to a rule rather
  than a transaction. A proposal should therefore carry the draft entries the rule would
  produce, so the person approving sees what it books before it books it; approval is the act
  that posts them. That is a decision for the record that builds it, not this one, but a design
  that lets the agent post a judgement directly contradicts this record.
* The bookkeeper skill's description advertises categorisation, which `BKP-06` was to provide
  and which does not exist. The description is corrected alongside this record; the capability
  is not.
* `RPT-09` names cash flows and receivables ageing as "defined, tested capabilities". Neither
  is built. The requirement is corrected rather than the map falsified to match it.

**Reversal cost.** Low internally — the bands are a document and a table, and no code depends
on them. Higher once published, because a conformance claim that narrows after customers have
relied on it costs more than the claim was ever worth. Widening it later is free.

Related: ADR-0036 (the four layers and the corpus), ADR-0044 (which sources may supply
evidence), ADR-0022 (the boundary this one restates), ADR-0010 (the oracle this substitutes
for until `LED-18`), ADR-0002 ("the answer is more cases").

## Revisit when

* `BKP-06` ships, which puts accounting policy into stored rules and gives band 3 a mechanism
  to describe rather than a gap to admit.
* `RPT-04` ships, which closes the largest band 2 gap on the map.
* `LED-18` activates and CI gate 3 turns on, which adds a second independent source of evidence
  for band 1 and may make part of the corpus redundant.
* A CPA reviews the corpus and disputes a band boundary. That is the review this record is
  written to invite, and the first such dispute is worth more than the next ten cases.
* An entity needs statements *audited* rather than accepted, at which point the question stops
  being what CFOKit claims and starts being what an auditor will rely on.
