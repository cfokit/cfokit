"""Provider implementations, one module each, all behind the same protocol (ADR-0004).

Exactly one provider must work with no cloud account. That local default is not a test
fixture — it is what the CI portability gate exercises and what a self-hoster gets
before signing up for anything.

Provider SDKs are never imported at module scope; import them inside the function that
needs them so the package remains importable without credentials or optional
dependencies present.
"""
