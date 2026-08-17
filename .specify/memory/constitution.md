# CFOKit Constitution — see CLAUDE.md

**This file is deliberately not the constitution.** It is a pointer, and it must stay one.

CFOKit's constitution is [`CLAUDE.md`](../../CLAUDE.md) at the repository root, together
with the [Architecture Decision Records](../../docs/adr/README.md) it cites. That decision
is recorded in
[ADR-0021](../../docs/adr/0021-spec-kit-workflow-claude-md-constitution.md).

## Why this file is empty of rules

`CLAUDE.md` is loaded into every agent session automatically, cites the ADR holding the
reasoning behind each rule, and encodes five machine-checkable CI gates. A second rules
document would be strictly worse, and its failure mode is silent: an agent follows whichever
document it happened to read, and nobody discovers the divergence until a rule is broken
with a justification attached.

So: **do not run `/speckit-constitution`.** If someone does and this file is overwritten with
generated principles, revert it to this pointer.

## Where the rules actually are

| What you need | Where |
|---|---|
| Binding rules for all packages | [`CLAUDE.md`](../../CLAUDE.md) |
| Package-specific rules | `packages/*/CLAUDE.md`, `skills/CLAUDE.md` |
| The reasoning behind any rule | [`docs/adr/`](../../docs/adr/README.md) |
| What the product must do | [`docs/product/requirements.md`](../../docs/product/requirements.md) |
| Why the product exists | [`docs/product/vision.md`](../../docs/product/vision.md) |
| What is being built next | [`docs/roadmap.md`](../../docs/roadmap.md) |
| Definition of done | `CLAUDE.md` § CI gates |

## The gate that matters most

Every spec and plan opens with a **"Decisions relied on"** block citing ADR numbers. Stock
spec-driven workflows start each feature from empty context and will re-argue settled
questions; that block is what prevents it. The overridden templates in
[`../templates/overrides/`](../templates/overrides/) enforce it.

If a feature appears to require contradicting a cited ADR: stop and escalate. Do not design
around it. Either the spec is wrong, or a new ADR supersedes the old one — and that is a
human decision.
