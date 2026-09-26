---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-26
decision-makers: [Geoff Scott]
---

# ADR-0044: An expected value comes only from a source we can redistribute

**Requirements served:** `NFR-01`, `NFR-14`.

## Context and Problem Statement

ADR-0036 § 2 says a conformance case may come from "intermediate accounting exercises,
released examination problems, standard-setter illustrative examples".
`tests/test_conformance_corpus.py` accepts a case whose licence is `public-domain`, `cc0` or
`cc-by-4.0`, and requires a public-domain work to predate 1931.

Those two statements are inconsistent, and nobody has noticed because there is one case. No
standard-setter illustrative example can satisfy that gate: FASB and the AICPA license their
material, and none of it is CC BY. The first person to follow the record rather than the gate
writes a case the gate refuses, or worse, edits the gate.

The constraint the gate is enforcing is real. Fixtures are committed to a repository
distributed under Apache 2.0, and `NFR-14` requires that no component impose an obligation
inconsistent with that on anyone who runs, modifies or forks it. A test fixture derived from a
share-alike source carries share-alike into the repository; one derived from a non-commercial
source cannot ship in a commercial product at all. "It is only a test" is not a distinction
copyright makes.

Checking specific publications rather than licence families produces a sharper picture than
expected, and a worse one:

| Source | Terms | Usable |
|---|---|---|
| US works published before 1931 | Public domain; the 95-year term reached 1930 on 2026-01-01 | Yes |
| US Government works | 17 USC § 105 — no copyright subsists. IRS, SEC, GAO, FFIEC, FASAB | Yes, verbatim |
| US books 1931–1963, never renewed | Public domain; renewal was required and most works never got one | Yes, where already determined |
| OpenStax, *Principles of Accounting* | CC BY-**NC**-SA 4.0 | No |
| Dauderis & Annand, *Introduction to Financial Accounting* | CC BY-**NC**-SA 3.0 | No |
| FASB Accounting Standards Codification, including Basic View | Copyright, plus a licence accepted at registration | No |
| FASB / XBRL US GAAP Financial Reporting Taxonomy | Verbatim and unmodified only, with its own notice | No |
| Beancount's test corpus | GPL-2.0 | No as fixtures; fine as CI tooling (ADR-0010) |

The open textbooks are the surprise. Most OpenStax titles are plain CC BY, but the accounting
ones are not, and neither is any other open accounting text checked. Every large body of
modern worked accounting answers is either non-commercial, share-alike, or proprietary.

Two constraints are easily confused here, and conflating them produces the wrong answer twice.
**Copyright** governs copying someone's expression, and binds what the corpus may contain.
**Provenance** — ADR-0036 § 5's rule that an expected value comes from outside the
implementation — governs whether an assertion is circular, and binds something else entirely.
A source can be perfectly free and still worthless as evidence, and a rule can be unavailable
for copying while remaining perfectly citable.

## Decision Drivers

* A fixture must impose nothing on a fork. `NFR-14` is a `Must` and says "permanently".
* The licence question must be answerable per case by a check, not per case by a judgement.
* We are not qualified to make a copyright determination and must never be in the position of
  having made one.
* Whatever the rule is, it must leave a usable path to the evidence band 3 needs (ADR-0043),
  or it has solved the licence problem by abandoning the claim.
* The distinction between a published answer and a cited rule must survive contact with a
  future reader, or the weaker evidence will be counted as the stronger.

## Considered Options

* Public domain and CC0 only, with a separate cited-rule class for what that cannot reach
* Keep `cc-by-4.0` and add the attribution machinery it requires
* Add a cite-not-reproduce class so standard-setter illustrations can be used by reference
* Accept CC BY-NC-SA, on the view that a test suite is not a commercial use

## Decision Outcome

Chosen option: "Public domain and CC0 only, with a separate cited-rule class", because it is
the only option under which no fixture carries any obligation at all, and because the band the
public domain cannot reach turns out not to need copying in the first place.

**Tier A — in the repository.** `licence` narrows to `public-domain` or `cc0`. `cc-by-4.0` is
removed: nothing in accounting uses it, and admitting it would import an attribution regime —
title, author, URI, licence, and a statement of changes, per case — for no source that exists.
A new `pd_basis` records *how* the work reached the public domain, because "public domain" is a
conclusion and the gate should check the premise:

| `pd_basis` | Requires | Example |
|---|---|---|
| `term-expired` | `year` before the cutoff | Greendlinger, 1911 |
| `not-renewed` | `pd_determination`, a URL to someone else's published determination | a 1947 text, full view on HathiTrust |
| `us-government` | nothing further | IRS Publication 538 |

`not-renewed` is what reaches the SEC era and the Accounting Research Bulletins, and it is the
basis most likely to be got wrong. **We never make the determination ourselves.** The case
cites a library that has already made it and published the result. A renewal search we ran is
not evidence; a full-view determination by a research library is.

**Tier B — outside the repository, and never an oracle.** A sample company file, an
illustration read under a standard-setter's own terms, an exercise from a non-commercial
textbook: all lawful to consult, none redistributable. Tier B is **a defect-finding
instrument**. It may reveal that CFOKit is wrong; it may never supply the expected value that
says so. A Tier B finding enters the repository as a fix plus a test resting on a domain
invariant or a Tier A citation, never as a fixture. Its directory is not committed.

**Cited-rule cases are a third thing, and are kept visibly apart.** Where the authority
publishes a *rule* rather than a worked answer, a case cites the rule by locator, states a fact
pattern we wrote ourselves, and derives the expected postings from the rule by arithmetic short
enough to check. Nothing is copied: a rule is a procedure, which 17 USC § 102(b) excludes from
copyright, and the fact pattern is our own expression. These live in
`tests/fixtures/recognition/`, under their own gate, and **may never count as corpus coverage**.

**How much weaker deserves stating plainly, because it is easy to oversell.** A recognition
case supplies its own journal. Running it therefore shows that CFOKit adds up entries we
handed it and presents the total correctly — which is close to tautological, and is nothing
like a published answer disagreeing with us. The case cannot show that CFOKit would *choose*
the treatment, because ADR-0043 band 3 says it does not choose treatments, so there is no
choice to test.

What the class is actually for is forward-looking: it pins a treatment's booking shape
against a cited authority *before* `BKP-06`'s rules exist to produce it, so that when a rule
is written the expected output is already recorded with something to justify it. That makes
it a specification carrying a citation rather than evidence of conformance. The coverage map
marks such an area `shape` and not `case` for exactly this reason, and a reader who treats
the two as grades of one thing has been misled.

The authorities that are both free and quotable cover more of what these users meet than the
band-3 framing suggests: IRS Publication 538 on cash and accrual, the all-events test, economic
performance and the twelve-month rule for prepayments; Publication 946 on depreciation. These
are tax authority rather than GAAP, which is a difference a case must state rather than blur,
so a cited-rule case records which basis its rule comes from.

### Consequences

* Good, because no fixture in the repository carries any downstream obligation whatsoever, which
  is what `NFR-14` asks for and what a narrower rule than the previous one delivers.
* Good, because `pd_basis` makes the licence claim checkable rather than asserted, and makes the
  1931 cutoff a property of one basis instead of a fact about the whole corpus.
* Good, because `not-renewed` widens the reachable vein by three decades without us ever making
  a copyright call.
* Good, because band 3 gains a usable evidence path that copyright does not touch.
* Bad, because the corpus is now permanently blind to the worked examples a modern textbook is
  full of, and that is a real loss of breadth, not a technicality.
* Bad, because cited-rule cases are weaker evidence and now have to be kept from being counted
  as the stronger kind, which is a rule a future reader has to be told about rather than
  discover.
* Bad, because a recognition case is nearly circular — it supplies the journal whose totals it
  then checks — so it reads as more validation than it is, and the separate `shape` marking is
  a guard against our own presentation rather than against anything external.
* Bad, because Tier B is a discipline with no mechanical enforcement: nothing stops someone
  reading a sample file and typing its figure into a fixture.
* Neutral, because the existing case is unaffected. Greendlinger 1911 is `term-expired` and
  passes the narrower gate unchanged.

### Confirmation

`tests/test_conformance_corpus.py` enforces Tier A: the licence is `public-domain` or `cc0`,
`pd_basis` is one of the three, `term-expired` requires a year before the cutoff, and
`not-renewed` requires a determination URL. The cutoff is a constant reviewed each 1 January
rather than computed from the clock, because a gate whose verdict changes with the date is a
gate that fails on a Tuesday for a reason nobody can reproduce. Recognition fixtures are gated
in the same file, which refuses a case naming no authority, no locator and no basis, and
refuses any attempt to count one as corpus coverage.

The two rules that are not gated, stated plainly rather than implied. Nothing detects a Tier B
source being used as an oracle: the licence field is self-reported, and a figure typed in from
a sample file looks exactly like a figure read from a scan. Nothing verifies that a
`pd_determination` URL says what the case claims it says. Both are review, and ADR-0036 § 5
already concedes what review is worth here, because the reviewer and the author are the same
process. What the gate buys is that the *question* is asked of every case and answered in a
field, which is the difference between a rule and a hope.

## Pros and Cons of the Options

### Public domain and CC0 only, with a separate cited-rule class

* Good, because it is the only option leaving the repository with zero downstream obligations,
  which is `NFR-14` read literally.
* Good, because the check is mechanical and per case, and needs no judgement from anyone.
* Good, because it loses nothing that was actually available: no accounting source checked is
  CC BY, so the narrowing removes a permission nobody could use.
* Bad, because it forecloses the modern worked-example literature permanently, and the corpus
  will always look thin next to what a textbook could have supplied.

### Keep `cc-by-4.0` and add the attribution machinery

Attractive because CC BY is genuinely permissive, compatible with commercial distribution, and
the obligation is only attribution — which Apache 2.0 imposes anyway.

* Good, because it would admit any CC BY source without further argument.
* Bad, because there is no such source. OpenStax's accounting titles are NC-SA, and so is every
  other open accounting text checked; the permission has been in the gate since it was written
  and has never been exercised.
* Bad, because CC BY 4.0's attribution is more specific than Apache 2.0's — title, author, URI,
  licence, and an indication of changes — so honouring it means a NOTICE regime and a
  per-case attribution string, built and maintained for a hypothetical.
* Bad, because a permission nobody uses is a permission nobody checks, and it would be the
  obvious thing to stretch when a tempting NC-SA source turns up.

### Add a cite-not-reproduce class for standard-setter illustrations

The option that would actually reach ASC 606 and ASC 842, by recording a paragraph locator and
the numeric outcome while copying no prose. Numbers are facts, and facts are not copyrightable,
so the copyright argument is genuinely strong.

* Good, because it reaches the material band 3 would most like to cite, by the most direct
  route.
* Good, because the copyright analysis is probably right: a locator is a fact and a figure is a
  fact.
* Bad, because copyright is not the only constraint. Access to the Codification is granted under
  a licence accepted at registration, and a contract can bind where copyright would not — so the
  analysis that matters is the one we have not read and are not qualified to read.
* Bad, because it builds machinery before a case needs it. ADR-0043 declines band 3, so the
  first case requiring this does not exist, and the class can be added by the record that needs
  it with the benefit of knowing why.
* Bad, because a case that cites a paragraph nobody in the project can open is unverifiable by
  the next reader, which is most of what a citation is for.

### Accept CC BY-NC-SA, on the view that a test suite is not a commercial use

Tempting because it unlocks OpenStax and the LibreTexts collections at a stroke — hundreds of
modern worked examples with answers, exactly what the corpus is short of.

* Good, because it is the single largest available body of suitable material.
* Bad, because the non-commercial clause attaches to the distribution, not to the file's role
  in it. CFOKit is a commercial product; shipping an NC fixture inside it is the case the clause
  exists to prevent.
* Bad, because share-alike is worse than non-commercial here: it reaches derivatives, so a
  fixture derived from an SA source argues for SA over the fixture, and a licence argument
  inside an Apache 2.0 repository is precisely what `NFR-14` says must never exist.
* Bad, because "a test is not really distribution" is the kind of reasoning that is cheap to
  adopt and expensive to unwind, and unwinding means deleting cases and whatever they were
  evidence for.

## More Information

**Follow-on obligations.**

* The public-domain cutoff constant advances each 1 January and is reviewed then. It is 1931 for
  2026.
* A Tier B working directory is gitignored rather than merely absent, so the rule is visible at
  the point of temptation.
* Every cited-rule case records whether its authority is tax or GAAP, because the two diverge —
  MACRS against useful lives, the twelve-month rule against deferral — and a case that blurs
  them is worse than no case.
* `.claude/commands/conformance-case.md` carries the procedure for building a case, including
  the source-vetting step, so the licence question is asked before transcription rather than at
  review.

**Reversal cost.** Low. The enum is one line, the corpus is small, and widening a licence rule
never invalidates work done under a narrower one. The asymmetry runs the other way: a case built
on a source later found unfree has to be deleted along with whatever it evidenced, which is why
the rule is set narrow now rather than relaxed and tightened later.

Related: ADR-0043 (what the evidence is for), ADR-0036 (the layers and the provenance rule),
ADR-0026 (Apache 2.0), ADR-0010 (Beancount as CI-only tooling, the same licence question
answered for a dependency rather than a fixture).

## Revisit when

* An accounting source with worked answers appears under CC BY 4.0, CC0 or a public-domain
  dedication. The narrowing is worth reopening for a real source and not before.
* A standard setter publishes illustrative examples under an open licence, which would make the
  cite-not-reproduce option unnecessary rather than merely premature.
* A band-3 case is needed that a cited rule cannot carry, which is the trigger for the
  cite-not-reproduce class and for reading the Codification's licence properly.
* `LED-18` activates and the differential oracle turns on, which supplies evidence with no
  licence question at all and may reduce how much corpus band 1 needs.
