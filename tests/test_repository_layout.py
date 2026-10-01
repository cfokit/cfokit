"""The web client's tree and the Python tree do not overlap (ADR-0054).

`web/` holds everything that runs in a browser or builds what does, and nothing else in the
product holds Node tooling. A skill is exempt: its bundle is its own kind of artifact and
carries whatever code the agent's runtime runs (ADR-0020). These read the tracked files, so they
need a git checkout and skip inside an image, which carries no `.git`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

NODE_MANIFESTS = {"package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "package-lock.json"}
NODE_SOURCE_SUFFIXES = {".ts", ".tsx", ".jsx"}
BUILD_OUTPUTS = ("web/dist/", "web/dist_keycloak/", "web/node_modules/")


def tracked() -> list[str]:
    if not (REPO_ROOT / ".git").exists() or shutil.which("git") is None:
        pytest.skip("needs a git checkout")
    result = subprocess.run(
        ["git", "ls-files"],  # noqa: S607 — git from PATH, as every contributor runs it
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def outside_web(paths: list[str]) -> list[str]:
    return [p for p in paths if not p.startswith(("web/", "skills/"))]


def test_node_manifests_live_only_in_web() -> None:
    outside = [p for p in outside_web(tracked()) if Path(p).name in NODE_MANIFESTS]
    assert outside == []


def test_typescript_lives_only_in_web() -> None:
    outside = [p for p in outside_web(tracked()) if Path(p).suffix in NODE_SOURCE_SUFFIXES]
    assert outside == []


def test_web_build_output_is_never_committed() -> None:
    committed = [p for p in tracked() if p.startswith(BUILD_OUTPUTS)]
    assert committed == []
