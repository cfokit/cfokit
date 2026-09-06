"""Configuration invariants that no running system can observe (ADR-0018, ADR-0019).

A test inside the compose network sees every address as the network resolves it, which is
exactly the view that makes a mapped port look correct. The failure it hides is that the same
address means something else from outside — and on a network where one service's internal port
is another's published port, "something else" is a different service answering confidently.

So these read the compose file. Nothing here starts a container: what is under test is what the
file *says*, because that is what a client is handed and what an operator copies.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "compose.yaml"


def lines() -> list[str]:
    """The compose file, by line.

    PyYAML is not a dependency and does not become one for this. The properties under test are
    addresses, and an address is found by reading the line that carries it — which is also what
    an operator does.
    """
    return COMPOSE.read_text(encoding="utf-8").splitlines()


def setting(name: str) -> str:
    """One environment default from compose, as `NAME: ${NAME:-default}` or `NAME: value`."""
    for line in lines():
        stripped = line.strip()
        if not stripped.startswith(f"{name}:"):
            continue
        value = stripped.split(":", 1)[1].strip().strip('"')
        if value.startswith("${") and ":-" in value:
            return value.split(":-", 1)[1].rstrip("}")
        return value
    pytest.fail(f"{name} is not set in compose.yaml")


def published(service_port: str) -> str:
    """The host side of a `"host:container"` port mapping, found by its container side."""
    for line in lines():
        stripped = line.strip().strip('"- ')
        if stripped.endswith(f":{service_port}") and ":" in stripped:
            host, _, _ = stripped.rpartition(":")
            if host.startswith("${") and ":-" in host:
                return host.split(":-", 1)[1].rstrip("}")
            return host
    pytest.fail(f"nothing is published to container port {service_port}")


def test_the_issuer_is_reachable_at_the_same_address_inside_and_out() -> None:
    """**The invariant a mapped port breaks.**

    A client is handed the issuer's address in the ledger's protected-resource metadata and
    goes to it directly, so it has to resolve to the issuer from wherever that client sits.
    The address comes from `AUTH_ISSUER_URL`, which is also where *this* process fetches JWKS
    — one string serving an inside view and an outside one.

    Mapping the container's port to a different host port breaks it for exactly one side, and
    silently: on this network 8080 is the ledger, so a browser following the chain to
    `keycloak:8080` reaches the ledger and is answered.
    """
    issuer_port = urlparse(setting("AUTH_ISSUER_URL")).port
    container_port = setting("KC_HTTP_PORT")

    assert str(issuer_port) == container_port, (
        f"AUTH_ISSUER_URL names port {issuer_port} and the issuer listens on {container_port}"
    )
    assert published(container_port) == container_port, (
        f"the issuer's port {container_port} is published on a different host port, so its"
        " advertised address means one thing inside the network and another outside it"
    )


def test_the_issuer_and_the_ledger_do_not_share_a_port() -> None:
    """Two services on one port is how the address above stops being ambiguous and starts
    being wrong: the wrong service answers rather than nothing answering."""
    issuer = setting("KC_HTTP_PORT")
    ledger = urlparse(setting("PUBLIC_BASE_URL")).port

    assert str(ledger) != issuer


def test_every_service_reads_the_same_issuer() -> None:
    """`AUTH_ISSUER_URL` is validated against a token's `iss` on every request (ADR-0019). Two
    services configured with different values would accept different tokens, and the one that
    accepted fewer would look like an intermittent fault."""
    values = {
        line.split(":", 1)[1].strip()
        for line in lines()
        if line.strip().startswith("AUTH_ISSUER_URL:")
    }

    assert len(values) == 1, f"services disagree about the issuer: {values}"
