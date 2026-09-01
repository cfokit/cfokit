---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0010: Beancount is a differential test oracle, never a runtime dependency

**Requirements served:** `NFR-01`.

## Context and Problem Statement

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
That is not an obstacle to the role chosen here: copyleft in CI-only tooling is explicitly fine, and
GPL obligations trigger on distribution in any case.

### The obvious objection, stated plainly

**If Beancount is the oracle, are we not simply reimplementing Beancount?** Partly, yes — and this
record would be dishonest not to say so.

What the oracle pins down is **booking arithmetic and lot semantics**, and those are not Beancount
inventions: they are correct double-entry, which any conforming implementation must agree on. That
part is commodity, and agreeing with a known-good implementation about commodity behaviour is the
point.

What CFOKit does *not* take from Beancount is everything that makes it a product: multi-tenancy,
per-entity authorisation, an audit trail, a published API, a draft/posted boundary. **ADR-0007 has
no Beancount analogue at all** — a Beancount ledger is a text file you edit, so immutability at
posting is a genuine divergence rather than a difference in degree.

So the oracle tests the part that must merely be *correct*, while the value sits in parts Beancount
does not have. Whether that division justifies building a ledger at all is a separate and larger
question, addressed in its own record rather than assumed here.

## Decision Drivers

* Detect misunderstandings of double-entry semantics, not merely implementation errors — which
  requires an implementation whose errors are uncorrelated with ours.
* Keep the comparison deterministic and scriptable enough to run as a CI gate.
* Do not re-adopt the single-writer, file-oriented constraints ADR-0003 exists to escape.
* One booking implementation in the product, never two.

## Considered Options

* Beancount as a CI-only differential oracle
* Use Beancount as the booking engine itself
* No oracle; rely on our own unit tests
* Write a second independent implementation ourselves
* Compare against a commercial system such as QuickBooks or Xero
* Use Beancount as an optional runtime import, behind a feature flag

## Decision Outcome

Chosen option: **Beancount is a development and CI dependency used as a differential oracle**, and
nothing else.

**It activates with `LED-18` and `LED-19`, not before.** See § "What the oracle covers, and when it
is worth its cost" below; [ADR-0036](0036-correctness-is-tested-in-four-layers.md) holds what tests
correctness in the meantime.

- It is never imported at runtime, never present in the distributed image, and never in the
  default compose stack.
- A differential test suite compares CFOKit's booking results against Beancount's over a corpus
  of transactions.
- **Every divergence must match a documented entry.** An undocumented divergence fails the build.
- The Beancount version is pinned; an upgrade is a deliberate act, because it can change the
  oracle's answers.

### What the oracle covers, and when it is worth its cost

Mapping the ledger requirements against Beancount gives a smaller answer than this record originally
assumed.

| | Requirements | Oracle value |
|---|---|---|
| **Exercised by comparison** | `LED-01` chart of accounts, `LED-02` account types, `LED-03` balance, `LED-10` opening balances | Low. None of these is a semantic anybody misunderstands, and each is a property test. `LED-03` compares only with Beancount's tolerance divergence already documented (ADR-0025). |
| **Where comparison is worth most — deferred** | `LED-18` positions in non-money commodities, `LED-19` FIFO lot consumption | **High, and unavailable.** Lot booking is Beancount's strongest area and CFOKit's hardest problem. Both are `Could \| Deferred`. |
| **No Beancount analogue** | `LED-05`, `LED-07`, `LED-08`, `LED-09`, `LED-11`, `LED-12`, `LED-13`, `LED-14`, `LED-15`, `LED-17`, `LED-20` | None. Beancount is a single-book text file with one date per transaction, no period concept, no accounting basis, and no record that cannot be edited. |

So the claim above — that the oracle pins down "booking arithmetic and lot semantics" — is half true.
Lot semantics are deferred, leaving booking arithmetic, which is the part least likely to be got
wrong and which property tests already reach.

**The cost was also understated.** The oracle is not a CI job. It is a transaction corpus in two
formats, a translator from CFOKit's model into Beancount syntax, a comparison harness, and a
divergence register. The translator is untested code sitting between the system and its own
correctness evidence, and a defect in it produces false agreement as readily as false divergence.

Eleven of twenty requirements having no analogue also means the divergence register would be
dominated by entries reading "Beancount has no concept of this" — noise that buries whatever signal
the register carries.

None of this makes the oracle wrong. It makes it **early**. When lot booking activates, the oracle
covers the hardest semantics in the ledger against the implementation best qualified to check them,
and the cost is then proportionate.

### Consequences

* Good, because it detects the one class of bug our own tests structurally cannot.
* Good, because it costs nothing at runtime and nothing in the shipped image.
* Bad, because we write and maintain a booking engine that already exists elsewhere.
* Bad, because the oracle corpus and the divergence register are ongoing maintenance, and the
  register is the part that will be tempting to neglect.
* Bad, because Beancount's own opinions leak into the comparison. Where CFOKit deliberately
  differs — the posting boundary of ADR-0007 has no Beancount analogue — the divergence must be
  documented as intentional rather than treated as a defect.

### Confirmation

**CI gate 3:** the differential suite passes, with every divergence matching a documented entry.
The `oracle` pytest marker is reserved and configured — **already in place** in `pyproject.toml`;
the CI job is scaffolded and commented out.

It stays commented out until `LED-18` activates. Until then the gate that carries `NFR-01` is the
conformance corpus of [ADR-0036](0036-correctness-is-tested-in-four-layers.md) § 2, which buys the
same independence from published answers rather than from a second implementation.

## Pros and Cons of the Options

### Beancount as a CI-only differential oracle

* Good, because its errors are uncorrelated with ours, which is the entire property an oracle
  needs.
* Good, because GPL-2.0-only is unproblematic for CI-only tooling.
* Bad, because it constrains the comparison to semantics Beancount has opinions about.

### Use Beancount as the booking engine itself

By far the most attractive option on the surface.

* Good, because it is correct, battle-tested, actively maintained, and would remove the need to
  write the most correctness-critical code in the project.
* Bad, on **architecture**. Beancount is file-oriented and single-writer, operating over a text
  ledger parsed in full. That is the model ADR-0003 rejected once multi-tenant hosting became the
  point of the system: no concurrent writers, no deferred constraint triggers, and no path to
  per-entity locking. Adopting it as the engine would re-adopt the constraints ADR-0003 exists to
  escape.
* Neutral on **licence**. GPL-2.0-only is not a reason against this option. GPL triggers on
  distribution, and CFOKit is hosted or self-hosted under a licence we choose, with dependencies
  resolved from an index rather than shipped by us. Copyleft would bite only if Beancount were
  distributed into agent skill runtimes, which is not how it is used.

### No oracle; rely on our own unit tests

* Good, because it is cheaper, and it is the normal standard for most software.
* Bad, because it cannot catch the failure mode that matters most here. A unit test asserts that
  the code does what its author expected. If the author misunderstood how a multi-currency disposal
  or an unbalanced-with-tolerance transaction should book, the test asserts the misunderstanding.

### Write a second independent implementation ourselves

* Good, because it would give a differential comparison with no third-party dependency at all.
* Bad, because an oracle is only worth something if its errors are uncorrelated with ours. The same
  authors, working from the same reading of the same references, will reproduce the same
  misconceptions in both implementations. It would cost twice as much and prove considerably less.

### Compare against a commercial system such as QuickBooks or Xero

* Good, because they define what users expect in practice.
* Bad, because their semantics deliberately differ from CFOKit's — they permit editing posted
  records (ADR-0007), so identical inputs legitimately produce different histories.
* Bad, because neither offers deterministic, scriptable comparison suitable for a CI gate.
* Bad, because driving them programmatically for this purpose raises terms-of-service questions.

### Use Beancount as an optional runtime import, behind a feature flag

* Good, because users wanting Beancount's exact semantics could opt into them.
* Bad, because it creates a second booking path exercised by a subset of users — the
  divergence-nobody-catches failure mode that ADR-0014 and ADR-0018 both reject in other guises.
  Two booking implementations in one product is the problem, regardless of which is default.

## More Information

**Follow-on obligations.**

- CI gate 3: the differential suite passes, with every divergence matching a documented entry.
- A divergence register, versioned in the repository, where each entry states what differs and why
  it is correct for CFOKit. **It is not created until the oracle activates** — ADR-0001 defines a home
  for every kind of document and has none for this, and deferring the register defers that question
  with it. Whoever turns the oracle on settles where the register lives and who adjudicates an entry,
  because a comparison detects difference and cannot say which side is wrong.
- The `oracle` pytest marker is reserved and configured. **Already in place.**
- Beancount pinned, in a CI-only dependency group — never in the default `dev` group used to build
  or run the service, and never in the image.
- Beancount stays out of the runtime dependency group, for the architectural reasons above rather
  than licensing ones — it is an oracle, not an engine.

**Reversal cost. Low.** The oracle is test infrastructure. Removing it would forfeit the strongest
correctness evidence CFOKit has, but it would break no shipped code.

## Revisit when

- **`LED-18` and `LED-19` activate.** This is the trigger that turns the oracle on, and the point at
  which its cost becomes proportionate to what it covers.
- Beancount gains multi-writer, database-backed operation. That is the architectural objection
  rather than the licensing one, and it is the only thing that would reopen using it directly.
- The divergence register grows large enough that the two systems are no longer usefully
  comparable, which would indicate the oracle has stopped testing what we think it tests.
- A permissively licensed, independently derived double-entry implementation of comparable maturity
  appears.
