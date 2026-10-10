"""The merge policy puts each pull request in the tier ADR-0048 assigns it.

Expected tiers come from the record's table, not from running the policy. The Dependabot cases
are the actual shapes of pull requests #89 to #94 (branch name, files, commit metadata), which
were open when the record was written, so they cover what arrives in practice.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from review_policy import (
    DEPENDABOT,
    Update,
    classify,
    decide,
    ecosystem,
    fix_rounds,
    parse_codeowners,
    parse_dependabot_updates,
    protecting_pattern,
    pyproject_shape,
    reviewed_shas,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTECTED = parse_codeowners((REPO_ROOT / ".github" / "CODEOWNERS").read_text())


def tier(**overrides: object) -> str:
    args: dict[str, object] = {
        "author": "geoffscott",
        "branch": "some-change",
        "changed": ["src/cfokit/activity/service.py"],
        "protected": PROTECTED,
        "updates": [],
        "pyproject_reshaped": False,
        "new_runtime_packages": set(),
    }
    args.update(overrides)
    return classify(**args).tier  # type: ignore[arg-type]


# --- The protected paths, which a person always reviews ------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/CODEOWNERS",
        "scripts/review_policy.py",
        "scripts/check_money.py",
        "REVIEW.md",
        "src/cfokit/ledger/service/authentication.py",
        "src/cfokit/ledger/migrations/0001_initial.sql",
        "src/cfokit/ledger/engine/balance.py",
        "infra/README.md",
        "CLAUDE.md",
        "src/cfokit/activity/CLAUDE.md",
        "docs/decisions/0048-merge-eligibility-is-policy.md",
        "docs/product/requirements.md",
        "docs/contracts/openapi.json",
    ],
)
def test_a_protected_path_goes_to_a_person(path: str) -> None:
    assert tier(changed=[path]) == "human"


@pytest.mark.parametrize(
    "path",
    [
        "src/cfokit/activity/service.py",
        "src/cfokit/ledgerish/thing.py",  # a prefix of a protected name is not inside it
        "tests/test_activity.py",
        "docs/how-to/connect-claude.md",
        "skills/bookkeeper/SKILL.md",
        "README.md",
    ],
)
def test_an_unprotected_change_by_a_person_may_merge_on_approval(path: str) -> None:
    assert tier(changed=[path]) == "auto"


def test_one_protected_path_among_many_is_enough() -> None:
    assert tier(changed=["README.md", "src/cfokit/ledger/errors.py"]) == "human"


def test_a_file_moved_out_of_a_protected_path_is_still_protected() -> None:
    """Renames are listed as a deletion and an addition, so the old path counts."""
    moved = ["src/cfokit/ledger/errors.py", "src/cfokit/activity/errors.py"]
    assert tier(changed=moved) == "human"


def test_codeowners_refuses_a_pattern_it_would_misread() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        parse_codeowners("/src/**/secret.py @someone\n")
    with pytest.raises(ValueError, match="unsupported"):
        parse_codeowners("docs/decisions/ @someone\n")


def test_protecting_pattern_forms() -> None:
    patterns = ["/infra/", "/REVIEW.md", "CLAUDE.md"]
    assert protecting_pattern("infra/tls/ca.py", patterns) == "/infra/"
    assert protecting_pattern("REVIEW.md", patterns) == "/REVIEW.md"
    assert protecting_pattern("docs/REVIEW.md", patterns) is None
    assert protecting_pattern("skills/CLAUDE.md", patterns) == "CLAUDE.md"


# --- Dependencies: adding one is a decision (CLAUDE.md) -----------------------------------


def test_a_new_runtime_package_goes_to_a_person() -> None:
    assert tier(changed=["uv.lock"], new_runtime_packages={"somepkg"}) == "human"


def test_a_reshaped_pyproject_goes_to_a_person() -> None:
    assert tier(changed=["pyproject.toml"], pyproject_reshaped=True) == "human"


PYPROJECT = """
[project]
name = "cfokit"
dependencies = ["psycopg[binary]>=3.2", "fastapi>=0.115"]

[dependency-groups]
dev = ["ruff>=0.14", {include-group = "lint"}]
lint = ["mypy>=1.18"]

[tool.taskipy.tasks]
lint = "ruff check ."
"""


def test_a_version_change_keeps_the_shape() -> None:
    bumped = PYPROJECT.replace(">=3.2", "==3.3.1").replace("ruff>=0.14", "ruff==0.16.9")
    assert pyproject_shape(bumped) == pyproject_shape(PYPROJECT)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ('"fastapi>=0.115"]', '"fastapi>=0.115", "httpx>=0.27"]'),  # a runtime dependency
        ('"mypy>=1.18"]', '"mypy>=1.18", "black"]'),  # a dev dependency
        ("psycopg[binary]", "psycopg[binary,pool]"),  # an extra
        ('lint = "ruff check ."', 'lint = "true"'),  # a gate's command
    ],
)
def test_anything_but_a_version_changes_the_shape(before: str, after: str) -> None:
    assert before in PYPROJECT
    assert pyproject_shape(PYPROJECT.replace(before, after)) != pyproject_shape(PYPROJECT)


# --- Dependabot, as it actually arrives ---------------------------------------------------

# The commit message of #94 (dependabot/uv/python-2f924b9b90), abridged to three of its six.
UV_GROUP = """Bump the python group with 6 updates

---
updated-dependencies:
- dependency-name: httpx2
  dependency-version: 2.13.1
  dependency-type: direct:development
  update-type: version-update:semver-minor
  dependency-group: python
- dependency-name: import-linter
  dependency-version: '2.15'
  dependency-type: direct:development
  update-type: version-update:semver-minor
  dependency-group: python
- dependency-name: ruff
  dependency-version: 0.16.9
  dependency-type: direct:development
  update-type: version-update:semver-patch
  dependency-group: python
...

Signed-off-by: dependabot[bot] <support@github.com>
"""

# #90: Postgres's tag is not semver, so Dependabot writes no update-type at all.
POSTGRES = """Bump postgres from 17.11-alpine to 18.6-alpine

---
updated-dependencies:
- dependency-name: postgres
  dependency-version: 18.6-alpine
  dependency-type: direct:production
...
"""


def test_dependabot_metadata_is_read() -> None:
    assert parse_dependabot_updates(UV_GROUP) == [
        Update("httpx2", "semver-minor"),
        Update("import-linter", "semver-minor"),
        Update("ruff", "semver-patch"),
    ]
    assert parse_dependabot_updates(POSTGRES) == [Update("postgres", None)]
    assert parse_dependabot_updates("Fix a typo") == []


def test_ecosystem_is_read_from_the_branch() -> None:
    assert ecosystem("dependabot/uv/python-2f924b9b90") == "uv"
    assert ecosystem("dependabot/github_actions/actions/checkout-7.0.1") == "github_actions"
    assert ecosystem("main") is None


def dependabot(branch: str, changed: list[str], updates: list[Update], **kw: object) -> str:
    return tier(author=DEPENDABOT, branch=branch, changed=changed, updates=updates, **kw)


def test_pr_94_a_grouped_minor_uv_update_may_merge() -> None:
    updates = parse_dependabot_updates(UV_GROUP)
    assert dependabot("dependabot/uv/python-2f924b9b90", ["uv.lock"], updates) == "auto"


def test_pr_94_but_not_if_it_brings_a_new_runtime_package() -> None:
    updates = parse_dependabot_updates(UV_GROUP)
    branch = "dependabot/uv/python-2f924b9b90"
    assert dependabot(branch, ["uv.lock"], updates, new_runtime_packages={"x"}) == "human"


def test_a_major_uv_update_goes_to_a_person() -> None:
    updates = [Update("fastapi", "semver-major")]
    assert dependabot("dependabot/uv/fastapi-1.0.0", ["uv.lock"], updates) == "human"


def test_pr_89_keycloak_is_the_issuer() -> None:
    updates = [Update("keycloak/keycloak", "semver-minor")]
    branch = "dependabot/docker_compose/services-e7f6c1f9bd"
    assert dependabot(branch, ["compose.yaml"], updates) == "human"


def test_pr_90_postgres_is_the_storage_backend_and_not_semver() -> None:
    updates = parse_dependabot_updates(POSTGRES)
    branch = "dependabot/docker_compose/postgres-18.6-alpine"
    assert dependabot(branch, ["compose.yaml"], updates) == "human"


def test_pr_91_a_minor_python_image_is_a_new_python() -> None:
    """3.12 to 3.14 is `semver-minor` to Dependabot, and a new interpreter to us."""
    updates = [Update("python", "semver-minor")]
    branch = "dependabot/docker/images-8366ca2852"
    assert dependabot(branch, ["Dockerfile"], updates) == "human"


def test_a_patch_python_image_may_merge() -> None:
    updates = [Update("python", "semver-patch")]
    branch = "dependabot/docker/images-0000000000"
    assert dependabot(branch, ["Dockerfile"], updates) == "auto"


@pytest.mark.parametrize(
    ("branch", "name", "size"),
    [
        ("dependabot/github_actions/astral-sh/setup-uv-10.2.0", "astral-sh/setup-uv", "major"),
        ("dependabot/github_actions/actions/checkout-7.0.1", "actions/checkout", "major"),
        ("dependabot/github_actions/actions-abc", "actions/checkout", "patch"),
    ],
)
def test_prs_92_93_an_action_update_rewrites_ci(branch: str, name: str, size: str) -> None:
    updates = [Update(name, f"semver-{size}")]
    assert dependabot(branch, [".github/workflows/ci.yml"], updates) == "human"


def test_dependabot_without_metadata_goes_to_a_person() -> None:
    """Someone pushed on top of Dependabot's commit, so the head carries no metadata."""
    assert dependabot("dependabot/uv/python-2f924b9b90", ["uv.lock"], []) == "human"


def test_another_bot_is_not_dependabot() -> None:
    assert tier(author="renovate[bot]") == "human"


# --- What a verdict may do ----------------------------------------------------------------

APPROVE = {"verdict": "approve", "findings": [{"severity": "nit", "file": "a", "title": "t"}]}
IMPORTANT = {"severity": "important", "file": "a.py", "line": 3, "title": "t"}
CHANGES = {"verdict": "changes", "findings": [IMPORTANT]}


def test_an_approval_merges_only_in_the_auto_tier() -> None:
    assert decide(tier="auto", verdict=APPROVE, dependabot=False, rounds=0) == "merge"
    assert decide(tier="human", verdict=APPROVE, dependabot=False, rounds=0) == "escalate"


def test_an_approval_carrying_an_important_finding_is_not_one() -> None:
    verdict = {"verdict": "approve", "findings": [IMPORTANT]}
    assert decide(tier="auto", verdict=verdict, dependabot=False, rounds=0) == "fix"


def test_changes_are_fixed_twice_then_escalated() -> None:
    assert decide(tier="auto", verdict=CHANGES, dependabot=False, rounds=0) == "fix"
    assert decide(tier="auto", verdict=CHANGES, dependabot=False, rounds=1) == "fix"
    assert decide(tier="auto", verdict=CHANGES, dependabot=False, rounds=2) == "escalate"


def test_dependabot_is_never_fixed() -> None:
    assert decide(tier="auto", verdict=CHANGES, dependabot=True, rounds=0) == "escalate"


def test_escalate_and_a_missing_verdict_go_to_a_person() -> None:
    verdict = {"verdict": "escalate", "findings": []}
    assert decide(tier="auto", verdict=verdict, dependabot=False, rounds=0) == "escalate"
    assert decide(tier="auto", verdict={}, dependabot=False, rounds=0) == "escalate"


def test_fix_rounds_are_counted_from_trailers() -> None:
    messages = ["Add a thing", "Address review findings, round 1\n\nReview-Round: 1\n", ""]
    assert fix_rounds(messages) == 1
    assert fix_rounds(["Add a thing"]) == 0


def test_only_a_bot_comment_marks_a_commit_reviewed() -> None:
    sha = "a" * 40
    marker = f"<!-- cfokit-review sha={sha} -->"
    assert reviewed_shas([{"user": {"type": "Bot"}, "body": marker}]) == {sha}
    assert reviewed_shas([{"user": {"type": "User"}, "body": marker}]) == set()
