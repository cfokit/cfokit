#!/usr/bin/env python3
"""Every CI gate that runs on the host, in one command, cheapest first and failing fast.

`uv run task check` runs this, and so does the opt-in pre-push hook in `scripts/hooks/`. Each
step is the command `.github/workflows/ci.yml` runs for that gate; this adds none and drops
none of the host's. What it cannot run is what needs the compose stack: Gate 2's integration
suite and the end-to-end test, which `docker compose --profile test run --rm test` and CI cover.

The web client's checks run only when the branch changes `web/` or what the client reads from
outside it (`docs/contracts/`, `docs/design/`) relative to `origin/main`, so a documentation
change stays fast. Without `origin/main` to compare against, they run.

It checks the working tree, not a commit: before pushing, that is the tree you committed, as
long as nothing is left uncommitted.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each step: a name, the command, and the directory it runs in.
HOST: list[tuple[str, list[str], Path]] = [
    ("ruff format", ["ruff", "format", "--check", "."], REPO_ROOT),
    ("ruff", ["ruff", "check", "."], REPO_ROOT),
    ("mypy --strict", ["mypy"], REPO_ROOT),
    ("import-linter", ["lint-imports"], REPO_ROOT),
    ("async boundary", [sys.executable, "scripts/check_async.py"], REPO_ROOT),
    ("Gate 4: no floats touch money", [sys.executable, "scripts/check_money.py"], REPO_ROOT),
    ("Gate 6: decision corpus", [sys.executable, "scripts/check_decisions.py"], REPO_ROOT),
    (
        "Gate 5: generate contracts",
        [sys.executable, "scripts/generate_contracts.py"],
        REPO_ROOT,
    ),
    (
        "Gate 5: published interfaces unchanged",
        ["git", "diff", "--exit-code", "--", "docs/contracts/"],
        REPO_ROOT,
    ),
    ("unit and documentation tests", [sys.executable, "-m", "pytest"], REPO_ROOT),
]

WEB_DIR = REPO_ROOT / "web"
PNPM = ["corepack", "pnpm"]
WEB: list[tuple[str, list[str], Path]] = [
    ("web: install", [*PNPM, "install", "--frozen-lockfile"], WEB_DIR),
    ("web: lint", [*PNPM, "lint"], WEB_DIR),
    ("web: test", [*PNPM, "test"], WEB_DIR),
    ("web: build", [*PNPM, "build"], WEB_DIR),
    ("web: design system", [*PNPM, "design-system"], WEB_DIR),
]

# What the web client is built from: itself, and the two things it reads from outside it.
WEB_INPUTS = ["web", "docs/contracts", "docs/design"]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        ["git", *args],  # noqa: S607 — git from PATH, as every other step finds its tool
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def web_changed() -> bool:
    """Whether the working tree differs from where it left origin/main, under WEB_INPUTS."""
    base = _git("merge-base", "origin/main", "HEAD")
    if base.returncode != 0:
        print("check: no origin/main to compare against, so the web client is checked too")
        return True
    tracked = _git("diff", "--quiet", base.stdout.strip(), "--", *WEB_INPUTS)
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", *WEB_INPUTS)
    return tracked.returncode != 0 or bool(untracked.stdout.strip())


def run(steps: list[tuple[str, list[str], Path]]) -> bool:
    for name, command, cwd in steps:
        print(f"\n==> {name}", flush=True)
        started = time.monotonic()
        result = subprocess.run(command, cwd=cwd, check=False)  # noqa: S603 — fixed argv, no shell
        elapsed = time.monotonic() - started
        if result.returncode != 0:
            print(f"\ncheck: FAILED at {name} ({elapsed:.1f}s): {' '.join(command)}")
            return False
        print(f"    ok ({elapsed:.1f}s)", flush=True)
    return True


def main() -> int:
    steps = list(HOST)
    if web_changed():
        steps += WEB
    else:
        print("check: nothing the web client is built from has changed; its checks are skipped")
    if not run(steps):
        return 1
    print("\ncheck: every host gate passed. The integration suite runs in Docker and in CI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
