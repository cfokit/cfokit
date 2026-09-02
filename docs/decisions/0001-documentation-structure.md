---
status: "draft"
kind: "substrate"
date: 2026-08-30
decision-makers: [Geoff]
---

# ADR-0001: Documentation structure

## Context and Problem Statement

CFOKit needs documentation, and it needs a structure decided once rather than re-derived by
whoever writes the next document.

Every kind of writing a software project produces has a different audience and a different
lifecycle. Requirements churn until they are agreed. Decisions churn until the system has users
who depend on them. Instructions to an agent are read every session and cost context on every
request. User instructions are read by people who will never see the source. Put them in one
undifferentiated tree and each erodes the others: a reader looking for what the system does
finds an argument about what it might have done, and the rules file grows until nothing in it
is followed.

The repository is developed by agents and is intended to take contributors. Both need the same
thing: a defined place for every kind of document, and a strong enough point of view that the
question does not get reopened.

## Decision Drivers

* One home per kind of writing, chosen by audience and lifecycle.
* Records separated from the working area, so an argument about what the system might have been
  is never mistaken for a description of what it is.
* A published standard in preference to a local invention, for each kind — the same reasoning that
  selects OpenTofu, Conventional Commits and Semantic Versioning elsewhere.
* Machine-readable metadata where a document has structure, so CI can check what review otherwise
  has to.
* A document states what is true now. The reasoning behind a decision belongs in a decision record;
  the history of how the thinking evolved belongs nowhere.

## Considered Options

* A defined home per kind, chosen by audience and lifecycle, each governed by a published standard
* One documentation tree — everything under `docs/`
* Diátaxis for the whole corpus
* No prescribed structure; per-document judgement

## Decision Outcome

**Every kind of document has exactly one home, and each home follows a published standard where
one exists.**

| Kind | Location | Read by | Lifecycle | Standard |
|---|---|---|---|---|
| Entry point | `README.md` | Anyone arriving | Churns | — |
| Vision | `docs/product/vision.md` | Product, contributors | Churns | — |
| Requirements | `docs/product/requirements.md` | Product, contributors, auditors | Churns until agreed; requirement ids are stable | — |
| Decision records | `docs/decisions/NNNN-*.md` | Contributors, future maintainers | Churns until the system has users who depend on them | [MADR 4.0.0](https://adr.github.io/madr/) |
| User documentation | `docs/tutorials/`, `docs/how-to/`, `docs/reference/`, `docs/explanation/` | Users | Churns | [Diátaxis](https://diataxis.fr) |
| Agent and contributor rules | `CLAUDE.md`, `src/cfokit/*/CLAUDE.md` | Every session | Churns | — |
| Contributor guide | `CONTRIBUTING.md` | Human contributors | Churns | — |

`requirements.md` serves the auditor as well as the contributor. There is no separate policy
document; a second document restating the requirements in another voice is a second thing to keep
correct, and the two drift.

`docs/reference/` is generated from source wherever a generator exists. Generated reference does
not drift.

Directories arrive with their first document. Defining the place does not mean creating an empty
folder.

### Decision records

MADR 4.0.0, full template, in `docs/decisions/`, with three local rules:

1. **`Considered Options` and `Pros and Cons of the Options` are mandatory.** MADR marks the second
   optional. A record that names alternatives without refuting each one does not prevent
   re-litigation, which is the main thing a decision record is for.
2. **`Revisit when` is added**, naming concrete triggers. MADR permits added sections.
3. **One decision per record, tested by supersession.** A record may state a decision in several
   clauses when they stand or fall together. The test is: *could one clause be superseded without
   reopening the others?* If it could, they are two decisions and belong in two records.

   A title containing "and" is a signal to apply the test, not a violation by itself. ADR-0007
   couples immutability at posting with corrections as reversing entries; neither half can be
   superseded alone, because reversal is what immutability leaves as the only correction mechanism.
   ADR-0008 originally also decided against an ORM, which *could* have been reversed without
   touching the layering — so that became ADR-0028.

   The cost of getting this wrong is paid at supersession, which is exactly when a corpus is
   under the most pressure: a bundled record forces a reader to re-open settled reasoning to change
   one part of it.

Records are numbered sequentially with no gaps. Numbers are identifiers, not chronology; the
`date` field is authoritative for sequence. A record that turns out to be wrong is corrected in
place, and one describing a problem the system does not have is deleted and the numbering
closed up. Supersession is available where the earlier reasoning is worth keeping beside the
new; it is not required. These loosen when something outside this repository cites a record.

### How the documents derive

```
vision.md  →  requirements.md  →  decision records  →  CLAUDE.md rules
```

The vision states why CFOKit exists. Requirements state what it must do, carrying stable
domain-prefixed ids — `LED-`, `BKP-`, `IAM-`, `PLT-`, `RPT-`, `IMP-`, `EXP-`, `AR-`, `NFR-`, `SOC1-`,
`SOC2-` — each traceable to the vision. Decision records that answer a question the product forces cite the
requirement ids they serve; records that settle a choice the product does not force cite none — see
Two kinds of decision record below. Rules in `CLAUDE.md` cite the record holding their reasoning.

**The arrow never reverses.** A requirement that cites a decision record has been written
backwards: the decision exists to satisfy the requirement, not the other way round. A requirement
constrained by a decision is a requirement that has been quietly rewritten to match what was
built.

Citation follows the same direction:

| Document | Cites |
|---|---|
| `vision.md` | Nothing. It is the root. |
| `requirements.md` | The vision. **Never a decision record.** |
| Decision records | Requirement ids, and each other by number |
| `CLAUDE.md`, `CONTRIBUTING.md` | Decision records, because a rule must point at the reasoning that binds it |

### Two kinds of decision record

Not every decision descends from a requirement, and pretending otherwise invents requirements to
justify choices that were never requirement-driven. Records are one of two kinds, declared as
`kind:` in frontmatter.

| Kind | Answers | Cites a requirement id |
|---|---|---|
| `requirement-driven` | A question the product forces | **Always.** At least one. |
| `substrate` | A choice any project of this shape must make | No. It has no requirement to cite. |

The discriminator is: **would this decision change if the requirements changed?**

Postgres is requirement-driven — multi-tenancy and a database-level zero-sum guard force it, and a
different product would choose differently. Money as `NUMERIC(28,10)` is requirement-driven.
Append-only posting is requirement-driven.

Python, `uv`, the linter, the decision-record format, this record: substrate. They would be the
same choices if CFOKit kept calendars instead of books. Asking which requirement dictates `uv` has
no answer, and a record invented to supply one is worse than no record.

Substrate decisions still need records — they are exactly the choices someone re-proposes in six
months — and they still need rejected alternatives. What they do not need is a manufactured trace
to a requirement.

**ADR-0001 is substrate, and it is the first one.** It decides where requirements are written
down, so it necessarily precedes them. Its shape is not specific to CFOKit: any repository
maintained by an agent needs the same thing settled before anything else can be recorded — one
home per kind of document, a published format for decisions, and a derivation order. What is local
to CFOKit is only which homes exist and what they are called.

### What CFOKit does not keep

**There is no roadmap file and no specifications directory.** Neither is absent by oversight, and
neither should be re-added without a record superseding this one.

**Where work sequencing lives is undecided**, and this record does not decide it. The argument
against a plan committed to git — reviewed on a different cadence than the code around it, covered
by no test, stale silently, and still cited — applies to a plan kept anywhere nobody reads while
reviewing a diff. That includes GitHub Milestones and Projects, which have the additional property
of living on a server rather than in the repository: not in a clone, not in a fork, and not
reviewable in a pull request. Until the need names its own answer, nothing here assumes one.

Whether CFOKit uses a specification workflow at all is a separate question with its own record to
write. Until then nothing assumes a location for one.

### Consequences

* Good, because the question "where does this go?" has one answer, available to a contributor who
  has never seen the repository.
* Good, because each home follows a standard already known to contributors and to agents, so no
  local format has to be learned from a template file.
* Good, because records live in their own tree, so an argument about a decision never sits in
  the middle of a description of the system.
* Good, because decision-record frontmatter is YAML, making status values, `superseded by` links,
  and index-to-file agreement checkable in CI rather than by review.
* Good, because `decision-makers` / `consulted` / `informed` record decision authority, which the
  SOC 1 and SOC 2 readiness requirements treat as evidence.
* Bad, because the full MADR template is longer than a minimal one, and length discourages writing
  records at all.
* Bad, because whether specifications exist at all is left open, so one home is undetermined until
  that record is written.

### Confirmation

Decision-record frontmatter is machine-readable, so a CI check asserts that every record carries a
valid `status` and a valid `kind`, that every `superseded by ADR-NNNN` resolves to a file, that
`docs/decisions/README.md` lists exactly the records present, that `requirements.md` and
`vision.md` cite no record, and that every `kind: requirement-driven` record cites at least one
live requirement id.

The `kind` field is what makes the last assertion checkable. Without it the rule is a judgement
call, and a judgement call is not a gate.

That check is `scripts/check_decisions.py`, run as `uv run task check-decisions` and as CI gate 6.
It additionally asserts that the mandatory sections above are present and that `Pros and Cons of the
Options` refutes at least as many options as `Considered Options` names — the local rules are
otherwise the easiest part of this record to let slide, because a record missing them still reads
like a record.

**Rule 3 is not checkable and is not gated.** No check can tell one decision from two; a title
containing "and" is a signal for review, not a failure condition.

## Pros and Cons of the Options

### A defined home per kind, each governed by a published standard

* Good, because audience and lifecycle are the two things that actually differ between documents,
  so splitting on them puts the boundary where the friction is.
* Good, because adopting a published standard per kind means the format question is answered by
  citation rather than by argument, for each kind independently.
* Good, because it degrades gracefully: a kind with no settled standard is named as open rather
  than forced into the wrong home.
* Bad, because it is more structure than a small project strictly needs, and every added home is
  another thing a contributor must learn.

### One documentation tree — everything under `docs/`

* Good, because it is the simplest taxonomy and there is one place to look.
* Bad, because it houses the decision corpus inside the working area an agent edits constantly,
  so a record and the documents deriving from it are edited together and drift silently.
* Bad, because it mixes lifecycles: documents that churn sit beside documents that must never
  change, and a reader cannot tell which is which from the location.

### Diátaxis for the whole corpus

* Good, because it is a coherent, widely adopted framework with a real point of view, and it is
  already the right answer for user documentation.
* Bad, because it classifies by *user need* — learning, doing, looking up, understanding — which is
  the wrong axis for decision records and requirements. An ADR is not a tutorial, a how-to, a
  reference or an explanation; forcing it into "explanation" loses its numbering and its
  status.
* Bad, because it has no concept of a document whose lifecycle differs from the rest.

### No prescribed structure; per-document judgement

* Good, because it costs nothing to adopt and never blocks anyone.
* Bad, because the question then gets re-answered by whoever writes the next document, differently
  each time, and an agent re-derives it from scratch on every encounter.
* Bad, because it is how the same content ends up in two places and drifts.

### On MADR specifically

Within the chosen structure, decision records could use a minimal MADR template, a bespoke template
derived from Nygard's original, or Nygard's template unextended.

* Minimal MADR is rejected because its `Considered Options` is a bare list of names, so a record may
  name three alternatives and refute none — precisely the failure the corpus exists to prevent — and
  it drops `Confirmation`, where enforcement is recorded.
* A bespoke Nygard variant is rejected because every advantage it offers is reproducible inside MADR:
  an optional section can be made mandatory by local rule, and MADR permits added sections. A fork
  buys nothing it could not have for free, while losing YAML metadata, the `consulted` / `informed`
  fields, the tooling ecosystem, and any upgrade path.
* Nygard's original is rejected because it has no alternatives section at all, discarding the
  anti-re-litigation property entirely, and it is a 2011 blog post rather than a maintained
  specification.

## More Information

**On the roadmap.** No published specification or platform convention governs a roadmap file.
`ROADMAP.md` is folk convention, not standard: it is not among GitHub's community health files and
no spec body defines it. [Keep a Changelog](https://keepachangelog.com) has backing and covers
what shipped, which is half of what a roadmap file usually carries. The other half is what is
sequenced, and this record leaves that open rather than naming a home for it.

**Follow-on obligations.**

* `scripts/check_decisions.py` stays current as the corpus grows. **Already in place**, as CI gate 6.
* `CONTRIBUTING.md` carries the table above, so a human contributor finds it without reading the
  decision corpus.
* A record deciding whether CFOKit uses a specification workflow.

**Reversal cost.** Low. Changing a home is a directory move; changing a format is a mechanical
rewrite of one directory.

**Sources.** MADR 4.0.0, <https://adr.github.io/madr/>. Diátaxis, <https://diataxis.fr>.

## Revisit when

* A kind of document arrives that none of the homes above fits.
* A contributor other than the deciders needs to write a record, which is the first real test of
  whether the full MADR template's length discourages writing them.
* MADR releases 5.0.0, at which point the upgrade is evaluated rather than assumed.
