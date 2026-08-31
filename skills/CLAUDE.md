# Skills — package rules

Loads when you work in `skills/`. Root `CLAUDE.md` still applies.

## What lives here

Shipped Agent Skills, as `SKILL.md` bundles. These are **product artifacts**, not
development tooling — tooling for developing this repository lives in `.claude/` and is
never shipped. (ADR-0020)

A skill is **not a Python distribution.** It has no `pyproject.toml`, is not a `uv`
workspace member, and `uv sync` does not install it. If you find yourself wanting to add
one, the thing you are building is a package and belongs in `packages/`.

## The hard boundary

Skills talk to the ledger **over HTTP only.** Never import ledger code, never read its
database, never reach into its internals. The skill and the ledger are separate systems
with separate dependency graphs that share a tool contract. (ADR-0014)

This is not a style preference. The boundary is what makes the ledger's tool contract a
real contract rather than an internal convention, and it is why a self-hoster can point a
skill at their own deployment.

If a skill needs something the tool contract does not expose, the answer is a change to the
contract — which is a published interface with stability obligations (ADR-0015) — not a
shortcut around it.

## Writing a skill

- **The ledger is the source of truth about money.** A skill never computes a balance,
  infers a total, or keeps its own tally. Ask the ledger.
- **Never invent a number.** If the ledger cannot answer, say so. A plausible figure is
  worse than no figure in a financial context, because the user cannot tell them apart.
- **Ambiguity is a question, not a guess.** When a transaction could book more than one
  way, ask. Do not book to a suspense account and move on silently — that is a guess with
  extra steps.
- **Report what happened, faithfully.** If a booking failed, say which and why, using the
  error `code` the ledger returned.
- Never echo token values, full account numbers, or payee names into logs.

## Layout

```
skills/
  bookkeeper/
    SKILL.md          # the skill itself
    references/       # optional supporting material
```

One directory per skill. Whether the tax, cash-flow, and compliance roles become separate
skills or modes of one is undecided (ADR-0020) — do not pre-emptively split them.

## Review

Anything affecting how a transaction is recorded is booking semantics and needs human
review before you proceed, regardless of which side of the boundary it sits on.
