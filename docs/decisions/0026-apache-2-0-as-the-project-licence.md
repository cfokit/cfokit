---
status: "draft"
kind: "requirement-driven"
date: 2026-08-31
decision-makers: [Geoff]
---

# ADR-0026: Apache 2.0 is the project licence

**Requirements served:** `NFR-14`, `NFR-12`.

## Context and Problem Statement

`NFR-14` makes permissive licensing a `Must`: the software is permissively licensed, permanently,
and no component imposes an obligation inconsistent with that on anyone who runs, modifies, or
forks it. It does not name a licence, correctly — a requirement states what, not how.

No record ever chose one. `LICENSE` and `pyproject.toml` said MIT from the first commit, ADR-0002
explicitly left the question open and called it not load-bearing, and ADR-0016 then relied on
"we are an MIT-licensed project" as an input to rejecting Terraform. A decision nobody made was
already carrying weight.

Two facts about this project narrow the choice more than the usual comparison does.

**The business is a service, not the software.** CFOKit's thesis is that software value approaches
zero and value accrues to an accountable hosted offering. That has a direct licensing consequence:
the code should spread as widely as possible, and **the name is the asset**, because the name is
what an accountable service is bought under.

**Contributors are a stated goal, and there is no CLA.** ADR-0002 records that the project is
actively recruiting them, `NFR-12` makes third-party extension a `Must`, and `CONTRIBUTING.md`
has neither a CLA nor a DCO. So whatever the licence says about inbound contributions is what is
actually in force.

## Decision Drivers

* `NFR-14`: permissive, permanently, with no inconsistent obligation on anyone who runs or forks it.
* `NFR-12`: third parties add providers and jurisdictions as additive contributions — so inbound
  contribution terms must be unambiguous without extra paperwork.
* Patent exposure is real. Financial computation and agent orchestration are actively patented
  areas, and a contributor who later asserts a patent over their own contribution is the specific
  risk.
* The project name must remain the project's, because the hosted service is what is sold.
* Enterprise procurement, given the SOC 1 and SOC 2 readiness the requirements already carry.

## Considered Options

* Apache License 2.0
* MIT
* BSD-3-Clause or ISC
* MPL-2.0
* A copyleft licence — GPL, AGPL, or a source-available licence such as BUSL

## Decision Outcome

Chosen option: **Apache License 2.0.**

> The project is licensed under Apache 2.0. `LICENSE` carries the unmodified text and `NOTICE`
> carries the attribution.

`NFR-14` is unchanged. Permissiveness stays the requirement; this record picks the instrument.

### Consequences

* Good, because §3 grants a patent licence explicitly and terminates it for anyone who brings a
  patent action over the software. MIT is silent on patents, and whether it carries an implied
  grant is contested and untested.
* Good, because §5 makes contributions inbound-equals-outbound by default, so `NFR-12`'s
  contribution path needs no CLA.
* Good, because §6 reserves the project's trade names explicitly, which matters precisely because
  the accountable service is the product.
* Good, because it is on more enterprise pre-approved lists than any other permissive licence.
* Bad, because it is 202 lines against MIT's 21, and nobody reads it.
* Bad, because the `NOTICE` convention adds attribution ceremony to anything distributed — which
  includes skills, the one artifact genuinely shipped to a user's machine.
* Neutral, because it does not prevent anyone hosting CFOKit in competition. Nothing permissive
  does, and preventing it would contradict the thesis outright.

### Confirmation

`LICENSE` holds the unmodified Apache 2.0 text and `NOTICE` sits beside it. `pyproject.toml`
declares `license = "Apache-2.0"`. The dependency rule in `CLAUDE.md` is unchanged: check a
licence before adding a dependency and verify it currently rather than from memory.

## Pros and Cons of the Options

### Apache License 2.0

* Good, because it is the only permissive licence that addresses patents, contributions and
  trademarks explicitly rather than by silence.
* Good, because the explicit terms cost nothing at the point of use — a consumer's obligations are
  attribution and NOTICE preservation.
* Bad, because it is long, and its `NOTICE` requirement is real ceremony for distributed artifacts.

### MIT

The incumbent, arrived at by default, and genuinely the best licence for maximum frictionless reuse.

* Good, because it is short enough to read, universally recognized, and imposes almost nothing.
* Good, because copying a skill and adapting it is as easy as it can be.
* Bad, because it says nothing about patents. For a product doing financial computation, that
  silence is the exposure — a contributor can supply code and later assert a patent over it, and
  nothing in the licence stops them.
* Bad, because inbound contribution terms are undefined without a CLA or DCO, neither of which
  exists here. `NFR-12` depends on that path being clear.
* Bad, because it is silent on trade names. Trademark law still applies, so this is ambiguity
  rather than a lost right — but ambiguity about the name is the wrong exposure for a business
  whose product is a service sold under it.

### BSD-3-Clause or ISC

* Good, because BSD-3 adds a no-endorsement clause MIT lacks, and ISC is MIT with tidier wording.
* Bad, because both share MIT's silence on patents and contribution terms, which is the reason MIT
  loses. They change the wording, not the answer.

### MPL-2.0

Weak copyleft, per-file, and compatible with proprietary combination.

* Good, because modifications to MPL files must be published, so improvements return.
* Good, because it has a patent grant, like Apache 2.0.
* Bad, because per-file copyleft is an obligation on anyone who modifies and distributes, which is
  in tension with `NFR-14`'s "no component imposes an obligation inconsistent with that on anyone
  who runs, modifies, or forks it."
* Bad, because file-level reciprocity is genuinely confusing in a repository that ships skills as
  editable Markdown. Whether an edited `SKILL.md` triggers it is the sort of question this project
  should not force on a user.

### A copyleft licence — GPL, AGPL, or BUSL

Reaching for reciprocity to stop a hyperscaler hosting CFOKit in competition.

* Good, because AGPL or BUSL would genuinely prevent unpaid rehosting, which is a real commercial
  concern for a hosted business.
* Bad, because it fails `NFR-14` outright, which is a `Must`.
* Bad, because it contradicts decisions already made. ADR-0019 excludes network copyleft from the
  stack, and ADR-0016 rejected Terraform *for being* BUSL on the grounds that shipping IaC users
  cannot freely use contradicts the anti-lock-in promise. Adopting the thing we rejected others
  for would be incoherent.
* Bad, because it contradicts the thesis. If value accrues to the accountable service rather than
  the code, protecting the code is defending the wrong asset.

## More Information

**Follow-on obligations.**

- `LICENSE` carries the unmodified Apache 2.0 text; `NOTICE` carries attribution and is preserved
  in anything distributed.
- ADR-0016 is corrected: it asserted MIT as settled fact while rejecting Terraform. The conclusion
  is unaffected — BUSL is not permissive under `NFR-14` whichever permissive licence we hold.
- Source files carry no per-file licence header. Apache 2.0's appendix offers one and it is
  declined: the repository is single-licensed and a header on every file is noise.
- Beancount stays GPL-2.0 and CI-only (ADR-0010). Apache 2.0 is one-way incompatible with GPLv2 —
  Apache code cannot be folded into a GPLv2 work — and that direction never arises, because
  Beancount is never combined, never linked, and never distributed. Recorded because it will be
  raised as an objection.

**Reversal cost. Asymmetric, and this is the cheapest moment.** Copyright is currently held by one
person, so relicensing is a file change. Once outside contributors land, moving to Apache 2.0 needs
their agreement for the patent grant to mean anything — and the patent grant is the main reason to
be here. Moving the other way, Apache 2.0 to MIT, means dropping a patent grant users may have
relied on.

## Revisit when

- A dependency or contribution arrives under terms Apache 2.0 cannot accept. That is a dependency
  decision first, and only then a licence one.
- Unpaid rehosting becomes a demonstrated commercial problem rather than an anticipated one. The
  answer would still not be copyleft, because `NFR-14` forbids it — it would be a requirements
  change, argued on its own terms.
- A jurisdiction CFOKit operates in makes the patent grant unenforceable, which would remove the
  main reason to prefer this over MIT.
