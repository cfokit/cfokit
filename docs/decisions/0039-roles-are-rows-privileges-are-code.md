---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-02
decision-makers: [Geoff]
---

# ADR-0039: Roles are rows, privileges are code, and only `owner` exists yet

**Requirements served:** `IAM-01`, `IAM-02`, `IAM-07`.

## Context and Problem Statement

`IAM-01` says access "is governed by the roles it holds there. A role carries a defined set of
capabilities". That is conventional role-based access control, and this part of the system has
no reason to be anything else.

Two questions it leaves open. **Where does the role catalog live** — compiled into the
application, or stored alongside the grants that reference it? And **which roles ship now**,
given the requirements name only administering and holding, and every early user is a sole
proprietor or solo founder who is the only person with access to their own books.

The catalog was a dictionary in `service/authorization.py` holding five roles, of which the
requirements named one. The other four were invented at the point of implementation and,
published in the OpenAPI document, became a contract with nothing behind it.

## Decision Drivers

* Adding a role is an ordinary operational change, not a release. It should not require
  editing code, rebuilding an image and redeploying.
* A privilege only means something because code checks it. Its name cannot be data without the
  check becoming data too, which is a rules engine and not this.
* A role nobody holds cannot be validated by use. The first customers are sole proprietors; no
  delegation happens until there is somebody to delegate to.
* Publishing a role name in the OpenAPI enumeration is a contract. Adding one later is
  additive; removing one is breaking. The asymmetry sets the bar for shipping a name.

## Considered Options

* Roles in the database, privileges in code
* Both in code: an enumeration of roles and a compiled map
* Both in the database, including the privilege names the code checks against

## Decision Outcome

Chosen option: "roles in the database, privileges in code".

> `Capability` enumerates the privileges, because something has to check them. `role` and
> `role_privilege` hold the catalog. Adding a role is inserting rows and mapping its flags.
> Only `owner` is defined; the rest arrive when there is somebody to hold them.

The privilege set already distinguishes what `IAM-02` requires — reading, recording, posting,
administering, holding — so nothing is foreclosed by shipping one role. A deployment that needs
a bookkeeper who drafts but does not post adds a row and maps `read` and `record` to it.

A privilege named in a row that the code does not define confers nothing. Failing closed is the
only safe direction: a typo in a migration must not widen anyone's authority.

The API takes a role name as a string rather than an enumeration, because a catalog that is
data cannot be enumerated at build time. An unknown name is refused with `unknown_role` rather
than a constraint violation.

### Consequences

* Good, because the shape supports every case the requirements anticipate while naming only the
  one that exists, so nothing is published before it is exercised.
* Good, because adding a role is a migration — reviewable in git, applied by the same explicit
  command as every other schema change (ADR-0004).
* Good, because the privilege map is resolved in the same query that reads the grants, so a
  change takes effect with no cache to invalidate.
* Bad, because the role catalog is no longer visible in the code that enforces it. Reading
  `authorization.py` no longer tells you what `owner` can do; the migration does.
* Bad, because the OpenAPI document can no longer enumerate valid roles, so a client cannot
  discover them from the contract. `IAM-19` asks for enumerable capabilities at deployment
  scope, and the same question one scope down would answer this.
* Neutral, because privileges could later become rows too. Nothing here prevents it; the
  argument against is that a checked flag is code by nature.

### Confirmation

An integration test asserts the catalog as shipped: `owner` exists, carries every privilege
the code defines, and is the only role. A second asserts that a grant naming an undefined role
is refused with `unknown_role`, and a third that a privilege row the enum does not define
confers nothing.

The unit tests over `effective` and `require` take privilege sets directly, so authorization
stays testable without a database (ADR-0036, layer 1).

## Pros and Cons of the Options

### Roles in the database, privileges in code

* Good, because it splits along the line that matters: what is checked is code, what is
  configured is data.
* Good, because it is what most role-based systems do, and this is not a part of the product
  that benefits from being novel.
* Bad, because the catalog and the checks are in two places, and reading one does not tell
  you the other.

### Both in code

* Good, because everything an authorization decision depends on is in one file and reviewed
  together.
* Bad, because adding a role for one customer means a release, which makes the answer to "can
  we add a bookkeeper role" a deployment rather than an insert.
* Bad, because it invites shipping speculative roles, since they cost nothing to add at the
  time and are then published.

### Both in the database

* Good, because the whole model would be configurable without a release.
* Bad, because a privilege is only real if code checks it. Making the names data means either
  the checks become data — a rules engine, which `ADR-0012` excludes — or rows exist that
  nothing consults.

## More Information

**Scope.** `IAM-07` describes an identity that can grant, which any role carrying `grant`
satisfies; it names no particular one. Whether the catalog should be enumerable through the
API is `IAM-19`'s question one scope down, and this record does not answer it.

**Reversal cost. Low.** The catalog is two small tables and a seed. Compiling it back into
code is a migration and a dictionary.

## Revisit when

* A second role is needed, which is the first real test of whether an insert is the right
  mechanism.
* Someone asks what roles exist and there is no way to answer it through the API.
