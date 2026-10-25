"""A synthetic small business, written as platform-neutral events (ADR-0078).

Development tooling: nothing here ships, and nothing under `src/` imports it. The generator
writes the business (`business`) as events (`events`); one adapter turns the events into
QuickBooks Online API payloads (`quickbooks`). A second vendor would be a second adapter over
the same events, which is why nothing in `events` or `business` names a QuickBooks concept.

    PYTHONPATH=scripts uv run python -m synthetic_books           # rewrite generated/
    PYTHONPATH=scripts uv run python -m synthetic_books --check   # fail if generated/ is stale
"""
