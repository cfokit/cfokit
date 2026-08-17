# ADR-0009: One application, two protocol adapters, with MCP calling the service in-process

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

## Context

The ledger has two consumers with different expectations. Agents — the bookkeeper skill, and any
third-party MCP client — expect a tool surface. Third-party integrators expect an HTTP API they
can build against. Both perform the same operations against the same books.

The service is a single stateless container backed by Postgres, deployed on a container runtime
with scale-to-zero and cold starts (ADR-0017). It is an OAuth 2.1 resource server with mandatory
audience validation on every request (ADR-0019).

The question is not whether to expose both protocols. It is where the boundary between them sits,
and specifically whether one is implemented in terms of the other.

## Decision

**One application, one service layer, two thin protocol adapters.**

- `api` exposes REST over HTTP.
- `mcp` exposes the tool surface.
- Both are siblings at the top layer (ADR-0008) and must not import each other.
- **`mcp` calls the service layer in-process.** It does not issue HTTP requests to `api`.

Adapters translate protocol to service call and back. Any behaviour in an adapter is a defect,
because it then exists in one protocol and not the other.

## Alternatives rejected

### Two separate services

An MCP server and a REST API as independent deployables, each with its own repository access.

Rejected because it doubles everything that must not diverge: two deployments to operate, two
auth configurations to keep consistent, two sets of database credentials, and — decisively — two
implementations of the service-layer obligations. Every state-changing call must write exactly one
`audit_log` row, take the entity lock, and validate grants server-side (ADR-0011). Two
implementations of that is two places for it to be subtly wrong.

### MCP server as an HTTP client of the REST API

The most attractive alternative, and worth stating fairly: it guarantees the two surfaces cannot
drift, since one is literally built on the other. It is also a common pattern for API gateways.

Rejected on four counts.

1. **It creates a second authentication hop.** The MCP server would need credentials to call the
   REST API on the user's behalf, which is either token forwarding or a service account with
   broad rights. Both weaken a tenancy boundary enforced by audience and scope validation
   (ADR-0019), and a service account holding rights across entities is precisely the thing
   per-entity grants exist to prevent.
2. **The service would call itself over the network.** On a runtime with scale-to-zero, a
   loopback request can hit a cold start, so an MCP tool call could pay two cold starts. It also
   makes the service depend on its own ingress being reachable from inside itself.
3. **`PUBLIC_BASE_URL` is not a valid loopback target.** It is authoritative for what the service
   says about itself and may be a tunnel hostname in local deployments (ADR-0003, ADR-0018).
   Dialling it from inside the container is either wrong or a second configuration variable,
   which the deployment contract does not have.
4. **Doubled latency for no correctness gain.** Parity is better obtained by generating both
   surfaces from one service layer and diffing the committed artifacts in CI (ADR-0015).

### REST implemented as a thin wrapper over the MCP tool surface

The inverse, attractive because MCP is the primary consumer.

Rejected because tool-call semantics translate poorly into a resource-oriented HTTP API. Tools
are verbs with flat argument objects; a good REST API has addressable resources, appropriate
methods, and status codes that mean something. Deriving one from the other would produce a public
HTTP interface that third parties find awkward — and it is a published interface with stability
obligations, so awkwardness is expensive to fix later.

### A single generic RPC surface serving both audiences

One `POST /call` endpoint with a method name, consumed by both.

Rejected because neither audience gets idiomatic access. MCP clients expect discoverable tools
with descriptions; HTTP clients expect resources and caching semantics. A shared lowest common
denominator serves the implementation rather than either consumer.

### GraphQL as a single flexible surface

Rejected: it is on the binding non-goals list (ADR-0012), and an interface whose queries are
composed by the caller is a poor fit for a system where every access must be checked against
per-entity grants.

## Consequences

**Accepted costs.**
- Two adapters to maintain, and two generated contract artifacts to keep committed and diffed.
- The in-process call means an MCP integration test exercises the service directly rather than
  the full HTTP path, so the HTTP path needs its own tests rather than inheriting coverage.
- Parity between surfaces is a property we must actively verify, not one the structure gives us
  for free. That verification is CI gate 5.

**Follow-on obligations.**
- `import-linter` keeps `api` and `mcp` as siblings that cannot import each other. **Already in
  place** and observed to fail when violated.
- Both adapters remain thin; any logic found in one moves down to `service`.
- Generated OpenAPI and MCP tool descriptions are committed, and a diff means a contract change
  requiring review (ADR-0015).
- Audience validation happens on every request through both adapters, not in one of them.
- Errors surface the same stable `code` through both protocols (ADR-0015).

**Reversal cost. Low to moderate.** Splitting into two deployables later is mostly packaging, and
the service layer is already the seam. Changing which surface derives from which is more
disruptive but would still not touch the service layer or below.

## Revisit when

- The two surfaces need genuinely different scaling characteristics — for example if MCP traffic
  becomes long-lived and bursty while REST stays light. That is an argument about deployment
  topology, not about the service layer.
- A third protocol appears, at which point the adapter pattern is either vindicated or shown to
  be leaking.
