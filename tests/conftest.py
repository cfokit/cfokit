"""Shared test configuration.

The only thing here is the Hypothesis profile. Deadlines are disabled because a per-example
time limit turns a slow CI runner into a flaky failure, and none of these properties is a
performance claim — what they assert is arithmetic.
"""

from __future__ import annotations

from hypothesis import HealthCheck, settings

settings.register_profile("cfokit", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("cfokit")
