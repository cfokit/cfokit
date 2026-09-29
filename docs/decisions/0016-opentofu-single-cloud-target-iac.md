---
status: "draft"
kind: "substrate"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0016: Use OpenTofu, one cloud target at a time, with a written deployment contract

## Context and Problem Statement

CFOKit must run in three topologies (ADR-0004): managed cloud, self-hosted cloud, and
self-hosted local. Portability is a product promise and a CI gate, not a convenience.

The obvious reading is that we need infrastructure-as-code for local, GCP, AWS, and
Azure. That reading conflates two different things. Portability is a property of the
container's configuration contract — the app needs `DATABASE_URL`, `PUBLIC_BASE_URL`,
auth issuer settings, and nothing else (ADR-0004). Given that contract, IaC for any
particular cloud is thin glue, not a port.

We also distribute IaC that users are expected to run themselves, under a permissive
license (`NFR-14`, settled as Apache 2.0 in ADR-0026), which makes the license of the IaC
tool a product concern rather than an internal preference.

## Decision Drivers

* The tool ships to users, so its license must permit them to run it freely — the same
  anti-lock-in promise that motivates the self-host tier.
* Portability lives in the configuration contract, not in the number of module sets, so
  the artifact that carries it should be the contract.
* Unexercised infrastructure code rots silently, and rotted code is worse than absent code.
* One workflow and one language across targets, so a second target is a second module
  rather than a second toolchain.

## Considered Options

* OpenTofu, one maintained target at a time, with a written deployment contract
* Terraform
* IaC for all four targets up front
* Cloud-native tooling (CDK, Bicep, Deployment Manager)
* Terraform/OpenTofu modules abstracted across clouds

## Decision Outcome

Chosen option: "OpenTofu, one maintained target at a time, with a written deployment
contract", because portability is carried by the configuration contract rather than by
module coverage, and OpenTofu is the only option whose license lets users run what we
ship.

> We will use OpenTofu, maintain IaC for exactly one cloud target at a time plus
> `compose.yaml` for local, and treat `infra/README.md` as the portability artifact.

Additional targets are added when someone actually needs one, and are expected to be
contributed.

### The deployment contract, and what changing it costs

`infra/README.md` states what any target must provide. That document, not a set of
modules, is the portability artifact, and it is the thing a self-hoster reads.

**Changing the *shape* of the contract requires a record. Adding a variable within the
existing shape does not.** The shape is what makes a deployment portable: configuration
is environment variables only, secrets arrive as containers whose values are populated out
of band, and nothing is read from cloud metadata (ADR-0004). A decision that breaks any of
those is architectural and needs its own record.

The names and count of the variables themselves are specification, and specification
belongs beside the code it configures rather than inside an immutable record. A record
that enumerates variables becomes wrong the first time one is renamed, and cannot be
corrected without violating immutability. `infra/README.md` is the authoritative list.

### Consequences

* Good, because a self-hoster on an untargeted cloud has a contract to build against
  rather than having to reverse-engineer one from modules.
* Good, because one working target that CI exercises is more honest than four module sets
  nobody runs.
* Good, because OpenTofu ships state encryption, which is directly useful for a financial
  application.
* Bad, because users on a cloud we do not target write their own IaC.
* Neutral, because OpenTofu and Terraform configurations remain interchangeable, so the
  license choice costs nothing in portability of the configuration itself.

### Confirmation

Partly enforced. CI gate 2 runs the full suite against `compose.yaml` with no cloud
credentials present, which is what keeps the configuration contract real (ADR-0004) — an
application that reached for cloud metadata or a provider SDK would fail there.

**The one-target rule itself is enforced by review, not by a gate.** Nothing fails the
build if a second `infra/aws/` directory appears; `CLAUDE.md` forbids it and a human has to
notice. This is a convention backed by a rule rather than a constraint, and it is stated
plainly here rather than implied.

## Pros and Cons of the Options

### OpenTofu, one maintained target at a time, with a written deployment contract

* Good, because MPL-2.0 under the Linux Foundation, and in the CNCF — users can run what
  we ship without a license question.
* Good, because it ships state encryption, which Terraform gates behind its own tiering.
* Good, because the contract degrades gracefully: an untargeted cloud has a specification
  to meet rather than nothing.
* Bad, because the provider ecosystem is downstream of Terraform's, so a needed provider
  could in principle lag.

### Terraform

Near-identical in configuration, providers, and commands, with a larger vendor ecosystem —
the default choice, and the one most contributors would already know.

* Good, because it is the ecosystem everything else is written against.
* Bad, because version 1.6.0 and later ship under BUSL 1.1 with IBM as licensor, which is
  source-available rather than open source. Shipping IaC our users cannot freely use
  contradicts the anti-lock-in promise that motivates the self-host tier. This is
  disqualifying on its own.

### IaC for all four targets up front

Attractive because it makes the portability promise visible in the repository rather than
in a document.

* Good, because a user on any of the four clouds finds something to run.
* Bad, because module sets nobody runs and CI never exercises rot silently. The first user
  to try an unmaintained module hits provider version errors and concludes the project is
  abandoned — worse than shipping nothing for that cloud.
* Bad, because it is speculative abstraction, which ADR-0012 makes a gated decision rather
  than a default.

### Cloud-native tooling (CDK, Bicep, Deployment Manager)

* Good, because ergonomics within a single cloud are better than a general-purpose tool's.
* Bad, because adding a second target would mean a second toolchain and a second language
  rather than a second module, which is precisely the cost being avoided.

### Terraform/OpenTofu modules abstracted across clouds

A shared module interface with per-cloud implementations, so the contract is expressed as
code rather than prose.

* Good, because the contract would then be type-checked rather than written down.
* Bad, because resources are provider-specific. The abstraction buys one workflow and one
  language, which the chosen option gets anyway, while adding an indirection layer that
  obscures what is actually deployed.

## More Information

**Follow-on obligations.**

* `infra/README.md` deployment contract, kept current as the configuration surface changes.
* IaC creates secret *containers* only, never secret values. State contains secrets in
  plaintext; treat state as sensitive and enable OpenTofu state encryption.
* Bootstrap (state backend storage) is a documented one-time step with local state,
  separate from the main configuration.
* `compose.yaml` at the repo root stays the local path and is exercised by the CI
  portability gate (ADR-0004).

**Reversal cost.** Low. OpenTofu and Terraform configurations are interchangeable; adding
a target is additive.

Related: ADR-0004 (portability as a build gate), ADR-0017 (which target), ADR-0026
(license), ADR-0032 (component configuration, which extends the contract within its shape).

## Revisit when

* A second cloud target has real demand — a paying customer or a contributor offering to
  maintain it. Add it then, not before.
* OpenTofu diverges enough from the provider ecosystem that a needed provider is
  unavailable.
* The BUSL grant on Terraform changes, which would remove the license objection but not
  the single-target reasoning.
