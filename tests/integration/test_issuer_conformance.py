"""The issuer conformance suite: `infra/README.md`'s contract, measured (ADR-0019).

> "The issuer is a **swappable dependency**, not a chosen product… No issuer-specific code
> exists anywhere in the codebase."

That claim is only true if something checks it, and the document said a suite did before one
existed. This is that suite. It drives the configured issuer over HTTP and asserts each line of
the contract, so swapping an issuer is a thing a self-hoster can verify rather than a thing we
assert on their behalf.

**Nothing here knows what Ory Hydra is.** Every request goes to an endpoint the issuer itself
advertises, which is the same discipline the contract demands of the application. A suite that
reached for a vendor's admin API would prove the default works and nothing about the swap.

**Two layers, because the second depends on the first.** Metadata conformance needs no client
and always runs. Token conformance needs one, and obtains it through RFC 7591 dynamic client
registration — itself a contract line. An issuer that advertises no registration endpoint fails
that line and cannot support the second layer at all, which is a diagnosis rather than a gap.

**`xfail(strict=True)` marks a contract line the shipped default does not meet.** Not a
schedule: the marker states a measured fact about a dependency, and `strict` means the suite
fails if the line ever starts passing, forcing the marker off rather than letting it rot.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.integration

ISSUER = os.environ.get("AUTH_ISSUER_URL", "").rstrip("/")
TIMEOUT = 10

# Where to register a client when the issuer does not advertise it.
#
# Not a workaround for the contract line below, which still fails: an unadvertised endpoint is
# unusable by a client, and the metadata test says so. This is what lets the *token* layer run
# anyway, so the most important line — whether `resource` binds the audience — is measured
# rather than skipped behind an earlier failure. The operator states it, not the suite: this
# file still knows nothing about what the issuer is, and the MCP authorization spec names
# exactly this fallback for issuers that do not support registration discovery.
FALLBACK_REGISTRATION = os.environ.get("AUTH_REGISTRATION_ENDPOINT", "")

# The canonical URI an MCP client sends as `resource` (RFC 8707), and the audience the token
# must come back bound to. Any value works for the test; what matters is that the issuer
# reflects it rather than ignoring it.
RESOURCE = "https://cfokit.test/mcp"


@pytest.fixture(autouse=True)
def _requires_issuer() -> None:
    """Skip unless an issuer is configured and reachable.

    A developer without the stack up gets a skip; CI gate 2 brings the issuer up, so there the
    suite runs for real.
    """
    if not ISSUER:
        pytest.skip("needs an issuer: docker compose --profile test run --rm test")
    try:
        httpx.get(f"{ISSUER}/health/ready", timeout=TIMEOUT)
    except httpx.HTTPError:  # pragma: no cover - environment dependent
        pytest.skip(f"issuer at {ISSUER} is not reachable")


def get(url: str) -> tuple[int, dict[str, Any]]:
    """One GET, returning the status and whatever JSON came back.

    A non-200 is data here rather than an error: several contract lines are about *whether* an
    endpoint exists, and an exception would make "absent" indistinguishable from "broken".
    """
    response = httpx.get(url, headers={"accept": "application/json"}, timeout=TIMEOUT)
    return response.status_code, _json(response)


def post(
    url: str, payload: dict[str, Any] | None = None, form: dict[str, str] | None = None
) -> tuple[int, dict[str, Any]]:
    """One POST, as JSON or as a form. Same tolerance for a refusal as `get`."""
    response = (
        httpx.post(url, data=form, timeout=TIMEOUT)
        if form is not None
        else httpx.post(url, json=payload or {}, timeout=TIMEOUT)
    )
    return response.status_code, _json(response)


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def claims(token: str) -> dict[str, Any]:
    """The claims inside a JWT, without verifying it.

    Deliberately unverified: what is under test is what the issuer *put* in the token, and
    verification is the application's job — `TokenAuthenticator` does it against JWKS, and
    `tests/test_authentication.py` covers that path.

    An opaque token fails here with a readable message rather than a decoding error, because
    "this issuer does not issue JWTs" is a contract answer and not a bug in the test.
    """
    parts = token.split(".")
    assert len(parts) == 3, "access token is not a JWT; see the JWT access token test"
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload))
    assert isinstance(decoded, dict)
    return decoded


@pytest.fixture
def metadata() -> dict[str, Any]:
    """The issuer's own description of itself, from whichever document it serves.

    RFC 8414 first, because that is what the MCP authorization spec requires a client to use,
    then OIDC discovery, which the contract also admits.
    """
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    ):
        status, document = get(f"{ISSUER}{path}")
        if status == 200 and document:
            return document
    pytest.fail(f"{ISSUER} serves neither authorization server metadata nor OIDC discovery")


# --- metadata: what the issuer says it does -----------------------------------------------


def test_the_issuer_describes_itself(metadata: dict[str, Any]) -> None:
    """Discovery is the first thing every client does, and the compose default once failed it
    outright — `SECRETS_SYSTEM` unset meant Hydra could not create signing keys and answered
    `server_error` to this request. Nothing downstream could work, and nothing noticed."""
    assert metadata["issuer"].rstrip("/") == ISSUER
    assert metadata["token_endpoint"]
    assert metadata["jwks_uri"]


def test_the_jwks_endpoint_serves_keys(metadata: dict[str, Any]) -> None:
    """Signature validation happens against these on every request (ADR-0019)."""
    status, jwks = get(metadata["jwks_uri"])

    assert status == 200
    assert jwks["keys"], "no signing keys published"


def test_pkce_is_offered_with_s256(metadata: dict[str, Any]) -> None:
    """The MCP authorization spec makes PKCE mandatory for clients, and `plain` is not PKCE in
    any useful sense — an interceptor who has the challenge has the verifier."""
    assert "S256" in metadata["code_challenge_methods_supported"]


def test_the_client_credentials_grant_is_offered(metadata: dict[str, Any]) -> None:
    """ADR-0032: separate components authenticate as machine callers, and ADR-0033 has an
    agent runtime obtain one token per session this way."""
    assert "client_credentials" in metadata["grant_types_supported"]


def test_the_authorization_code_grant_is_offered(metadata: dict[str, Any]) -> None:
    """How a person authorises a client — the flow every MCP client uses."""
    assert "authorization_code" in metadata["grant_types_supported"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Ory Hydra v2.3.0 serves OIDC discovery at /.well-known/openid-configuration and does "
        "not serve RFC 8414 metadata at /.well-known/oauth-authorization-server. The MCP "
        "authorization spec requires a client to use RFC 8414, so a spec-following client "
        "cannot discover this issuer. Measured, not assumed."
    ),
)
def test_authorization_server_metadata_is_served_at_the_rfc_8414_path() -> None:
    status, _ = get(f"{ISSUER}/.well-known/oauth-authorization-server")

    assert status == 200


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Ory Hydra v2.3.0 implements dynamic client registration at /oauth2/register — it "
        "answers 201 — but omits `registration_endpoint` from its metadata. A client discovers "
        "the endpoint from metadata, finds none, and concludes registration is unsupported, so "
        "an unadvertised endpoint is the same as an absent one."
    ),
)
def test_dynamic_client_registration_is_advertised(metadata: dict[str, Any]) -> None:
    """RFC 7591. Without it every client needs a credential issued by hand, which the MCP spec
    names as the friction dynamic registration exists to remove."""
    assert metadata.get("registration_endpoint")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Ory Hydra v2.3.0 does not advertise RFC 9207 support. Without the issuer identifier "
        "in the authorization response, a client holding registrations with several issuers "
        "cannot tell which one answered — the mix-up attack RFC 9207 exists to close."
    ),
)
def test_the_issuer_identifier_is_returned_in_the_authorization_response(
    metadata: dict[str, Any],
) -> None:
    """RFC 9207."""
    assert metadata.get("authorization_response_iss_parameter_supported") is True


# --- tokens: what the issuer actually issues ----------------------------------------------


@pytest.fixture
def registered(metadata: dict[str, Any]) -> tuple[str, str]:
    """A client, obtained the only way that is not issuer-specific: RFC 7591.

    An issuer advertising no registration endpoint cannot be exercised further without knowing
    what it is, which is precisely what this suite must not know. The failure is reported by
    the registration test above rather than repeated here.
    """
    endpoint = metadata.get("registration_endpoint") or FALLBACK_REGISTRATION
    if not endpoint:
        pytest.skip(
            "issuer advertises no registration endpoint and none is configured;"
            " see the RFC 7591 test"
        )

    status, client = post(
        endpoint,
        {
            "client_name": "cfokit-conformance",
            "grant_types": ["client_credentials"],
            "response_types": ["token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert status in (200, 201), f"registration refused: {status} {client}"
    return client["client_id"], client["client_secret"]


def test_a_registered_client_can_obtain_a_token(
    metadata: dict[str, Any], registered: tuple[str, str]
) -> None:
    client_id, secret = registered

    status, response = post(
        metadata["token_endpoint"],
        form={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        },
    )

    assert status == 200, response
    assert response["access_token"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Ory Hydra v2.3.0 ignores the RFC 8707 `resource` parameter and returns aud: []. It "
        "honours its own non-standard `audience` parameter instead. The MCP authorization spec "
        "requires a client to send `resource`, and CFOKit validates the audience on every "
        "request (ADR-0011, ADR-0019) — so a spec-following MCP client is issued a token this "
        "deployment must reject. Measured against the shipped default."
    ),
)
def test_the_resource_parameter_binds_the_token_audience(
    metadata: dict[str, Any], registered: tuple[str, str]
) -> None:
    """**The contract line that matters most.**

    Audience binding is what stops a token issued for one resource being replayed at another,
    and the MCP spec makes both halves mandatory: the client MUST send `resource`, and the
    server MUST reject a token not issued for it. An issuer that ignores the parameter leaves
    the client with nothing it can present.
    """
    client_id, secret = registered

    status, response = post(
        metadata["token_endpoint"],
        form={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "resource": RESOURCE,
        },
    )
    assert status == 200, response

    audience = claims(response["access_token"]).get("aud")
    assert RESOURCE in ([audience] if isinstance(audience, str) else (audience or []))


def test_the_access_token_is_a_jwt(
    metadata: dict[str, Any], registered: tuple[str, str]
) -> None:
    """CFOKit validates a signature locally against cached JWKS and reads the audience and
    subject from the claims (ADR-0019). An opaque token carries none of that and would need an
    introspection round trip on every request — which is an issuer-specific API, so a
    deployment doing that would have coupled itself to one issuer.

    Hydra's default strategy is opaque, so a client registering itself through RFC 7591 was
    issued tokens this deployment cannot read at all.
    """
    client_id, secret = registered

    _, response = post(
        metadata["token_endpoint"],
        form={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        },
    )

    assert response["access_token"].count(".") == 2, "opaque access token"


def test_a_token_names_its_issuer_and_subject(
    metadata: dict[str, Any], registered: tuple[str, str]
) -> None:
    """`LED-20` requires every transaction to record what wrote it, and `sub` is where that
    comes from. A token without one is a token the ledger must refuse."""
    client_id, secret = registered

    _, response = post(
        metadata["token_endpoint"],
        form={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        },
    )
    payload = claims(response["access_token"])

    assert payload["iss"].rstrip("/") == ISSUER
    assert payload["sub"]
