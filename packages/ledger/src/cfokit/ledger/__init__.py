"""CFOKit Ledger — multi-tenant double-entry accounting engine.

Publishes a tool contract. Knows nothing about any consumer (ADR-0014).

Layering, enforced by import-linter and not by convention (ADR-0008, ADR-0009):

    api | mcp     protocol adapters; MCP calls the service layer in-process
    service       orchestration, audit logging, entity locking
    repository    hand-written SQL; no ORM
    engine        pure booking logic; no I/O, no configuration
"""
