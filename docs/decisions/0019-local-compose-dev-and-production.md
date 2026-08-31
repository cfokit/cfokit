---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0019: One compose stack serving both local development and local production

**Requirements served:** `NFR-11`, `NFR-21`.

## Context

ADR-0004 commits to three deployment topologies, one of which is self-hosted local. That
tier is a product promise: a user should be able to run CFOKit on a laptop, point an MCP
client at it, and have real books — not a demo.

Local development has overlapping but different needs: source reload, an inspectable
database, seed fixtures, verbose logs.

The failure mode to avoid is a "local mode" that quietly becomes a second product with
its own semantics. That is what collapsing the two backends (ADR-0015) was meant to
prevent, and a divergent compose file is the same mistake in a different place.

The genuinely hard part is not containers. It is authentication: the service is an
OAuth 2.1 resource server, and on a laptop with no cloud account there is no issuer.

## Decision

We will ship **`compose.yaml` as a production-shaped local deployment**, with
**`compose.dev.yaml` as an explicitly-applied overlay** containing only development
differences.

Local deployment will not require an external identity provider. The specific issuer
arrangement is deferred to ADR-0020; what this ADR fixes is that whatever it is, it runs
inside the compose stack and needs no cloud account.

**Scope note.** An earlier draft of this ADR claimed a local issuer makes the
application's auth path "identical in every topology." That is true only of token
validation. Issuer-side behaviour — dynamic client registration, claim shapes, scope
encoding — can still diverge, and the DCR shim is custom code. ADR-0020 addresses what
must actually be held constant.

## Alternatives rejected

### `docker-compose.override.yml` (auto-loaded)

The idiomatic Compose pattern, and rejected for that reason: it applies silently, so
`docker compose up` gives you development configuration by default. A user who follows
the quickstart and then keeps their real books in it gets bind mounts, debug logging,
and an exposed database without ever having chosen them. For a financial application,
explicit beats idiomatic.

### Separate compose files with no shared base

Duplicates the service topology, so the two drift. The development stack stops proving
anything about the production one.

### Require an external OAuth issuer for local deployment

Simplest application code, but local deployment then requires a cloud account and a
provider project, which defeats the purpose of the tier.

### Static bearer token for local mode

Easiest for the user, and rejected because it is a second authentication path in the
application. Auth is the component where divergence between what we develop against and
what users run is least acceptable, and a local-only code path would be exercised by
nobody who could catch its bugs.

## Consequences

**Accepted costs.**
- At least one additional container in the local stack.
- Whatever ADR-0020 settles on must be pinned and tracked for security updates like any
  other dependency.

**Follow-on obligations.**
- The CI portability gate runs `compose.yaml` **without** the dev overlay, so what CI
  proves is what users run (ADR-0004).
- `compose.dev.yaml` may not alter the image build target's runtime dependencies, the
  migrations, or the auth path. Divergence is limited to reload, exposed ports, log
  level, and opt-in fixtures.
- Seeding is behind a Compose profile and never runs by default. Seeding a ledger
  holding real books would corrupt it.
- Data lives in a named volume. Document that `docker compose down -v` destroys it, and
  ship a backup command.
- Cross-device access requires a tunnel and `PUBLIC_BASE_URL` set to the public
  hostname. Same-machine access over `http://localhost` needs no TLS.

**Reversal cost.** Low. Both files are configuration.

## Revisit when

- An MCP client we want to support cannot complete discovery against the local issuer.
- Local deployment demand justifies a packaged installer, at which point compose becomes
  an implementation detail behind it rather than the user-facing interface.
