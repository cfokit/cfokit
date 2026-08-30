---
status: "accepted"
kind: "substrate"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0013: Binding non-goals, enforced as a gate rather than a ban

## Context and Problem Statement

CFOKit is built largely by agents, working from a rulebook, against a product whose adjacent
possibilities are all individually reasonable. That combination has a specific failure mode.

Every item on the list below will be proposed, and each proposal will be locally correct. A report
needs rendering, so a small web view. Compliance rules vary by jurisdiction, so a plugin system.
Reports are slow, so a cache. Agents want live updates, so websockets. None of these arrives
announced as scope creep; each arrives as the obvious next step, with a real problem behind it.

The cost is not the feature. It is that each one is a surface with its own security model,
operational burden, and stability obligations, added to a project whose scarce resource is
attention on correctness. And an agent given a plausible reason will build it, because "is this in
scope?" is not a question it can answer from the code.

What is needed is not a prohibition — several items on the list are things CFOKit will probably
need. It is a **forcing function**: a point at which building the thing requires writing down why,
so that the decision is made deliberately once rather than drifted into.

## Decision Drivers

* The primary builder is an agent with no accumulated sense of what the project has already
  declined.
* Several listed items are genuinely needed, so a ban would be violated and thereby discredited.
* The forcing function must sit at the moment of proposal, because drift happens in a single
  session rather than on a quarterly cadence.
* The rule must be encountered where building happens, which is `CLAUDE.md`.

## Considered Options

* A binding non-goals list, enforced as a gate requiring an ADR
* No list; rely on judgement
* Hard prohibitions instead of a gate
* A permitted list instead of a forbidden one
* Put the non-goals in the product documentation only
* Time-box instead of gate: revisit the list quarterly

## Decision Outcome

Chosen option: the following are **binding non-goals**. Do not build them, and do not propose them
**without an ADR**.

| Non-goal | Why it is listed |
|---|---|
| Web UI or admin console | A second product surface: its own auth, session handling, XSS surface, and design work |
| Plugin system | Extension points cannot be designed before there are extensions to generalise from |
| Custom query language | Reimplementing SQL, worse, against a database chosen for its query capability |
| Caching or rollup layer | ADR-0003 chose derived balances deliberately; materialisation belongs behind profiler evidence |
| Read replicas | Replication lag against read-your-writes on a ledger, for a workload that is mostly idle |
| GraphQL | Caller-composed queries sit badly with per-entity grant checks (ADR-0012) |
| Websockets or SSE transport | Stateful connections against a scale-to-zero container (ADR-0018) |
| Event bus | A second account of what happened, when an append-only ledger already is one |

**This is a gate, not a ban.** The rule is *do not build without an ADR*, and an ADR sanctioning one
of these is a legitimate outcome, not a violation.

**What an ADR must establish** to lift the gate:

1. The `REQ-` id it serves, and why that requirement cannot be met with the existing surfaces.
2. What the smallest version looks like, and where its boundary sits.
3. Its ongoing cost: security surface, operational burden, and whether it becomes a published
   interface with stability obligations (ADR-0016).

Anything absent from this list is not thereby endorsed. The list names the temptations that were
foreseen, not the complete set.

### Items that have passed the gate

| Item | Passed via | When |
|---|---|---|
| Slack as a delivery surface | [ADR-0023](0023-slack-as-a-delivery-surface.md) | 2026-08-18 |

Slack was never literally on the list, but two ways of building it are — Socket Mode is a websocket,
and a chat surface is adjacent enough to "web UI" that building one unrecorded would be the drift
this gate exists to catch. It was assessed against the gate and passed; the websocket route was
rejected and the record says why.

### Consequences

* Good, because a proposal must be written down before it is built, which converts drift into a
  deliberate decision.
* Good, because an agent encountering the list at the moment of building gets an answer to a
  question it cannot answer from the code.
* Bad, because legitimate work is slowed by a writing step. That is the intended trade, and it will
  occasionally be genuinely annoying.
* Bad, because the list will look wrong in hindsight for whichever items eventually pass the gate.
  That is not a failure of the list — a gate that nothing ever passes is a ban that was mislabelled.
* Bad, because it needs maintaining: an item that has passed should be marked as such rather than
  silently removed, so the reasoning history survives.

### Confirmation

`CLAUDE.md` § Scope discipline carries the list and points here — **already in place**. Enforcement
is by review and by the agent reading the rule, not by a CI gate; this is a scope rule rather than a
mechanical property.

## Pros and Cons of the Options

### A binding non-goals list, enforced as a gate

* Good, because it is available at the moment of proposal, to a builder with no institutional
  memory.
* Good, because it permits the right answer to be "yes, and here is the record" rather than "no".
* Bad, because it requires maintenance, and an unmaintained list decays into noise.

### No list; rely on judgement

The usual approach, and it works in teams with shared context and a habit of saying no.

* Good, because it costs nothing and slows nothing.
* Bad, because the primary builder here is an agent, which has no accumulated sense of what this
  project has already declined. Judgement that lives only in one person's head is not available at
  the moment a proposal is made, and the proposals arrive with reasons attached.

### Hard prohibitions instead of a gate

* Good, because it is cleaner and more enforceable: these things are never built, full stop.
* Bad, because it is already false. The product vision depends on a Slack surface, and REQ-B3
  requires statements in a form a human can hand to a lender — which is rendered output. A ban
  would either be violated within months, teaching everyone that the list is advisory, or would
  block the product. A gate that is respected is worth more than a ban that is not.

### A permitted list instead of a forbidden one

Enumerate what CFOKit *is*, and treat everything else as out of scope by default.

* Good, because it is a stronger constraint in principle.
* Bad, because it cannot be written honestly. The product is early and its surface is not yet known,
  so a permitted list would either be so broad as to permit everything or would forbid work nobody
  has thought of yet — including work that turns out to be the point.

### Put the non-goals in the product documentation only

They are product boundaries, so arguably they belong with the vision rather than in a rules file.

* Good, and also true — hence the "What CFOKit is not" section in `vision.md`.
* Bad, as *sufficient* on its own. The list has to be where a builder will encounter it at the
  moment of building, which is `CLAUDE.md`. The product documentation states the outward
  commitment; this record and the rules file are what prevent the drift.

### Time-box instead of gate: revisit the list quarterly

* Good, because it is softer and avoids blocking on a written decision.
* Bad, because scope creep does not happen on a quarterly cadence. It happens in a single session,
  when something adjacent is three hours of work and nobody is watching.

## More Information

**Follow-on obligations.**

- `CLAUDE.md` § Scope discipline carries the list and points here. **Already in place.**
- `vision.md` states the outward-facing version, and must not overstate it as a prohibition.
  **Already in place.**
- An ADR that lifts the gate for an item updates the list to record that it passed, and when.
- Slack has passed (ADR-0023). Rendered report output, which REQ-B3 requires, is still queued.

**Reversal cost. Low.** The list is a rule, not an architecture. Removing it costs nothing
mechanically and costs the forcing function entirely.

## Revisit when

- An item passes the gate, which is a routine update rather than a revisit.
- A category of proposal recurs that is not on the list, indicating a temptation that was not
  foreseen and should be named.
- CFOKit acquires a team large enough that shared judgement replaces the need for a written list —
  which is a long way off and should not be assumed early.
