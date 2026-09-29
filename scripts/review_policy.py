#!/usr/bin/env python3
"""Decides whether a pull request may merge without a person (ADR-0048).

The reviewing model can withhold approval; it cannot grant eligibility. Eligibility is this
file's job, and it is deterministic so that nothing a pull request says — in its title, its
body, its commit messages, or the release notes a reviewer fetches — can talk it into one.

Three subcommands, each called by `.github/workflows/review.yml`:

- ``classify``  the tier: ``auto`` (may merge on the reviewer's approval) or ``human``.
- ``select``    which pull requests a run reviews: the one named, or, for the weekly sweep,
                every open Dependabot pull request with no verdict at its head commit.
- ``decide``    what to do with a verdict: ``merge``, ``fix`` or ``escalate``, and the review
                comment that records it.

The workflow runs this file from a checkout of ``main``, never from the pull request, so a
pull request cannot rewrite the policy it is judged by. The pull request's files are data.

Standard library only: adding a dependency is a decision (CLAUDE.md), and this is not one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

DEPENDABOT = "dependabot[bot]"

# Ecosystems whose non-major updates may merge on approval. Everything else goes to a person:
# `github_actions` rewrites CI itself (and `.github/` is code-owned regardless), and
# `docker_compose` moves Postgres, the only storage backend (ADR-0003), and Keycloak, the
# issuer (ADR-0019), which CLAUDE.md puts behind human review.
AUTO_ECOSYSTEMS = {"uv": {"semver-patch", "semver-minor"}, "docker": {"semver-patch"}}

# A fix round is a commit carrying this trailer. Two rounds, then a person (ADR-0048).
ROUND_TRAILER = re.compile(r"^Review-Round: (\d+)$", re.MULTILINE)
MAX_FIX_ROUNDS = 2

# The verdict marker a review comment carries, so a head commit is never reviewed twice.
MARKER = "<!-- cfokit-review sha={sha} -->"
MARKER_PATTERN = re.compile(r"<!-- cfokit-review sha=([0-9a-f]{40}) -->")

# A PEP 508 requirement's identity: its name and any extras. The version is what changes.
REQUIREMENT_IDENTITY = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?")


@dataclass(frozen=True)
class Update:
    name: str
    update_type: str | None  # "semver-patch" | "semver-minor" | "semver-major" | None


@dataclass(frozen=True)
class Classification:
    tier: str  # "auto" | "human"
    reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# Pure policy
# ---------------------------------------------------------------------------


def parse_codeowners(text: str) -> list[str]:
    """The path patterns in a CODEOWNERS file. Owners are irrelevant here; ownership is.

    Only the forms this repository uses are understood: an anchored directory (``/infra/``),
    an anchored file (``/REVIEW.md``), and a bare file name matching at any depth
    (``CLAUDE.md``). Anything else is refused rather than guessed at, because a pattern this
    reader silently misread would silently unprotect a path.
    """
    patterns: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pattern = line.split()[0]
        if any(c in pattern for c in "*?[!"):
            raise ValueError(f"unsupported CODEOWNERS pattern {pattern!r}")
        if not pattern.startswith("/") and "/" in pattern:
            raise ValueError(f"unsupported CODEOWNERS pattern {pattern!r}")
        patterns.append(pattern)
    return patterns


def protecting_pattern(path: str, patterns: list[str]) -> str | None:
    """The first pattern that owns ``path``, or None if no one does."""
    for pattern in patterns:
        if pattern.endswith("/"):
            if ("/" + path).startswith(pattern):
                return pattern
        elif pattern.startswith("/"):
            if "/" + path == pattern:
                return pattern
        elif PurePosixPath(path).name == pattern:
            return pattern
    return None


def parse_dependabot_updates(commit_message: str) -> list[Update]:
    """The ``updated-dependencies`` block Dependabot writes into its commit message.

    It is YAML, but a fixed and flat shape, so it is read line by line rather than adding a
    YAML parser. A missing ``update-type`` is kept as None: Dependabot omits it when a
    version is not semver (``postgres`` ``18.6-alpine``), and an unknown size is not small.
    """
    updates: list[Update] = []
    name: str | None = None
    update_type: str | None = None
    in_block = False
    for line in commit_message.splitlines():
        if line.strip() == "updated-dependencies:":
            in_block = True
            continue
        if not in_block:
            continue
        if line.startswith("- dependency-name:"):
            if name is not None:
                updates.append(Update(name, update_type))
            name = line.split(":", 1)[1].strip().strip("'\"")
            update_type = None
        elif line.strip().startswith("update-type:"):
            update_type = line.split(":", 1)[1].strip().removeprefix("version-update:")
        elif not line.startswith(" ") and not line.startswith("-"):
            break
    if name is not None:
        updates.append(Update(name, update_type))
    return updates


def ecosystem(branch: str) -> str | None:
    """Dependabot names its branches ``dependabot/<ecosystem>/...``."""
    parts = branch.split("/")
    if len(parts) >= 3 and parts[0] == "dependabot":
        return parts[1]
    return None


def _requirement_identities(requirements: list[Any]) -> list[Any]:
    identities: list[Any] = []
    for requirement in requirements:
        if isinstance(requirement, str) and (match := REQUIREMENT_IDENTITY.match(requirement)):
            identities.append(match.group(1).lower().replace("_", "-") + (match.group(2) or ""))
        else:
            identities.append(requirement)
    return identities


def pyproject_shape(text: str) -> dict[str, Any]:
    """``pyproject.toml`` with every dependency's version removed.

    Two files with the same shape differ only in versions. Anything else — a dependency
    added, an extra, a task, a lint rule, a gate's configuration — is a different shape.
    """
    shape = tomllib.loads(text)
    project = shape.get("project", {})
    if "dependencies" in project:
        project["dependencies"] = _requirement_identities(project["dependencies"])
    for extra, requirements in project.get("optional-dependencies", {}).items():
        project["optional-dependencies"][extra] = _requirement_identities(requirements)
    for group, requirements in shape.get("dependency-groups", {}).items():
        shape["dependency-groups"][group] = _requirement_identities(requirements)
    return shape


def classify(
    *,
    author: str,
    branch: str,
    changed: list[str],
    protected: list[str],
    updates: list[Update],
    pyproject_reshaped: bool,
    new_runtime_packages: set[str],
) -> Classification:
    """The tier. Every reason found is reported, not just the first."""
    reasons: list[str] = []

    for path in changed:
        if pattern := protecting_pattern(path, protected):
            reasons.append(f"`{path}` is code-owned (`{pattern}`)")

    if pyproject_reshaped:
        reasons.append("`pyproject.toml` changes more than versions")
    if new_runtime_packages:
        names = ", ".join(sorted(new_runtime_packages))
        reasons.append(f"new runtime packages: {names} — adding one is a decision (CLAUDE.md)")

    if author == DEPENDABOT:
        eco = ecosystem(branch)
        allowed = AUTO_ECOSYSTEMS.get(eco or "")
        if allowed is None:
            reasons.append(f"Dependabot `{eco}` updates always go to a person")
        elif not updates:
            reasons.append("Dependabot commit carries no update metadata")
        else:
            for update in updates:
                if update.update_type not in allowed:
                    size = update.update_type or "non-semver"
                    reasons.append(f"`{update.name}` is a {size} update of `{eco}`")
    elif author.endswith("[bot]"):
        reasons.append(f"authored by `{author}`, which is not Dependabot")

    return Classification("human" if reasons else "auto", tuple(reasons))


def fix_rounds(commit_messages: list[str]) -> int:
    rounds = [int(m.group(1)) for msg in commit_messages if (m := ROUND_TRAILER.search(msg))]
    return max(rounds, default=0)


def decide(*, tier: str, verdict: dict[str, Any], dependabot: bool, rounds: int) -> str:
    """``merge``, ``fix`` or ``escalate``.

    An approval that carries an Important finding is not an approval. A fix is attempted only
    on a pull request a person wrote with an agent — never on Dependabot's, which Dependabot
    rebases over — and only twice.
    """
    important = [f for f in verdict.get("findings", []) if f.get("severity") == "important"]
    if verdict.get("verdict") == "approve" and not important:
        return "merge" if tier == "auto" else "escalate"
    if verdict.get("verdict") == "escalate" or dependabot or rounds >= MAX_FIX_ROUNDS:
        return "escalate"
    return "fix" if important else "escalate"


def render(
    *,
    sha: str,
    classification: Classification,
    verdict: dict[str, Any],
    action: str,
    mode: str,
) -> str:
    """The review comment. It carries the marker that makes a head commit's review final."""
    lines = [MARKER.format(sha=sha), f"### Review of `{sha[:7]}`: {verdict.get('verdict')}"]
    lines.append("")
    lines.append(str(verdict.get("summary", "")).strip())
    findings = verdict.get("findings", [])
    if findings:
        lines += ["", "| Severity | Where | Finding |", "|---|---|---|"]
        for f in findings:
            where = f"`{f.get('file', '')}:{f.get('line', '')}`"
            title = str(f.get("title", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {f.get('severity')} | {where} | {title} |")
        details = [f for f in findings if f.get("detail")]
        if details:
            lines += ["", "<details><summary>Detail</summary>", ""]
            for f in details:
                lines += [f"**{f.get('title', '')}**", "", str(f["detail"]).strip(), ""]
            lines.append("</details>")
    lines += ["", f"**Tier:** {classification.tier}"]
    lines += [f"- {reason}" for reason in classification.reasons]
    outcome = {
        "merge": "Approved; auto-merge waits for **All gates**.",
        "fix": "Important findings on an agent-authored change: a fix round follows.",
        "escalate": "@geoffscott — this one needs you.",
    }[action]
    if mode != "enforce":
        outcome = f"Shadow mode — would have done: {outcome}"
    lines += ["", f"**Outcome:** {outcome}"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# I/O, called by the workflow
# ---------------------------------------------------------------------------


def _run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _gh_json(*args: str) -> Any:
    return json.loads(_run("gh", *args))


def _runtime_packages(pyproject: str, lock: str) -> set[str]:
    """The runtime closure, the same way CLAUDE.md counts it. ``--frozen`` reads the lock
    and resolves nothing, so no code from the pull request runs."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "pyproject.toml").write_text(pyproject)
        Path(tmp, "uv.lock").write_text(lock)
        exported = _run(
            "uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes",
            "--project", tmp,
        )  # fmt: skip
    return {line.split("==")[0] for line in exported.splitlines() if re.match(r"^[a-z]", line)}


def _output(**values: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    text = "".join(f"{k}<<__EOF__\n{v}\n__EOF__\n" for k, v in values.items())
    if target:
        with Path(target).open("a") as handle:
            handle.write(text)
    else:
        print(text, end="")


def cmd_classify(args: argparse.Namespace) -> None:
    pr = _gh_json(
        "pr", "view", str(args.pr), "--json", "author,headRefName,baseRefOid,headRefOid"
    )
    author = pr["author"]["login"]
    # `gh` reports apps as `app/<slug>`; the REST API, and this policy, as `<slug>[bot]`.
    if author.startswith("app/"):
        author = author.removeprefix("app/") + "[bot]"
    base, head = pr["baseRefOid"], pr["headRefOid"]
    repo = Path(args.head_dir)

    changed = _run("git", "diff", "--name-only", "--no-renames", f"{base}...{head}", cwd=repo)
    changed_paths = [p for p in changed.splitlines() if p]
    protected = parse_codeowners(Path(args.codeowners).read_text())

    def at(ref: str, path: str) -> str:
        return _run("git", "show", f"{ref}:{path}", cwd=repo)

    merge_base = _run("git", "merge-base", base, head, cwd=repo).strip()
    reshaped = False
    new_runtime: set[str] = set()
    if "pyproject.toml" in changed_paths:
        reshaped = pyproject_shape(at(merge_base, "pyproject.toml")) != pyproject_shape(
            at(head, "pyproject.toml")
        )
    if {"pyproject.toml", "uv.lock"} & set(changed_paths):
        before = _runtime_packages(at(merge_base, "pyproject.toml"), at(merge_base, "uv.lock"))
        after = _runtime_packages(at(head, "pyproject.toml"), at(head, "uv.lock"))
        new_runtime = after - before

    updates: list[Update] = []
    if author == DEPENDABOT:
        updates = parse_dependabot_updates(
            _run("git", "log", "-1", "--format=%B", head, cwd=repo)
        )
    messages = _run("git", "log", "--format=%B%x00", f"{merge_base}..{head}", cwd=repo)
    result = classify(
        author=author,
        branch=pr["headRefName"],
        changed=changed_paths,
        protected=protected,
        updates=updates,
        pyproject_reshaped=reshaped,
        new_runtime_packages=new_runtime,
    )
    _output(
        tier=result.tier,
        reasons=json.dumps(result.reasons),
        dependabot=str(author == DEPENDABOT).lower(),
        rounds=str(fix_rounds(messages.split("\x00"))),
        sha=head,
        branch=pr["headRefName"],
    )


def reviewed_shas(comments: list[dict[str, Any]]) -> set[str]:
    """Head commits that already carry a verdict. Only a bot's comment counts: anyone can
    comment on a public repository, and a forged marker must not be able to skip a review
    — though skipping one only withholds an approval, so it fails safe either way."""
    shas: set[str] = set()
    for comment in comments:
        if comment.get("user", {}).get("type") == "Bot":
            shas.update(MARKER_PATTERN.findall(comment.get("body", "")))
    return shas


def cmd_select(args: argparse.Namespace) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    if args.pr:
        candidates = [int(args.pr)]
    else:
        listed = _gh_json(
            "pr", "list", "--state", "open", "--author", "app/dependabot", "--json", "number"
        )
        candidates = [p["number"] for p in listed]
    selected: list[int] = []
    for number in candidates:
        pr = _gh_json("pr", "view", str(number), "--json", "headRefOid,isCrossRepository,state")
        if pr["isCrossRepository"] or pr["state"] != "OPEN":
            continue
        comments = _gh_json(
            "api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/comments"
        )
        flat = [c for page in comments for c in page]
        if pr["headRefOid"] in reviewed_shas(flat):
            print(f"#{number}: verdict exists at {pr['headRefOid'][:7]}; skipped")
            continue
        selected.append(number)
    _output(prs=json.dumps(selected), any=str(bool(selected)).lower())


def cmd_decide(args: argparse.Namespace) -> None:
    verdict = json.loads(os.environ.get("VERDICT") or "{}")
    if not verdict:
        verdict = {"verdict": "escalate", "summary": "The reviewer returned no verdict."}
    classification = Classification(
        os.environ["TIER"], tuple(json.loads(os.environ["REASONS"]))
    )
    action = decide(
        tier=classification.tier,
        verdict=verdict,
        dependabot=os.environ["DEPENDABOT"] == "true",
        rounds=int(os.environ["ROUNDS"]),
    )
    body = render(
        sha=os.environ["SHA"],
        classification=classification,
        verdict=verdict,
        action=action,
        mode=os.environ.get("REVIEW_MODE", "shadow"),
    )
    Path(args.body).write_text(body)
    _output(action=action)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("classify")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--head-dir", required=True)
    p.add_argument("--codeowners", required=True)
    p.set_defaults(func=cmd_classify)
    p = sub.add_parser("select")
    p.add_argument("--pr", default="")
    p.set_defaults(func=cmd_select)
    p = sub.add_parser("decide")
    p.add_argument("--body", required=True)
    p.set_defaults(func=cmd_decide)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, ValueError) as error:
        print(f"review_policy: {error}", file=sys.stderr)
        sys.exit(1)
