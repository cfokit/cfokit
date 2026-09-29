---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-05
decision-makers: [Geoff]
---

# ADR-0040: Import is the first in-process module, and the file never passes through a model

**Requirements served:** `IMP-01`, `IMP-04`, `IMP-05`, `IMP-06`, `IMP-08`, `PLT-02`.

## Context and Problem Statement

`IMP-01` to `IMP-08` require CFOKit to land a company's books from the system it already runs. A
QuickBooks Online export is the concrete case: a zip of `.xlsx` reports carrying, on a real set of
books, 5,556 transactions and 11,580 posting lines across 64 accounts and eight years.

ADR-0022 classified everything outside the ledger as an in-process module or a separate component and
deliberately left the module list to be decided when each domain existed. It also recorded that the
`import-linter` contracts encoding "modules depend on the ledger, never on each other, and the ledger
depends on no module" **do not exist yet** and "are added as the first one lands". Import is the
first one.

Three questions arrive together and cannot be answered separately, because each constrains the next:
where the code lives, what it is called, and how the file reaches it. The third is not obvious. The
intended operator surface is an agent — a skill in a runtime the organization operates (`PLT-02`) —
and the naive shape has the model read the export and hand its contents to a tool. That would put
every posting line, payee and amount through a context window as a side effect of loading a file.

## Decision Drivers

* The ledger stays about double-entry. ADR-0022's test: if the ledger needs to know what a customer
  is, the boundary has moved wrongly. Understanding a QuickBooks export is the same kind of knowledge.
* Atomicity where the domain requires it, which in-process buys and a separate component cannot.
* Boundaries drawn before a domain exists are guesses, and a wrong boundary written down is hard to
  move (ADR-0012, ADR-0031). The `connectors` package was deleted for exactly this.
* `IMP-05` requires an import validated before anything is posted, with the operator able to abandon
  it — which is a shape, not a flag.
* `IMP-08` requires agreement demonstrated rather than assumed, and `NFR-01` allows no tolerance.
* An export of this size does not fit usefully in a context window, whatever anyone thinks about
  confidentiality.

## Considered Options

* Import is an in-process module named for the capability, and reads the file itself
* Import lives in the ledger, beside the export it mirrors
* Import is a separate component from the start
* The model reads the export and passes transactions to a tool

## Decision Outcome

Chosen option: "Import is an in-process module named for the capability, and reads the file itself",
because reading a foreign system's books requires exactly the domain knowledge ADR-0022 keeps out of
the ledger, while nothing about an import has yet earned separation — and because a model asked to
carry eleven thousand posting lines is a lossy pipe that adds nothing to the operation it is
carrying.

> Import is `cfokit.imports`, a sibling of the ledger. The ledger may not depend on it. A reader
> turns one foreign format into `SourceBooks`; nothing below a reader knows what QuickBooks is.
> `plan` says what would happen and `apply` does it. Both take a location and return a summary; the
> transactions go from the file to the database without an intermediate that holds them all.

### 1. Named for the capability, not the vendor or the mechanism

`imports`, not `quickbooks`, which names a vendor, and not `ingest`, which names a mechanism
(root `CLAUDE.md`). The trailing `s` is only because `import` is a keyword.

QuickBooks is one reader inside it. A second source is a second reader against the same
`SourceBooks`, not a second pipeline.

### 2. Export stays in the ledger; import does not

Not an inconsistency. `EXP-01` and `EXP-02` write the ledger's own data in the ledger's own shape and
need no foreign vocabulary. Reading someone else's file needs a great deal of it — which statement a
row appears under, what "Total for X with sub-accounts" means, that a sub-account is printed under its
bare leaf name. That knowledge is the thing the boundary exists to keep out.

### 3. In-process, because separation is not yet earned

ADR-0022 § 3 makes in-process the default. Import holds no third-party credential today. Its one real
claim to separation — that a third party could build a Xero reader against the API — is about an
extension point that does not exist (`NFR-12`), and drawing a boundary around it now is the mistake
`connectors` already made.

### 4. The file is read, not transmitted

`plan` and `apply` take an archive and return a summary. The operator surface passes a location.

This is an engineering constraint before it is anything else, and the test is whether it survives
assuming confidentiality is worth nothing: it does. Eleven thousand posting lines do not fit usefully
in a context, the model gains no insight from carrying them, and truncation mid-import would corrupt
books silently.

**It implies nothing about analysis.** `PLT-02` puts the runtime in the organization's own hands, and
ADR-0035 keeps it there on the default path: a model reading the loaded books is the user's own
runtime reading the user's own data, which is the product rather than a risk. Bulk transfer and
analysis are different operations, and the plumbing for one should not impose the costs of the other.
The reporting tools return figures for exactly this reason.

### 5. Two calls, because `IMP-05` requires two

`plan` reads the file and reports what would be created, what would not, and why. `apply` re-plans
first rather than trusting a plan it was handed: a plan is a description, not a permission, and the
books may have moved.

A plan that cannot foresee a refusal is worth less than no plan, so the refusals it computes are the
ledger's own rules — `MINIMUM_POSTINGS` is imported from the engine rather than restated.

### 6. Basis is two questions, not one

The entries carry one accounting method and the source's stated balances may carry another. A real
QuickBooks export prints cash-basis reports over a journal that is the accrual record.

`IMP-06` refuses a conflict with the **entries** only. The balances' basis explains a divergence
rather than causing one: an accrual journal reconciled against cash-basis balances differs by exactly
what is unsettled, which is ADR-0037 working. Refusing on it would reject a file whose data is fine
because a report beside it was run differently.

### 7. Applying is a person's act; planning is not

`plan` reads a file and reports; `apply` posts a company's whole history in one call. ADR-0007
settles which is which — "the agent proposes; a person's confirmation posts" — and this is the
largest single act of posting the system offers.

Enforced as a capability rather than an instruction, which is the same division ADR-0030 drew
around reopening a closed period and for the same reason: an instruction can be argued past and
a capability cannot. Checked on `actor_class`, which comes from the shape of the token and never
from a claim the caller sets (ADR-0033), so a skill cannot describe itself as a person.

A token carrying no delegation is a person's; one carrying an RFC 8693 `act` claim is an agent
acting for someone, and it is that second shape this refuses. An operator running the import
themselves is unaffected either way.

### 8. Lineage is written at insert

`IMP-04` requires an imported record "identifiable as imported and names the system it came from".
`ledger_transaction.derived_from` has existed since migration 0001 for `BKP-19` and was left
unpopulated because "the sources are not enumerable yet". An import is the first source.

Written at insert and never afterwards. The entry is append-only, so lineage that arrived later could
not be attached — and lineage that *can* be attached later is lineage that can be changed.

### Consequences

* Good, because the ledger stays about double-entry while a whole foreign vocabulary lands beside it.
* Good, because an import commits through the ordinary write path, with its own audit row per
  transaction, rather than through a bulk path with different rules.
* Good, because the one act that could land thousands of entries unattended cannot be reached
  by a delegated agent, while the act that describes it can.
* Good, because `IMP-08` reconciles against the source's own stated figures — its arithmetic against
  ours over the same journal, not ours against itself.
* Bad, because the module needs its own operator surface: the ledger's adapters may not import it, so
  a REST route or MCP tool for import cannot simply be added to `cfokit.ledger.api`.
* Bad, because reading a file by path means the reader and the file must share a filesystem. A hosted
  deployment needs the bytes delivered another way, and that is a separate decision.
* Neutral, because a second reader is additive and touches nothing below `SourceBooks`.

### Confirmation

`import-linter` holds "The ledger depends on no module", failing `uv run task lint` on a violation.
A contract forbidding module-to-module dependencies is added with the *second* module: ADR-0022
forbids them, and a contract naming a single module would assert nothing while reading as though it
did.

The rest is review. No check asserts that a reader stays inside its own file, or that a summary
carries counts rather than figures.

## Pros and Cons of the Options

### Import is an in-process module named for the capability, and reads the file itself

* Good, because it keeps the ledger's boundary and takes the atomicity in-process offers.
* Good, because the placement follows ADR-0022's criteria rather than adding a rule.
* Bad, because the module needs an operator surface the ledger's adapters cannot provide.
* Bad, because "read by path" does not survive a hosted deployment unchanged.

### Import lives in the ledger, beside the export it mirrors

The symmetry is genuinely appealing: `EXP-01` and `IMP-01` read like two halves of one capability, and
`service/interchange.py` already exists.

* Good, because it needs no new package, no contract, and no composition question.
* Bad, because it is the exact failure ADR-0022 § 1 names. The ledger would acquire what a
  QuickBooks report section means, how a sub-account is printed, which footer states a basis — and
  the tiny-ledger test is "if the ledger needs to know what a customer is, the boundary has moved
  wrongly".
* Bad, because the oracle's meaning depends on the engine staying about double-entry (ADR-0002,
  ADR-0010), and vendor knowledge in the ledger erodes that by exactly the amount it grows.

### Import is a separate component from the start

* Good, because an import is a batch workload with a different runtime shape from a request, and
  because a QBO API sync would one day hold vendor credentials that a process holding database
  credentials should not (ADR-0022's blast-radius driver).
* Good, because a third party could build a reader against the published API (`NFR-12`, `PLT-03`).
* Bad, because none of that is true today. There are no credentials, and the extension point does not
  exist — so the boundary would be drawn around a guess, which ADR-0012 and ADR-0031 both refuse and
  which the deleted `connectors` package demonstrates.
* Bad, because it forfeits atomicity now for a separation that may never be needed. ADR-0022 makes
  in-process the default precisely so this trade is not made speculatively.

### The model reads the export and passes transactions to a tool

Attractive because it needs no new entrypoint at all: the agent already has a tool surface, and a
tool taking a list of transactions is the obvious shape.

* Good, because it works identically whether the ledger is local or hosted — the model bridges the
  filesystem gap without anything being built for it.
* Bad, because 11,580 posting lines do not fit usefully in a context. This is disqualifying on its
  own and independent of any view about confidentiality.
* Bad, because truncation is silent. A context that drops the last two thousand lines produces books
  that are wrong and a reconciliation that says so without saying why.
* Bad, because it spends tokens and latency on an operation that gains nothing from a model. The
  value of an agent here is reading the books afterwards, and that capability is unaffected.

## More Information

**Follow-on obligations.** A second module requires the module-to-module contract. An operator
surface for import — REST route, MCP tool, or both — needs a composition point above the ledger's
adapters, since they may not import a module. A hosted deployment needs the bytes delivered without a
shared filesystem, which is not decided here.

**Reversal cost.** Low. `cfokit.imports` is one package with one caller; moving it into the ledger
would be a rename and a contract deletion. The expensive part is the boundary it establishes, and
that is ADR-0022's, not this record's.

Related: ADR-0022 (tiny ledger, modules and components), ADR-0037 (basis as a presentation property),
ADR-0033 (provenance at the tool boundary), ADR-0035 (inference for the attested runtime),
ADR-0010 (the rejected translator, and why a reader is not one).

## Revisit when

* A second reader lands, which tests whether `SourceBooks` is the right neutral shape or a
  QuickBooks shape with the labels filed off.
* An import needs a third-party credential — a QBO or Xero API sync rather than a file — which is the
  blast-radius driver actually firing and the strongest argument for a separate component.
* A hosted deployment needs import, which forces the delivery question this record leaves open.
