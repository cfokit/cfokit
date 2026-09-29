"""The importer's sign-in and posting loop (ADR-0041 § 5).

Driven against a stub issuer and a stub CFOKit, both `http.server` in a thread. That is
enough to test what belongs to the script — discovery, the device-code poll, batching, and
how a refusal is reported — without a Keycloak or a database, so it gates every commit.

What it deliberately does not test is whether Keycloak implements RFC 8628. That is the issuer's
half of the contract and `tests/integration/test_issuer_conformance.py` measures it against the
real one.
"""

from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# `tests` is deliberately not a package, so this is an absolute import: pytest puts the test
# file's own directory on `sys.path` under the default import mode. mypy does not resolve it
# that way and adding `tests` to `mypy_path` shadows `tests/conftest.py`, so the ignore is
# narrower than the alternative.
from test_reader_script import SCRIPT, SKILL_PYTHON, export  # type: ignore[import-not-found]

Recorded = list[tuple[str, str, Any]]


class Stub(BaseHTTPRequestHandler):
    """One handler standing in for both the issuer and CFOKit."""

    script: Any = None

    def log_message(self, *args: Any) -> None:
        pass

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        self.server.seen.append(("GET", path, None))  # type: ignore[attr-defined]
        if path == "/.well-known/oauth-protected-resource":
            base = f"http://{self.headers['Host']}"
            self._send(200, {"resource": base, "authorization_servers": [base + "/issuer"]})
        elif path == "/issuer/.well-known/openid-configuration":
            base = f"http://{self.headers['Host']}"
            self._send(
                200,
                {
                    "issuer": base + "/issuer",
                    "token_endpoint": base + "/issuer/token",
                    "device_authorization_endpoint": base + "/issuer/device",
                },
            )
        else:
            self._send(404, {"code": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        content = self.headers.get("Content-Type", "")
        body: Any
        if "form-urlencoded" in content:
            body = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
        else:
            body = json.loads(raw) if raw else {}
        self.server.seen.append(("POST", path, body))  # type: ignore[attr-defined]
        self._send(*self.server.reply(path, body, self.headers))  # type: ignore[attr-defined]


def serve(reply: Any) -> Any:
    server = HTTPServer(("127.0.0.1", 0), Stub)
    server.seen = []  # type: ignore[attr-defined]
    server.reply = reply  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def base_of(server: Any) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def run(server: Any, archive: bytes, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "export.zip"
    source.write_bytes(archive)
    return subprocess.run(  # noqa: S603 - our own script, at a path this file computes
        [
            SKILL_PYTHON,
            str(SCRIPT),
            str(source),
            "--post",
            base_of(server),
            "--entity",
            "e-1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def happy(pending: int = 0) -> Any:
    """An issuer that approves after `pending` polls, and a CFOKit that accepts everything."""
    state = {"polls": 0}

    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        if path == "/issuer/device":
            return 200, {
                "device_code": "d",
                "user_code": "WXYZ-1234",
                "verification_uri": "http://example.test/device",
                "interval": 0,
            }
        if path == "/issuer/token":
            state["polls"] += 1
            if state["polls"] <= pending:
                return 400, {"error": "authorization_pending"}
            return 200, {"access_token": "a-persons-token"}
        assert headers.get("Authorization") == "Bearer a-persons-token"
        if path.endswith("/imports"):
            return 201, {
                "import_id": "i-1",
                "accounts_created": len(body["accounts"]),
                "accounts_already_present": 0,
            }
        if path.endswith("/entries"):
            return 200, {"posted": len(body["entries"]), "replayed": 0, "refusals": []}
        return 200, {"agreed": 3, "compared": 3, "divergences": [], "statements": []}

    return reply


# --- signing in ------------------------------------------------------------------------------


def test_it_discovers_the_issuer_from_the_resource(tmp_path: Path) -> None:
    """RFC 9728. Handing an operator a second URL to configure is the kind of setup step that
    does not survive contact with one."""
    server = serve(happy())
    run(server, export(), tmp_path)

    assert ("GET", "/.well-known/oauth-protected-resource", None) in server.seen
    assert ("GET", "/issuer/.well-known/openid-configuration", None) in server.seen


def test_it_signs_in_as_a_public_client_with_no_secret(tmp_path: Path) -> None:
    """A public client, which is why it can ship in the realm file at all."""
    server = serve(happy())
    run(server, export(), tmp_path)

    started = next(b for m, p, b in server.seen if p == "/issuer/device" and m == "POST")
    assert started == {"client_id": "cfokit-importer"}
    assert "client_secret" not in started


def test_it_shows_the_person_a_code_to_approve(tmp_path: Path) -> None:
    server = serve(happy())
    done = run(server, export(), tmp_path)

    assert "WXYZ-1234" in done.stderr
    assert "http://example.test/device" in done.stderr


def test_it_waits_while_the_approval_is_pending(tmp_path: Path) -> None:
    """`authorization_pending` is the ordinary case, not a failure: the person is still reading
    the screen."""
    server = serve(happy(pending=3))
    done = run(server, export(), tmp_path)

    assert done.returncode == 0
    assert len([1 for m, p, _ in server.seen if p == "/issuer/token"]) == 4


def test_a_refused_sign_in_stops_rather_than_polling_on(tmp_path: Path) -> None:
    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        if path == "/issuer/device":
            return 200, {
                "device_code": "d",
                "user_code": "X",
                "verification_uri": "u",
                "interval": 0,
            }
        return 400, {"error": "access_denied"}

    server = serve(reply)
    done = run(server, export(), tmp_path)

    assert done.returncode == 1
    assert "not_authenticated" in done.stderr


def test_an_issuer_without_device_flow_says_so(tmp_path: Path) -> None:
    """RFC 8252 loopback is the documented fallback, and an operator needs to be told which
    problem they have."""

    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        return 200, {}

    class NoDevice(Stub):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            base = f"http://{self.headers['Host']}"
            if path == "/.well-known/oauth-protected-resource":
                self._send(200, {"authorization_servers": [base + "/issuer"]})
            else:
                self._send(200, {"token_endpoint": base + "/issuer/token"})

    server = HTTPServer(("127.0.0.1", 0), NoDevice)
    server.seen = []  # type: ignore[attr-defined]
    server.reply = reply  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    done = run(server, export(), tmp_path)

    assert done.returncode == 1
    assert "device authorization" in done.stderr


# --- posting ---------------------------------------------------------------------------------


def test_it_opens_then_batches_then_reconciles(tmp_path: Path) -> None:
    server = serve(happy())
    done = run(server, export(), tmp_path)

    posts = [p for m, p, _ in server.seen if m == "POST" and "issuer" not in p]
    assert posts == [
        "/entities/e-1/imports",
        "/entities/e-1/imports/i-1/entries",
        "/entities/e-1/imports/i-1/reconciliation",
    ]
    assert done.returncode == 0


def test_the_opening_call_carries_no_entries(tmp_path: Path) -> None:
    """A company's whole journal in one request is the shape this design exists to avoid."""
    server = serve(happy())
    run(server, export(), tmp_path)

    opened = next(b for m, p, b in server.seen if p == "/entities/e-1/imports")
    assert "entries" not in opened
    assert opened["shape_version"] == "1"
    assert opened["accounts"]


def test_every_amount_leaves_as_a_string(tmp_path: Path) -> None:
    """A JSON number is a float in most parsers, and a float's binary expansion is not the
    figure the workbook shows (ADR-0005)."""
    server = serve(happy())
    run(server, export(), tmp_path)

    batch = next(b for m, p, b in server.seen if p.endswith("/entries"))
    for entry in batch["entries"]:
        for line in entry["lines"]:
            assert isinstance(line["amount"], str)


def test_a_refusal_from_the_server_is_reported_with_its_code(tmp_path: Path) -> None:
    """The code is what a caller branches on (ADR-0015), so it is what a person is shown."""

    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        if path.startswith("/issuer"):
            reply: tuple[int, dict[str, Any]] = happy()(path, body, headers)
            return reply
        return 422, {"code": "import_refused", "message": "the source states cash basis"}

    server = serve(reply)
    done = run(server, export(), tmp_path)

    assert done.returncode == 1
    assert "import_refused" in done.stderr
    assert "cash basis" in done.stderr


def test_a_divergence_makes_the_run_fail(tmp_path: Path) -> None:
    """`NFR-01`: a disagreement is resolved, never tolerated — so it cannot exit zero."""

    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        if path.startswith("/issuer") or not path.endswith("reconciliation"):
            reply: tuple[int, dict[str, Any]] = happy()(path, body, headers)
            return reply
        return 200, {
            "agreed": 2,
            "compared": 3,
            "divergences": [{"account_code": "Checking", "ours": "100.00", "theirs": "90.00"}],
            "statements": [],
        }

    server = serve(reply)
    done = run(server, export(), tmp_path)

    assert done.returncode == 1
    assert "DIVERGES Checking" in done.stderr
    assert "ours 100.00 theirs 90.00" in done.stderr


def test_skipped_rows_are_reported(tmp_path: Path) -> None:
    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        if path.startswith("/issuer") or not path.endswith("/entries"):
            reply: tuple[int, dict[str, Any]] = happy()(path, body, headers)
            return reply
        return 200, {
            "posted": 1,
            "replayed": 0,
            "refusals": [
                {
                    "reference": "7",
                    "date": "2026-01-01",
                    "code": "unbalanced",
                    "detail": "debits and credits differ by 1.00",
                }
            ],
        }

    server = serve(reply)
    done = run(server, export(), tmp_path)

    assert done.returncode == 1
    assert "skipped 7: unbalanced" in done.stderr


def test_a_replayed_batch_is_reported_apart_from_a_posted_one(tmp_path: Path) -> None:
    """ "Nothing happened, it was already done" and "the books changed" are different answers,
    and a person about to tell someone what changed needs to tell them apart."""

    def reply(path: str, body: Any, headers: Any) -> tuple[int, dict[str, Any]]:
        if path.startswith("/issuer") or not path.endswith("/entries"):
            reply: tuple[int, dict[str, Any]] = happy()(path, body, headers)
            return reply
        return 200, {"posted": 0, "replayed": len(body["entries"]), "refusals": []}

    server = serve(reply)
    done = run(server, export(), tmp_path)

    assert "posted 0, replayed 2" in done.stderr


def test_the_person_sees_the_summary_before_approving(tmp_path: Path) -> None:
    """`IMP-05`: the operator sees what will happen and can abandon it. Printed before the
    sign-in, because after it the books are already changing."""
    server = serve(happy())
    done = run(server, export(), tmp_path)

    summary_at = done.stderr.index("2 transactions")
    approve_at = done.stderr.index("WXYZ-1234")
    assert summary_at < approve_at


def test_nothing_is_cached_between_runs(tmp_path: Path) -> None:
    """One sign-in per run. A standing refresh token in an agent's runtime buys convenience on
    an operation a company performs about once."""
    server = serve(happy())
    run(server, export(), tmp_path)
    run(server, export(), tmp_path)

    assert len([1 for m, p, _ in server.seen if p == "/issuer/device"]) == 2
