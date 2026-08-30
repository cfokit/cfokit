"""CFOKit Connectors — transaction feed ingestion.

Produces transactions via the ledger's **public API**, never by importing ledger code.
import-linter enforces this (ADR-0015).

The package is named for the capability, not the vendor. Plaid, Stripe, and anything
else are providers behind one protocol, because provider-specific code sits behind a
protocol with a local default requiring no cloud account (ADR-0004). That local default
is what makes the self-hosted tier and the CI portability gate work.
"""
