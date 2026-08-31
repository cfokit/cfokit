---
status: "draft"
kind: "substrate"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0016: Use OpenTofu, one cloud target at a time, with a written deployment contract

## Context

CFOKit must run in three topologies (ADR-0004): managed cloud, self-hosted cloud, and
self-hosted local. Portability is a product promise and a CI gate, not a convenience.

The obvious reading is that we need infrastructure-as-code for local, GCP, AWS, and
Azure. That reading conflates two different things. Portability is a property of the
container's configuration contract — the app needs `DATABASE_URL`, `PUBLIC_BASE_URL`,
auth issuer settings, and nothing else (ADR-0004). Given that contract, IaC for any
particular cloud is thin glue, not a port.

We also distribute IaC that users are expected to run themselves, under a permissive
licence (`NFR-14`, settled as Apache 2.0 in ADR-0026), which makes the licence of the IaC
tool a product concern rather than an internal preference.

## Decision

We will use **OpenTofu**. We will maintain IaC for **exactly one cloud target at a
time**, plus `compose.yaml` for local development. Additional targets are added
when someone actually needs one, and are expected to be contributed.

We will maintain a written **deployment contract** (`infra/README.md`) stating what any
target must provide. That document, not a set of modules, is the portability artifact.

## Alternatives rejected

### Terraform

Near-identical in configuration, providers, and commands, with a larger vendor
ecosystem. Rejected on license: version 1.6.0 and later ship under BUSL 1.1 with IBM as
licensor, which is source-available rather than open source. Shipping IaC our users
cannot freely use contradicts the anti-lock-in promise that motivates the self-host
tier. OpenTofu is MPL-2.0 under the Linux Foundation, is in the CNCF, and additionally
ships state encryption — directly useful for a financial application.

### IaC for all four targets up front

Rejected as speculative abstraction (ADR-0012). Module sets nobody runs and CI never
exercises rot silently; the first user to try an unmaintained module hits provider
version errors and concludes the project is abandoned. That is worse than shipping
nothing for that cloud. A documented contract plus one working target is both more
honest and more useful.

### Cloud-native tooling (CDK, Bicep, Deployment Manager)

Better ergonomics within a single cloud. Rejected because adding a second target would
mean a second toolchain and a second language rather than a second module, which is
precisely the cost we are trying to avoid.

### Terraform/OpenTofu modules abstracted across clouds

A shared module interface with per-cloud implementations. Rejected because resources
are provider-specific — the abstraction buys one workflow and one language, which we
get anyway, while adding an indirection layer that obscures what is actually deployed.

## Consequences

**Accepted costs.** Users on a cloud we do not target write their own IaC. We accept
that and document what it must do.

**Follow-on obligations.**
- `infra/README.md` deployment contract, kept current as the config surface changes.
- IaC creates secret *containers* only, never secret values. State contains secrets in
  plaintext; treat state as sensitive and enable OpenTofu state encryption.
- Bootstrap (state backend storage) is a documented one-time step with local state,
  separate from the main configuration.
- `compose.yaml` at the repo root stays the local path and is exercised by the
  CI portability gate (ADR-0004).

**Reversal cost.** Low. OpenTofu and Terraform configurations are interchangeable;
adding a target is additive.

## Revisit when

- A second cloud target has real demand — a paying customer or a contributor offering
  to maintain it. Add it then, not before.
- OpenTofu diverges enough from the provider ecosystem that a needed provider is
  unavailable.
