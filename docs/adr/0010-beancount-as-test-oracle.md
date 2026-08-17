# ADR-0010: Beancount is a differential test oracle, never a runtime dependency

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

## Context

CFOKit's value proposition is that the books are correct. The hardest class of bug to defend
against is not an implementation error but a **misunderstanding of double-entry semantics** —
because our own unit tests encode our own understanding, and therefore cannot detect that the
understanding is wrong. Tests written by the same person who wrote the booking logic will agree
with it about the wrong answer.

The defence against that class of bug is a differential comparison against an implementation
derived independently. [Beancount](https://beancount.github.io/) is a mature, widely used
double-entry accounting implementation with precise, documented booking semantics, and it is the
system CFOKit's model most closely resembles — the commodity concept and the booking-method
vocabulary both come from it.

**Beancount is licensed GPL-2.0-only** (verified for the current v3 line, stable since June 2024).
That is not an obstacle to the role chosen here — copyleft in CI-only tooling is explicitly fine, and
GPL obligations trigger on distribution in any case. It is recorded because it was once thought
decisive, and was not.

## The obvious objection, stated plainly

**If Beancount is the oracle, are we not simply reimplementing Beancount?** Partly, yes — and this
record would be dishonest not to say so.

What the oracle pins down is **booking arithmetic and lot semantics**, and those are not Beancount
inventions: they are correct double-entry, which any conforming implementation must agree on. That
part is commodity, and agreeing with a known-good implementation about commodity behaviour is the
point.

What CFOKit does *not* take from Beancount is everything that makes it a product: multi-tenancy,
per-entity authorisation, an audit trail, a published API, a draft/posted boundary. **ADR-0006 has
no Beancount analogue at all** — a Beancount ledger is a text file you edit, so immutability at
posting is a genuine divergence rather than a difference in degree.

So the oracle tests the part that must merely be *correct*, while the value sits in parts Beancount
does not have. Whether that division justifies building a ledger at all is a separate and larger
question, addressed in its own record rather than assumed here.

## Decision

Beancount is a **development and CI dependency used as a differential oracle**, and nothing else.

- It is never imported at runtime, never present in the distributed image, and never in the
  default compose stack.
- A differential test suite compares CFOKit's booking results against Beancount's over a corpus
  of transactions.
- **Every divergence must match a documented entry.** An undocumented divergence fails the build.
  This is CI gate 3.
- The Beancount version is pinned; an upgrade is a deliberate act, because it can change the
  oracle's answers.

## Alternatives rejected

### Use Beancount as the booking engine itself

By far the most attractive option on the surface: it is correct, battle-tested, actively
maintained, and would remove the need to write a booking engine at all — which is the most
correctness-critical code in the project.

Rejected on **architecture**. Beancount is file-oriented and single-writer, operating over a text
ledger parsed in full. That is the model ADR-0002 rejected once multi-tenant hosting became the point
of the system: no concurrent writers, no deferred constraint triggers, and no path to per-entity
locking. Adopting it as the engine would re-adopt the constraints ADR-0002 exists to escape.

**Not rejected on licence.** An earlier draft made GPL-2.0-only a co-equal reason. That is wrong for
a server-side dependency: GPL triggers on distribution, and CFOKit is hosted or self-hosted under a
licence we choose, with dependencies resolved from an index rather than shipped by us. That concern
was inherited from an earlier architecture which would have distributed Beancount into agent skill
runtimes — genuine distribution, where it genuinely would have mattered.

### No oracle; rely on our own unit tests

Cheaper, and the normal standard for most software.

Rejected because it cannot catch the failure mode that matters most here. A unit test asserts that
the code does what its author expected. If the author misunderstood how a multi-currency disposal
or an unbalanced-with-tolerance transaction should book, the test asserts the misunderstanding.
Only comparison against an independently derived implementation detects that.

### Write a second independent implementation ourselves

Would give a differential comparison with no third-party dependency at all.

Rejected because an oracle is only worth something if its errors are uncorrelated with ours. The
same authors, working from the same reading of the same references, will reproduce the same
misconceptions in both implementations. It would cost twice as much and prove considerably less.

### Compare against a commercial system such as QuickBooks or Xero

Attractive because they define what users expect in practice.

Rejected for three reasons: their semantics deliberately differ from CFOKit's — they permit
editing posted records (ADR-0006), so identical inputs legitimately produce different histories;
neither offers deterministic, scriptable comparison suitable for a CI gate; and driving them
programmatically for this purpose raises terms-of-service questions.

### Use Beancount as an optional runtime import, behind a feature flag

Would let users who want Beancount's exact semantics opt into them.

Rejected because it creates a second booking path exercised by a subset of users — the
divergence-nobody-catches failure mode that ADR-0014 and ADR-0018 both reject in other guises. Two
booking implementations in one product is the problem, regardless of which is default.

## Consequences

**Accepted costs.**
- We write and maintain a booking engine that already exists elsewhere.
- The oracle corpus and the divergence register are ongoing maintenance, and the register is the
  part that will be tempting to neglect.
- Beancount's own opinions leak into the comparison. Where CFOKit deliberately differs — the
  posting boundary of ADR-0006 has no Beancount analogue — the divergence must be documented as
  intentional rather than treated as a defect.

**Follow-on obligations.**
- CI gate 3: the differential suite passes, with every divergence matching a documented entry.
- A divergence register, versioned in the repository, where each entry states what differs and
  why it is correct for CFOKit.
- The `oracle` pytest marker is reserved and configured. **Already in place** in
  `pyproject.toml`; the CI job is scaffolded and commented out pending the engine existing (M2).
- Beancount pinned, in a CI-only dependency group — never in the default `dev` group used to
  build or run the service, and never in the image.
- Beancount stays out of the runtime dependency group, for the architectural reasons above rather
  than licensing ones — it is an oracle, not an engine.

**Reversal cost. Low.** The oracle is test infrastructure. Removing it would forfeit the strongest
correctness evidence CFOKit has, but it would break no shipped code.

## Revisit when

- Beancount gains multi-writer, database-backed operation. That is the architectural objection
  rather than the licensing one, and it is the only thing that would reopen using it directly.
- The divergence register grows large enough that the two systems are no longer usefully
  comparable, which would indicate the oracle has stopped testing what we think it tests.
- A permissively licensed, independently derived double-entry implementation of comparable
  maturity appears.
