---
status: "draft"
kind: "requirement-driven"
date: 2026-08-20
decision-makers: [Geoff]
---

# ADR-0025: The ledger never rounds; presentation rounds half-up, allocation uses largest remainder

**Requirements served:** `LED-05`, `LED-06`, `RPT-12`.

## Context

[ADR-0005](0005-decimal-throughout-numeric-28-10.md) fixed how money is *represented* —
`decimal.Decimal` and `NUMERIC(28,10)` — and explicitly left rounding undecided. That is the
remaining gap before the booking engine can be written, and it surfaces immediately rather than
eventually: the Beancount differential harness ([ADR-0010](0010-beancount-as-test-oracle.md)) cannot
be built without knowing whether the two systems are expected to agree exactly.

Three separate questions hide inside "rounding", and conflating them is how systems end up with
money that does not add up:

1. **Does the ledger round when storing?**
2. **What happens when a figure is shown to a human**, whose currency has fewer decimal places than
   ten?
3. **What happens when a total must be split** across lines that cannot divide evenly — £100 across
   three lines is 33.33 three times, which is a penny short of the total.

The third is not hypothetical. Invoicing and AR (AR-12) allocate constantly: tax across line items,
a payment across several invoices, a discount across a basket.

## Decision

`LED-06` obliges the ledger never to round and gives each commodity a display scale. `RPT-12`
obliges presentation to round half-up and to total from unrounded values. `LED-05` obliges an
uneven division to sum exactly and to be deterministic. `LED-03` obliges exact balance. Those are
the rules, they are stated once in `requirements.md`, and this record does not restate them.

What this record decides is how they are met, and three things follow that requirements do not say.

**Allocation is largest remainder, ties broken by line order.** `LED-05` requires the parts to sum
exactly and the division to be deterministic; it does not say which parts get the residual pennies.
Largest remainder distributes by how close each line came to rounding up anyway. Line order settles
ties so the result is reproducible, which the differential oracle and reproducible reports both
need.

**Allocation lives in the pure engine** (ADR-0008). It takes a total and a line count and returns
parts: no I/O, no configuration, no clock. That makes it property-testable — the parts must sum to
the whole, for any total and any line count — which is the only way a rule like this stays true.

**Exact balance is a deliberate divergence from the oracle.** Beancount infers tolerances, because
a text ledger is written by hand at whatever precision its author chose. CFOKit's input arrives
through an API at full precision and is never rounded on the way in, so anything that fails to
balance exactly is a real defect rather than a rounding artefact. The differential harness will
report this on its first run, and it belongs in the divergence register as intended rather than
being treated as a failure (ADR-0010).

**Rounding is applied once, at the edge.** Never to an intermediate, never stored back. If a
rounding call appears in `engine`, `repository`, or `service`, the boundary has been misplaced.

## Alternatives rejected

### Round to the currency's minor unit when posting

The intuitive choice: store what you would display, so the books and the statement never disagree.

Rejected because it discards information irreversibly at the moment of capture. A feed delivering a
sub-cent value, an FX conversion, or a unit price with more precision would all be silently truncated,
and the original is unrecoverable — which is precisely the class of silent alteration ADR-0007 exists
to prevent. Storing full precision and rounding at the edge gives the same displayed figure without
the loss.

### Banker's rounding (`ROUND_HALF_EVEN`) for presentation

Python's `decimal` default, IEEE's default, and genuinely better in the abstract: it avoids the
systematic upward bias that half-up accumulates over many roundings.

Rejected because the bias argument applies to *repeated arithmetic*, and under this decision rounding
happens once, at the edge, on figures that are not fed back into further calculation. What is left is
a presentation boundary where a reader compares CFOKit's number against a bank statement, an invoice,
or a tax form — and where 2.5 displaying as 2 is a support conversation, not a feature.

### Tolerance-based balancing, as Beancount does

Would make the oracle comparison simpler by matching its semantics, and would tolerate imprecise
input gracefully.

Rejected because tolerance is where errors hide. Beancount needs it because a human types its
ledgers; CFOKit's arrives through an API at full precision and never rounds on the way in, so anything
that fails to balance exactly is a real defect rather than a rounding artefact. Accepting a tolerance
would mean accepting that some transactions create or destroy a small amount of money.

### Allocate by giving the residual to the first or last line

Simpler, and deterministic.

Rejected because it systematically biases one position — the last invoice in every batch absorbs
every rounding residual, which is visible and hard to justify to whoever holds that invoice. Largest
remainder distributes by how close each line was to rounding up anyway, which is both fairer and the
conventional method.

### Let each report choose its own rounding

Maximum flexibility, and some jurisdictions genuinely differ.

Rejected because two reports over the same data would then disagree, and a reader has no way to know
which convention produced which figure. If a jurisdiction requires something different, that is a
policy decision recorded as a requirement, not a per-report option.

### Round intermediates to keep numbers tidy

Rejected outright: rounding an intermediate and then rounding the result is where compounding error
enters. Rounding happens once, at the edge.

## Consequences

**Accepted costs.**
- A commodity needs a **display scale** — USD 2, JPY 0, some currencies 3. That is a registry the
  system does not yet have, defaulting to 2, and it is a follow-on rather than part of this record.
- Stored values can carry more precision than any report shows, so a user summing displayed figures
  by hand may find a penny that the totals do not. Reports must total the *unrounded* values and
  round the total, never sum rounded parts.
- The oracle will report divergences on tolerance. That is expected and documented, but it means the
  divergence register has an entry from its first run.

**Follow-on obligations.**
- Allocation lives in the **pure engine** (ADR-0008): deterministic, no I/O, and therefore
  property-testable — the parts must always sum to the whole, for any total and any line count.
- A divergence-register entry recording that CFOKit requires exact balance where Beancount infers
  tolerance.
- `docs/product/requirements.md` states the rounding and allocation rules, since a reader
  comparing CFOKit's figures against another system needs to know them.
- Rounding never appears in `engine`, `repository`, or `service`. If a rounding call is needed below
  the presentation layer, the boundary has been misplaced.

**Reversal cost. Low for presentation, high for storage.** Changing the display mode is a
presentation-layer change. Changing "the ledger never rounds" after data exists would mean the stored
history has precision that later records lack, with no way to reconstruct which is which.

## Revisit when

- A jurisdiction CFOKit supports requires a different presentation rounding mode, which becomes a
  per-entity policy rather than a global change.
- A commodity needs more than ten decimal places, which is an ADR-0005 question first.
- Allocation is found to be used somewhere it should not be — allocating *across entities*, for
  instance, would be a tenancy problem wearing a rounding costume.
