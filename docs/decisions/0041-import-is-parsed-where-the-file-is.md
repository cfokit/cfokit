---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-09
decision-makers: [Geoff]
---

# ADR-0041: An import is parsed where the file is, and the books arrive as a neutral shape

**Requirements served:** `IMP-01`, `IMP-03`, `IMP-05`, `IMP-08`, `NFR-04`, `NFR-12`, `PLT-02`.

## Context and Problem Statement

[ADR-0040](0040-import-is-the-first-module.md) settled where import lives, what it is called, and
that the file never passes through a model. It left delivery as a path: mount a directory, set
`IMPORT_ROOT`, name a file inside it.

That is not a deployment shape — a container on the maintained cloud target has no host directory
to mount, and the substitutes are provider-coupled in a way [ADR-0004](0004-portability-as-a-build-gate.md)
forbids at module scope. It is also not usable. The operator is a person with a zip in their
downloads folder, and "place this file where the server can see it, then tell me its path" is not
an onboarding step anybody completes.

So the file has to travel. **The question is what travels — the archive, or what was read out of
it** — and it is decided by two measurements against a real export of 5,556 transactions and 11,580
posting lines.

**The model carries the transactions expensively, not impossibly.** As JSON tool arguments they
are 1.35 MB, about 404,000 tokens. Positionally encoded with the chart as an index — 62 accounts
referenced 11,580 times, so the repeated paths are 270 KB of the total — the same information is
**about 74,000 tokens**. That is a real cost and a slow one, because the model emits every figure;
it is not the impossibility the first draft of this record asserted.

**The work outlives a tool call, but only just.** 10.2 ms per transaction through the ordinary
service path, of which 4.4 ms — 43% — is connection setup, entity scoping and the advisory lock,
because `entity_write` opens a connection per call. About 57 seconds for the whole export locally,
longer against a managed database. Too long for one request; nothing like long enough to need a
job.

A skill can carry a script, and where that script runs on the host it makes its own HTTP calls
with no model in the path. That makes "where does parsing happen" a real choice rather than a
consequence of the transport.

**Where the script runs is not ours to choose, and one runtime cannot reach us at all.** Measured
in Claude Desktop: skill code runs in a sandbox with Python 3.11 and egress through a proxy with a
domain allowlist — `pypi.org` and `github.com` answer, `example.com` returns 403, and no port on
the operator's own machine is reachable. A tunnel does not help, because a tunnel's hostname is
not on that list either. Desktop's MCP servers are unaffected: they are host processes, which is
why the earlier end-to-end over MCP worked and this does not.

The interpreter version is not documented for Desktop, and it may differ by platform. It read
3.11.15 when `python3 --version` was run in a Desktop chat on 2026-09-29, and Anthropic documents
3.11 for the API's code-execution tool. `tests/test_reader_script.py` runs the reader on that
version, and ruff holds `skills/` to it.

So the transport is not one question but two, and they have different answers:

- **A runtime with host access** — Claude Code, and any agent running as an ordinary process —
  posts the shape directly, and no transaction passes through a model.
- **A sandboxed runtime** — a Claude Desktop chat — cannot reach CFOKit by any route. The model
  is the only bridge between the sandbox that holds the file and the MCP server that can write.

## Decision Drivers

* `NFR-04` requires one tenant's activity not to degrade another's. Decompressing an untrusted
  archive in the process that serves every other entity's tools is the sharpest version of that
  risk: a genuine QuickBooks export compresses at 1.08x, and 1,029x is four lines of Python.
* `NFR-12` wants an extension point without a plugin system. If the contract is a foreign file
  format, CFOKit must ship a reader per source system. If it is a neutral shape, anyone writes one.
* `PLT-02` puts the runtime in the organisation's hands. A file that never leaves the operator's
  machine is the strongest form of that.
* [ADR-0024](0024-synchronous-application-code.md) makes a runtime dependency a decision.
  Exactly one file imports `openpyxl`, and it is the reader.
* `IMP-05` requires the operator to see what will be created and what will not, and to be able to
  abandon it — which is a plan against parsed content, wherever the parsing ran.

## Considered Options

* Parse in the agent runtime; post the neutral shape
* Upload the archive; parse on the server as a staged job
* Send parsed transactions as MCP tool arguments
* Keep the mounted directory

## Decision Outcome

Chosen option: "Parse in the agent runtime; post the neutral shape".

### 1. The published contract is `SourceBooks`, not a QuickBooks zip

The endpoint accepts the neutral shape [ADR-0040](0040-import-is-the-first-module.md) already
defined — accounts, entries, stated balances, stated statements, and the fingerprint of the file
they came from. That shape existed so "adding a second source is a reader rather than a second
pipeline"; publishing it makes the same seam the boundary between CFOKit and whoever holds the
file.

`NFR-12` follows without a plugin system. A Xero or Sage reader is somebody's script targeting a
published shape, and it needs nothing from CFOKit but the contract — which is the same relationship
`skills/` already has with the ledger ([ADR-0014](0014-single-tool-surface-hosted-backend-only.md)).

### 2. The reader ships with the skill, and CI tests it as a client

A stdlib-only script — an `.xlsx` is a zip of XML with a shared-strings table — distributed in the
skill bundle. No `openpyxl` in the agent runtime and none on the server.

**This does not weaken the testing story, which is why the earlier draft of this record was wrong
to keep a server-side reader for that reason.** `skills/` is in this repository. CI runs the script
against the synthetic export and checks what it emits, exactly as layer 3 of
[ADR-0036](0036-correctness-is-tested-in-four-layers.md) drives both adapters as a client does. The
boundary forbids a code dependency, not a test.

### 3. The server stops parsing foreign binary formats

The archive never reaches it. `quickbooks.py` and its 546 lines leave `src/`, `openpyxl` leaves the
runtime dependencies, and the server validates a JSON schema instead — a categorically smaller
thing to get wrong than a zip of XML from an untrusted source.

The bounds do not disappear; they move to where the parsing is. A malicious archive then bombs the
runtime of the person who chose to open it, on their own machine, with their own file. That is not
nothing, and it is not `NFR-04`.

### 4. There is no job, because there is no work that outlives a request

The client posts the shape in batches; each is a short request and the client holds the loop
counter. At the measured rate a batch of 500 is about five seconds. Nothing is staged, nothing is
polled, and no worker runs.

**This is where the previous draft's event-bus question dissolves rather than being answered.**
That draft argued a fixed pipeline should be stage rows rather than messages. With parsing on the
client there is no server-side pipeline to shape either way: the stages are steps in a script,
and a script's stages are lines of code. `ADR-0012`'s gate on an event bus is untouched and
unspent. It will be asked again when a bank feed arrives on a cadence, which is the case that
genuinely has server-side work between arrivals.

Retry stays safe because [ADR-0029](0029-mandatory-idempotency-keys.md)'s keys are derived from the
file's fingerprint and the source's own row reference: a batch sent twice is a replay, and a client
that dies mid-import resumes by sending the same batches again.

### 5. The script authenticates as a person, by device flow, and caches nothing

The script POSTs, so it needs a credential, and it cannot borrow the agent session's: `apply`
refuses anything that is not `ActorClass.PERSON`, and a token an agent session holds carries an
RFC 8693 `act` claim. **A person-facing sign-in is therefore the design rather than friction added
to it** — ADR-0007's "the agent proposes; a person's confirmation posts", applied to the largest
single act of posting the system offers.

**RFC 8628 device authorization**, against a public client declared in the realm. The script
discovers `device_authorization_endpoint` from `AUTH_ISSUER_URL`'s metadata, prints a URL and a
user code, and polls — no issuer-specific code (ADR-0019), and no bound port or local browser,
neither of which an agent runtime reliably has. It is what `gh`, `aws` and `az` do, for that
reason.

**A public client, so it ships in the realm.** It holds no secret, which is why it can be in the
repository where the Claude Desktop client deliberately is not. A self-hoster gets it with the
realm rather than registering one.

**Nothing is cached — no token, no refresh token.** One sign-in per run. A standing refresh token
in an agent runtime is a credential sitting where a great deal can read it, in exchange for
convenience on an operation a company performs approximately once. A run that dies is resumed by
signing in again, which is safe because ADR-0029's derived keys make the repeat a replay.

CFOKit issues nothing. `IAM-10` says it "issues no credentials", so an endpoint minting a short-lived import token was considered and rejected outright
rather than weighed.

**Device flow is not universal, and that is a contract line rather than a surprise.** It joins the
issuer contract `infra/README.md` states and the conformance suite verifies, on the same footing as
RFC 8707 — which no issuer implements and which the suite records as a strict xfail. Loopback with
PKCE (RFC 8252) is the documented fallback for an issuer without it.

### 6. A sandboxed runtime imports over MCP, and the model is the bridge

**Superseded by [ADR-0051](0051-books-are-imported-through-the-web-client.md).** Sections 1–5 stand.

Where the runtime cannot reach CFOKit, the same neutral shape arrives as MCP tool arguments. The
sandbox parses the archive and hands the model a compact rendering; the model calls the tool.

**The encoding is the design.** One line per transaction — reference, date, description, then
`account~amount` per posting — with the chart sent once as an index and referenced by number. The
account paths are 270 KB of a 509 KB payload because 62 accounts are named 11,580 times, so
indexing them halves it: **about 74,000 tokens** against 404,000 as JSON.

What is kept and why, because each of these was measured and could have gone the other way:

- **ISO dates**, not `260628`. Compact dates save 7,000 tokens, and a model emits a correct
  `2026-06-28` more reliably. Transcription accuracy is worth more than 10%.
- **Descriptions**, costing 17,000 tokens. They are `IMP-04`'s lineage and the difference between
  books somebody can read and a column of figures.
- **Explicit references.** ADR-0029 derives the idempotency key from them, so implying them from
  line order would break a retry that batched differently — and retry is the only thing standing
  between a dropped connection and a company's history posted twice.

**The transcription risk is real and is not silent.** A model that mistypes an amount produces
books that disagree with the balances the source states for itself, and `IMP-08` reports that as a
divergence. `NFR-01` then forbids carrying it. That is the reconciliation doing the job it was
built for rather than a defence invented for this case — and it is why the comparison must stay
over the *journal*, not over figures the same file stated.

**This is a second ingress path, and the previous section argued against having one.** The
argument was that a convenience kept alongside a supported route becomes a supported route by
accident. This is not that: the two exist because two runtimes exist, one of which cannot open a
socket to CFOKit. They carry the same shape, the same idempotency keys and the same
reconciliation, so they are one design with two transports rather than two designs.

### 7. Opening balances are not a cheaper onboarding, and the reason is `NFR-01`

Carrying in per-account balances is a fraction of the cost — the chart and the stated balances are
**about 2,900 tokens** — and it is what a system migration conventionally does. It is refused here
for onboarding, because the figures would come from the source's trial balance and would then be
reconciled against that same trial balance. `NFR-01` says agreement with our own arithmetic is not
evidence, and `IMP-08`'s whole value is that our balances are computed from the *journal* while
the stated ones come from a report — two independent paths through one file. Collapse them and
the reconciliation proves only that the loader can read what it wrote.

A statement comparison is impossible on those terms as well: a profit and loss is period activity,
which carried-in balances do not contain.

**Backfilling history afterwards is possible, and is not the design.** Confirmed against the
ledger: `open_balances` refuses a second opening, so the carried-in entry is *reversed* — which it
accepts, being an ordinary posting — and the history is then posted. The books come out right. It
is recorded because somebody will ask, not because onboarding is meant to work that way:
onboarding is one flow with nothing else happening on the ledger in between, so there is no window
in which a cheap approximation is worth having. Anyone doing it later should know that a closed
period refuses the backfill with `period_closed` and has to be reopened first, which is now an
`ACT_AS_PRINCIPAL` act (ADR-0042).

### 8. `IMPORT_ROOT` is removed rather than demoted

An earlier draft kept it as a development affordance. Two ingress paths is the thing that record
argued against, and a convenience kept "for local development" is how a second supported path
arrives by accident. The script runs locally as readily as it runs anywhere.

### Consequences

* Good, because the import is the one operation that already had to be a person's act, so the
  credential it needs and the credential it can get are the same one — the constraint and the
  mechanism agree instead of fighting.
* Good, because the runtime dependency count goes **down**. `openpyxl` was added for the reader and
  nothing else imports it.
* Good, because the operator's file never leaves their machine, on a hosted deployment as much as a
  self-hosted one.
* Good, because a third party can land books from a system CFOKit has never heard of without
  CFOKit changing.
* Good, because no object store, no blob lifecycle, no upload surface, and no worker are built at
  all — the smallest version of this is also the portable one.
* Bad, because the reader now versions separately from the server, which "same code in production"
  previously made impossible. It becomes a contract problem, governed by
  [ADR-0015](0015-three-published-interfaces-stability-obligations.md), and a genuinely new failure mode:
  an old skill against a new server produces books nobody intended.
* Bad, because a sandboxed runtime pays about 74,000 tokens and the generation time that goes
  with it, every time a company onboards, for books the operator already has in a file.
* Bad, because two transports carry the same shape, so a change to it has to land in both — and
  the compact encoding has no schema validation the way the REST models do.
* Bad, because someone using the REST API without the skill has to bring a reader. That is the
  cost of the contract being neutral, and it is the same cost that buys `NFR-12`.
* Bad, because a stdlib reader is a rewrite of working, tested code. `openpyxl` earns its place in
  the current reader; replacing it with `zipfile` and `ElementTree` is real work and the shared
  strings table is the fiddly part.
* Bad, because `IMP-08`'s reconciliation now depends on a client that supplies both the entries and
  the source's stated balances. This is weaker than it looks: the comparison's value was never that
  the client is trusted, but that the figures are the *source's* arithmetic rather than ours. A
  client that tampers with both consistently has entered different books, which it could always do
  by hand.

### Confirmation

The reader's own conformance is CI running the distributed script against the synthetic export and
comparing what it emits against the shape the server accepts — a layer 3 test in
`ADR-0036`'s terms, driving the script as the skill drives it.

The bounds are gated where the parsing is: an archive past each bound is refused, and a member
whose declared size understates what it delivers is refused on read, because the central directory
is written by whoever made the file.

The contract itself is gated by CI gate 5 (`ADR-0015`): the neutral shape is a published interface,
so a change to it appears in a pull request as a change to a contract.

The issuer contract's device-flow line is verified by `tests/integration/test_issuer_conformance.py`
against the running issuer, which is where `AUTH_ISSUER_URL`'s other obligations are already
measured rather than assumed.

**Not gated:** nothing detects a skill emitting an older shape than the server expects. A version
field makes it detectable at the boundary; nothing makes it impossible.

## Pros and Cons of the Options

### Parse in the agent runtime; post the neutral shape

* Good, because the untrusted archive never reaches the multi-tenant process.
* Good, because it removes two runtime dependencies, an upload surface, a storage protocol and a
  worker, none of which then have to be portable.
* Good, because the extension point arrives as a consequence rather than as a plugin system.
* Bad, because the reader versions separately and can skew from the server.
* Bad, because it requires rewriting a working reader without its library.

### Upload the archive; parse on the server as a staged job

The previous draft of this record, and the obvious shape.

* Good, because one reader exists, running the same code in production that CI tested.
* Good, because the operator uploads a file, which needs no script and no runtime beyond a browser.
* Bad, because it puts an untrusted archive into the process serving every tenant, and every bound
  that process lacks becomes reachable the day the endpoint ships.
* Bad, because it requires an object store behind a portability protocol, a worker entrypoint, a
  stage table and a polling loop — all to carry 57 seconds of work.
* Bad, because it keeps `openpyxl` and adds an XML-hardening dependency to the server for a parse
  that does not have to happen there.

### Send parsed transactions as MCP tool arguments

Rejected outright in this record's first draft, on a figure that was right for the wrong encoding.
Now § 6, for sandboxed runtimes only.

* Good, because it needs no new endpoint and no credential beyond the MCP session's own — which
  matters most exactly where nothing else works.
* Good, because 404,000 tokens was JSON. The same information positionally encoded, with the chart
  as an index, is about 74,000.
* Bad, because every figure is retyped by something that can retype it wrong. Mitigated rather
  than removed: `IMP-08` compares against figures the source stated, so a mistyped amount is a
  reported divergence rather than quiet corruption.
* Bad, because the model emits 74,000 tokens, which is minutes of a person watching it type.
* Bad, because ADR-0040 said the file never passes through a model. This does not breach that —
  the *archive* still never does, and what crosses is the parsed shape — but it is close enough
  to the line that it needed saying rather than assuming.

### Keep the mounted directory

* Good, because it is built, tested, and demonstrated end to end against a real company's books.
* Bad, because it has no analogue on the maintained cloud target that `ADR-0004` permits.
* Bad, because it asks a person with a zip in their downloads folder to operate a file share.

## Revisit when

* A sandboxed agent runtime gains a configurable egress allowlist, or reaches an operator's own
  host. Either makes § 6 unnecessary and collapses two transports back to one.
* A second reader lands, which tests whether the neutral shape is genuinely neutral or a
  QuickBooks shape with the labels filed off.
* A bank feed arrives on a cadence, which puts server-side work between arrivals and is the case
  that reopens the queue question this record leaves unspent.
* The write path is batched. 43% of per-transaction cost is connection setup paid 5,553 times; if
  an import finishes in seconds, the batch size and the client's loop are both worth revisiting.
