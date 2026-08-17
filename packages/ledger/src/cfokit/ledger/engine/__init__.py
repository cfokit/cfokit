"""Pure booking engine — the bottom layer (ADR-0008).

No I/O, no configuration, no database, no clock. Every input arrives as an argument
and every output is a return value, so booking semantics are testable in isolation and
differentially against the Beancount oracle (ADR-0010).

Money is `decimal.Decimal`, never `float` (ADR-0004).
"""
