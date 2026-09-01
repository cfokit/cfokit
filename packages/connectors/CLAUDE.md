# Connectors — package rules

Loads when you work in `packages/connectors/`. Root `CLAUDE.md` still applies.

## The boundary

**Never import `cfokit.ledger`.** An `import-linter` contract fails `uv run task lint` if you try.

**This is a provisional default, not a settled answer.** ADR-0014 governs *skills*, which are
unambiguously separate, and says explicitly that it does not settle whether first-party packages
must also use HTTP. ADR-0022 § 5 leaves ingestion's classification open: it writes drafts, which are
ledger records, so committing atomically argues for an in-process module, while credential isolation
and a scheduled runtime argue for a separate component. The contract stands because it is the safe
direction to be wrong in — an HTTP boundary can be relaxed later, an in-process one cannot.

If you have a reason to cross it, that is the open question in ADR-0022 § 5 being answered. Raise it;
do not work around the contract.

## Naming

The package is named for the **capability**, not the vendor. It was `plaid-sync`; that made
one provider structural. Plaid is a provider. So is Stripe. Neither is the package.
(ADR-0031)

Do not add `plaid` or `stripe` to a module name outside `providers/`.

## Providers

One module per provider under `providers/`, all behind the same protocol. (ADR-0004)

- **Exactly one provider must work with no cloud account and no credentials.** That local
  default is what the CI portability gate exercises and what a self-hoster gets before
  signing up for anything. It is not a test fixture, and it may not be skipped when
  credentials are absent. (ADR-0004)
- **Import provider SDKs inside the function that needs them, never at module scope.** The
  package must stay importable without credentials or optional dependencies present — module
  scope imports break the portability gate and make `--help` require an API key.
- If adding a provider requires changing the protocol, stop and say so. The protocol earning
  its abstraction is the whole premise.

## Licences

Check the licence before adding any provider SDK, and **verify it currently rather than from
memory** — two of this project's ADRs exist because a dependency relicensed. No copyleft in
the distributed artifact.

Any SDK is a runtime dependency, so it needs approval before you add it.

## Ingestion is not booking

A connector's job ends at producing a candidate transaction. Categorisation and booking belong
to the ledger and the bookkeeper skill.

A connector that decides which account something posts to has taken on booking semantics,
which need human review. If you find yourself writing category-matching rules here, the logic
is in the wrong package.

## Correctness

- Monetary values are `decimal.Decimal`, constructed from `str`. Provider APIs commonly return
  amounts as JSON numbers or as integer minor units — **convert deliberately**, and never via
  `float`. This is the single most likely place for a float to enter the system. (ADR-0005)
- Ingestion is idempotent. Re-running a sync must never double-book, which means carrying a
  stable idempotency key derived from the provider's own transaction identifier. (ADR-0029)
- Never log account numbers, tokens, or payee names at info level. Log counts and identifiers.
- A provider that returns a transaction you cannot map is a reported error, not a silently
  dropped row. Retain it with the reason, and record what each sync run was expected to cover
  against what it delivered — a feed that skips a period must be detectable, not inferred from an
  absent batch. (`BKP-21`)
- **Mark content the organisation did not author as it arrives**, and carry the marking with the
  stored record. It cannot be applied retrospectively, and everything downstream that limits what
  an agent may do with untrusted content depends on it. (`BKP-20`, `PLT-23`)
- Record what each transaction was derived from — the feed record, the uploaded statement, the
  document. The link ships with the row or it is lost. (`BKP-19`)
