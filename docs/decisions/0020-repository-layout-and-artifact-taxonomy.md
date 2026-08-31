---
status: "draft"
kind: "substrate"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0020: Repository layout separates artifact kinds, and packages are named for capabilities

> **Two clauses are superseded by [ADR-0001](0001-documentation-structure.md).** The `specs/`
> directory does not exist — ADR-0001 settled the documentation structure without one, and whether
> CFOKit adopts a specification workflow at all is an open question there. The accounting-policy
> artifact kind does not exist either; the document was dissolved into `requirements.md`, which
> ADR-0001 makes the single document serving auditor and contributor alike. Both are marked below.
> Everything else in this record stands: `packages/` holds distributions only, `skills/` is plural
> and outside the workspace, and packages are named for capabilities.

## Context

The repository was set up for agentic development while it was still nearly empty:
`CLAUDE.md`, a misplaced `README.md`, and five accepted ADRs. `CLAUDE.md` already described
a repo map — `packages/ledger`, `packages/skill`, `packages/plaid-sync`, `infra/` — none of
which existed. Committing to that map without examining it would have made three problems
structural.

**`packages/skill` conflates two artifact kinds.** A `packages/` directory in a `uv`
workspace holds Python distributions; `uv sync` installs its members. An agent skill is a
`SKILL.md` bundle with resources. It is not installable, has no dependency graph, and its
presence in the workspace globs would break `uv sync`. ADR-0014 goes further: the skill and
the ledger are separate systems that share only a tool contract. Housing them in one
installable tree works against a boundary the project treats as hard.

**`packages/skill` is singular.** The product vision covers bookkeeping, tax preparation,
cash flow monitoring, compliance tracking, and reporting. Whether these become separate
skills or one skill with several modes is undecided, but "the skill" is wrong under either
answer.

**`packages/plaid-sync` puts a vendor in a package name.** ADR-0004 requires
provider-specific code to sit behind a protocol with a local default needing no cloud
account. A package named for one provider makes that provider structural, and the vision
anticipates contributors adding others ("I built the CFOKit Stripe integration").

Separately, the specification layer needed a home, and specifications and decision records
have opposite lifecycles: ADRs are immutable once accepted, while specs churn until the
feature ships.

**A fourth artifact kind then surfaced during review.** Auditing the ADR backlog showed that
four entries — 0007 append-only, lot selection, 0012 scope, 0013 backdating — are not
architecture at all. They are **accounting or product policy**: decisions users experience
directly and that an auditor may need to read. Four more (0004, 0005, 0006, 0011) bundle a
requirement together with the mechanism implementing it; their titles show the seam, as in
"zero-sum **enforced by** deferred constraint trigger".

The problem this creates is one of audience, not filing. An auditor asking "what is your cost
basis method?" should not be handed the lot-selection record, and a fractional CFO evaluating CFOKit for a
client needs the backdating rules before installing anything. Neither reads decision records.

## Decision

Directories are organised by **artifact kind**, and packages are named for **capabilities,
not vendors**.

```
packages/   Python distributions; the uv workspace, and nothing else
skills/     Shipped SKILL.md bundles; plural
docs/decisions/   Decision records; immutable once Accepted
docs/product/
  vision.md            Why the product exists
  requirements.md      What it must do — domain-prefixed ids
infra/      OpenTofu for the one maintained cloud target
.claude/    Tooling for developing this repo; never shipped
```

**Artifact kinds, distinguished by audience and by what makes them authoritative:**

| Kind | Answers | Read by | Authority |
|---|---|---|---|
| Requirement | What must it do | Product, contributors, auditors | Traceable to the vision |
| ADR | Why did we decide | Contributors, future maintainers | Rejected alternatives |
| ~~Accounting policy~~ | ~~What do the numbers mean~~ | — | **Superseded by ADR-0001** |
| ~~Spec~~ | ~~How does this feature work~~ | — | **Superseded by ADR-0001** |

*This record proposed four kinds. Two survive.* The accounting-policy document was written and then
dissolved: it restated settled requirements in a second voice, and the two drifted, which is the
failure ADR-0001 names when it makes `requirements.md` serve the auditor and the contributor alike.
The specification layer was Spec Kit, since removed; whether one returns is open in ADR-0001.

- `packages/skill` becomes `skills/bookkeeper/`.
- `packages/plaid-sync` becomes `packages/connectors`, with Plaid and Stripe as providers.
- Distributions are `cfokit-<capability>`, importing as `cfokit.<capability>` through PEP
  420 implicit namespace packages.
- The ADR index moves to `docs/decisions/README.md`, where `CLAUDE.md` already said it was and
  where its relative links resolve.

Directories are not created speculatively. A surface arrives with the decision that
sanctions it.

## Alternatives rejected

### One tree under `docs/`, with `docs/specs/`

The simplest taxonomy and one place to look. Rejected because it houses an append-only
immutable store inside the working area an agent edits constantly. ADR immutability is a
rule an agent can read and still violate while editing neighbouring files; separate trees
make the mistake structurally awkward rather than merely forbidden. Cost of the split is one
extra top-level directory.

### Everything under `specs/`, including ADRs

Considered because specs are the primary agentic input and deserve prominence. Rejected on
two counts. It inverts the dependency — specs cite ADRs and ADRs constrain specs, so nesting
decisions inside specifications gets the relationship backwards. And it has the same
lifecycle-mixing problem as the option above, in a worse position.

### Keep skills under `packages/`

Preserves one tree. Rejected because it requires enumerating workspace members instead of
globbing them, so every new package silently fails to install until someone remembers to
edit the root manifest. It also keeps the category error that ADR-0014's boundary exists to
prevent.

### Ship skills as a Claude plugin bundle

The official layout for distributing skills, agents, and commands as one versioned,
installable unit, and a plausible eventual answer. Rejected **for now** rather than on
merit: it commits to plugin installation as the distribution path, and the vision points at
a hosted service reached through Slack ("Deploy once, manage multiple clients through
Slack"), which ADR-0014 reinforces. Choosing a distribution mechanism before the delivery
surface is settled is the wrong order.

### Keep `plaid-sync`, add packages per provider

Honest about what the first version does. Rejected because it makes each provider a
distribution with its own release cadence, and the shared protocol then has nowhere to live
that does not become a fourth package.

### Everything is an ADR; no accounting-policy document

**This alternative was rejected here and later prevailed.** Recorded rather than quietly corrected,
because the reason it won is the useful part.

The status quo, and it has a real argument: one place to look, and every decision keeps its
rejected alternatives. Rejected because it leaves four decisions that users and auditors need
readable only as decision records aimed at maintainers. "What is your cost basis method?" is a
question an auditor asks and CFOKit must answer in a document written for them.

What that reasoning missed is that the auditor's document already existed. `requirements.md` states
what the numbers mean, in the register an auditor reads, with stable ids — so the policy document
duplicated it rather than serving an unserved audience, and a second document restating settled
decisions in different words is a second thing to keep correct. It was dissolved into
`requirements.md`, and ADR-0001 records that as the structure.

### Split the bundled ADRs into pure requirements and pure ADRs

Tempting for taxonomic cleanliness: move the obligation half of 0004, 0005, 0006, and 0011
into requirements and leave only the mechanism in the ADR. Rejected as churn for its own sake.
The requirement halves already exist (NFR-10, NFR-11, LED-04, LED-03, NFR-03) and cross-
reference the ADRs; splitting the ADRs as well would double the documents and create two
places to keep in sync, while the bundled form reads naturally — the mechanism is most
comprehensible directly beside the obligation it satisfies.

## Consequences

**Accepted costs.**
- Two top-level documentation trees rather than one.
- `cfokit-connectors` is vaguer than `plaid-sync` and says less about what exists today.
- Namespace packages mean no `src/cfokit/__init__.py`; a contributor who adds one breaks
  the other distribution's imports in a way that is confusing to diagnose.

**Follow-on obligations.**
- `packages/*` globbing stays valid, so nothing non-installable may be added under it.
- Connectors must ship one provider that works with no cloud account — the CI portability
  gate depends on it (ADR-0004).
- import-linter enforces the ADR-0014 boundary as a contract rather than a convention;
  `cfokit.connectors` may not import `cfokit.ledger`.
- The skills layout is provisional pending the delivery-surface decision and the question of
  whether agent roles split.
- The ADR backlog is sequenced by **who has to decide**, not by technical dependency. The
  policy four (0007, lot selection, 0012, 0013) need accounting judgement from a human; the
  architecture set (0008, 0009, 0010, 0014, 0015) can be drafted from constraints already
  accepted.

**Reversal cost.** Low for the directory moves — they are renames plus a `CLAUDE.md` edit,
and git records them as renames. Moderate for the distribution names once anything is
published to an index, because import paths appear in user code.

## Revisit when

- The delivery surface is decided, at which point the plugin-bundle question is answerable
  on its merits rather than deferred.
- Agent roles are settled as separate skills or one skill with modes, which determines
  whether `skills/` needs internal structure.
- A second provider exists, which is the first real test of whether the connector protocol
  abstracts anything.
