"""ADR-0036 layer 4: evals, the only layer that needs a model.

**These do not gate a commit, and that is deliberate.** Layers 1 to 3 are deterministic and
run on every change. Evals are slow, non-deterministic and cost tokens, so they run on a
cadence and a regression here blocks a release rather than a commit. They skip unless asked
for, the way the integration tier skips without a database.

What belongs here, from ADR-0036 § 4 and the claims `skills/bookkeeper/SKILL.md` makes:

- Did it draft rather than post directly?
- Did it stop and ask when it met a closed period, rather than working around it (ADR-0030)?
- Given a document carrying an embedded instruction, did it post anything (`PLT-23`)?
- Did it abandon a refused import rather than forcing it, and report skipped rows rather
  than repairing them?
- Did it ask rather than guess where nothing resolved the assignment (`BKP-12`)?
- Did it keep books anywhere but CFOKit?

**Assert on records, never on prose**, and never on the trial balance — that is a derived
aggregate, and two materially different behaviors produce an identical one. What a turn
leaves behind is the transaction and whether it is draft or posted, the postings under it and
the accounts they hit, any reversal link, the audit row, and the decision record of ADR-0033.

**Gate on a statistically significant regression in pass rate, not a fixed threshold.**
Demanding 100% of a non-deterministic system produces a suite people disable. **Pin the model
version** (ADR-0033, `SOC1-35`).

The directory is empty of cases. ADR-0036's "Revisit when" names the missing piece: a harness
that runs a skill against graders with a no-plugin baseline arm, "without it an eval reports
that the model did well, which is not the question". A case written before that arm exists
measures the model rather than the skill, so the marker and the gate are here and the cases
wait for the harness.
"""

from __future__ import annotations

import os

import pytest

ENABLED = os.environ.get("CFOKIT_EVALS", "")


@pytest.fixture(autouse=True)
def _requires_a_model() -> None:
    """Skip everything in this directory unless evals were asked for.

    Autouse rather than an importable marker, for the reason `tests/integration/conftest.py`
    gives: `tests` is not a package, and making it one to share a constant would be a lot of
    ceremony for a skip.
    """
    if not ENABLED:
        pytest.skip("evals run on a cadence, not per commit: set CFOKIT_EVALS=1")
