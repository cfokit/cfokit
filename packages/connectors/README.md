# cfokit-connectors

Transaction feed ingestion — bank accounts, cards, and payment processors.

Produces transactions through the ledger's **public API**. It does not import ledger
code, and import-linter fails the build if it starts to
([ADR-0014](../../docs/adr/README.md)).

## Why it isn't named after a vendor

The earlier working name was `plaid-sync`. Naming a package after one provider makes that
provider structural, which contradicts the rule that provider-specific code sits behind a
protocol with a local default requiring no cloud account
([ADR-0003](../../docs/adr/README.md)). Plaid is a provider. So is Stripe. Neither is the
package.

## Provider rules

- One module per provider under `providers/`, all behind the same protocol.
- **Exactly one provider must work with no cloud account.** That local default is what
  the CI portability gate exercises and what a self-hoster gets before signing up for
  anything — it is not a test fixture.
- Provider SDKs are imported inside the function that needs them, never at module scope,
  so the package stays importable without credentials or optional dependencies present.
- Check the licence before adding a provider SDK, and verify it currently rather than
  from memory. No copyleft ships in the distributed artifact.

## Ingestion is not booking

A connector's job ends at producing a candidate transaction. Categorisation and booking
belong to the ledger and the bookkeeper skill. A connector that decides which account
something posts to has taken on booking semantics, which need human review
(`CLAUDE.md`, Working style).
