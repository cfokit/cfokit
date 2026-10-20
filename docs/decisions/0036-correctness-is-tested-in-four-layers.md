---
status: "draft"
kind: "requirement-driven"
date: 2026-09-01
decision-makers: [Geoff]
---

# ADR-0036: Correctness is tested in four layers, and only the top one needs a model

**Requirements served:** `NFR-01`, `NFR-21`, `PLT-23`.

## Context and Problem Statement

[ADR-0010](0010-beancount-as-test-oracle.md) identified the hardest class of bug correctly: **tests
written by whoever wrote the logic encode that person's understanding, so they cannot detect that
the understanding is wrong.** That is not a hypothetical. The eval literature reports the same
failure for generated assertions — an assertion written against an implementation tends to encode
its current behavior, including its bugs, rather than the intended behavior.

ADR-0010 answered it with a differential oracle. That is *an* answer, and an expensive one, and it
is the only testing decision the corpus contains. Three things are unaddressed:

**What the oracle actually covers is small, and shrinking.** Of twenty ledger requirements, four are
meaningfully exercised by comparison with Beancount, eleven have no Beancount analogue at all, and
the two where the comparison would be most valuable — `LED-18` and `LED-19`, lot booking and FIFO
consumption — are `Deferred`. The subtle semantics an independent implementation is worth having for
are precisely the ones not being built yet. ADR-0010 now records this.

**Nothing covers the protocol surfaces.** The MCP tool surface and the REST API are published
interfaces with stability obligations (ADR-0015), and no record says how either is tested.

**Nothing covers agent behavior.** A skill is non-deterministic and reads untrusted content
(`PLT-23`, `BKP-20`). Its behavior cannot be asserted the way a function's can, and no record says
what takes the place of that.

## Decision Drivers

* Independence is the property that matters. At least one source of truth must be one CFOKit did not
  author, or the blind spot ADR-0010 named remains open whatever else is built.
* A gate that is slow, flaky, or costs tokens cannot run on every commit, and one that does will be
  disabled.
* ADR-0009 makes both adapters thin over one service layer, so most behavior is reachable without a
  protocol or a model.
* An agent acts on the books only through calls to the published tool surface, so its behavior can
  be asserted against those calls rather than judged.
* A contributor runs the full suite from a clean checkout with no credentials and no accounts
  (`NFR-21`).

## Considered Options

* Four layers, with independence bought by a conformance corpus and the differential oracle deferred
* The differential oracle now, as the primary correctness evidence
* Self-written tests only — API contract tests plus evals
* A second differential oracle from the same family, such as Ledger or hledger
* LLM-as-judge as the primary check on agent behavior

## Decision Outcome

Chosen option: "Four layers, with independence bought by a conformance corpus and the differential
oracle deferred", because independence can be had from published answers at a fraction of the
oracle's cost, and because the oracle's remaining value is concentrated in requirements that are not
being built yet.

### 1. Unit and property tests — the engine and the service

No protocol, no model, and no database for the engine, which is pure by construction (ADR-0008).

Property tests carry the arithmetic invariants, because they hold for all inputs rather than for the
examples someone thought of: postings sum to zero for any transaction; allocation parts sum to the
whole for any total and any line count (ADR-0025 already requires this); a reversal restores the
prior balance exactly; the trial balance ties after any sequence of operations.

### 2. A conformance corpus — where independence comes from

Worked examples taken from **published sources with published answers**, asserted directly against
the expected result. Intermediate accounting exercises, released examination problems, standard-setter
illustrative examples.

This is what replaces the oracle's independence property, and it is strictly better on two counts.
It has **no translation layer** — the oracle needs CFOKit's model rendered into Beancount syntax, and
that translator is untested code sitting between the system and its own correctness evidence, able to
produce both false divergences and false agreement. And it tests whether the answer is **right**
rather than whether it **matches**, which is what "500 years of double-entry practice" actually
means.

Every case cites its source. A case with no citation is not conformance evidence, it is a unit test
that has been misfiled.

### 3. Protocol integration — deterministic, no model

Both published surfaces are exercised as a client would: a real MCP client from the SDK over the real
transport, and the REST API over HTTP. This asserts that the contract *behaves*.

That the contract has not silently *changed* is already CI gate 5 — generated OpenAPI and tool
descriptions committed and diffed (ADR-0015). The two halves are complementary and neither replaces
the other.

### 4. Evals — the only layer that needs a model

Evals answer a question the layers below cannot: whether the tool surface is good enough for a model
to use correctly. That is a property of the descriptions and the capability model, not of the
service.

**Evals assert on what the agent did, never on what it said.** A turn's effect on the books is the
calls it made to the published tool surface: which tools, in what order, with what inputs. Each is
directly assertable, and together they carry the trajectory as well as the result. What the ledger
does with a call — the transaction, its postings, the audit row, the decision record of ADR-0033 —
is proven deterministically at layers 1 to 3, and an eval does not prove it again.

So the questions worth asking are all questions about calls:

- Did it draft rather than post directly?
- Did it stop and ask when it met a closed period, rather than working around it (ADR-0030)?
- Given a document carrying an embedded instruction, did it post anything (`PLT-23`)?
- What did it actually call, and in what order?

**Not the trial balance, and not the prose.** A trial balance is a derived aggregate: drafting then
posting and posting directly produce an identical one, as do a posting plus a reversal that nets
out. Its place is layer 1, where "it ties" is an invariant, and `EXP-01`, where it verifies an
export. Prose is what a judge reads, and LLM-as-judge is permitted only where no assertion on the
calls is possible, which for this product should be rare. General guidance puts deterministic checks
at 60–70% of an eval surface; a ledger should sit well above that, and a judge appearing where a call
assertion was available is a design smell.

**`claude plugin eval` runs them.** It runs each case against the plugin and again without it, and
reports the difference. The difference is the question: not whether the model did well, but whether
the skill changed the outcome.

- **Cases live in `skills/cfokit/evals/`.** The harness reads cases only from inside the plugin, so
  they ship with it.
- **The tool surface is mocked.** A case answers the CFOKit tools it needs from mocks written from
  the committed tool descriptions and refusal codes (ADR-0015). A run needs no stack, no issuer and
  no CFOKit credential — only the contributor's own Claude sign-in.
- **Graders are deterministic** — a tool called or not, calls in order, inputs matching. A judge
  needs the justification above.
- **A case pins its model** (ADR-0033, `SOC1-35`).
- **`uv run task eval` runs the suite**, under a cost ceiling, and so does adding the `eval` label
  to a pull request, which comments each case's score and delta at the head commit. Neither
  `uv run task check` nor `ci.yml` runs it.
- **A merge is a release.** Claude reads the plugin from `main`, so a regression is kept out of a
  release by keeping it out of a merge. A pull request changing `skills/cfokit/` merges without a
  person only when its head commit carries a passing result: the run finished, and every case
  scored at or above its threshold with the plugin (ADR-0048). A result below that is not a
  failed gate. It sends the pull request to a person, who judges whether it is a regression.

The harness is a tool, not the layer. Where it cannot express a case the layer needs, it is replaced,
and the layer's rules stand.

### 5. The rules that make the layers hold

- **Layers 1 to 3 are deterministic and gate every commit. Layer 4 does not.** Evals are slow,
  non-deterministic and cost tokens; they run on a cadence, and a regression there blocks a release
  rather than a commit.
- **An assertion's expected value comes from outside the implementation.** A published worked
  example, a requirement's stated acceptance, a domain invariant, or a second enforcement point —
  never from observing what the code returns. Who types the assertion is not the control and cannot
  be: every commit here is generated, tests included, so a rule about authorship is one the process
  writing it violates. Where the answer came from is checkable, which is why a layer 2 case carries
  a citation and a test refuses one without it.
- **Recording what the code returned and asserting that is never a specification.** It pins current
  behavior including its defects, which reintroduces at the top of the pyramid exactly the blind
  spot layer 2 exists to close. It is legitimate only as a characterization test taken deliberately
  before a refactor and labeled as one, and it never stands in for a case at layer 2 or layer 4.
- **Evals pin the model version** (ADR-0033, `SOC1-35`). An eval run against an unpinned model
  measures the model, not the change.
- **Evals gate on a regression in pass rate that a person judges real**, not on a fixed threshold.
  Demanding 100% of a non-deterministic system produces a suite people disable, so a score below a
  case's threshold routes the change to a person rather than refusing it.
- **Every real failure becomes a permanent case**, in whichever layer would have caught it.

### Consequences

* Good, because independence is preserved — the property ADR-0010 was right about — without the
  translation layer, the corpus in two formats, or the divergence register.
* Good, because the conformance corpus tests correctness against published answers rather than
  agreement with another implementation, which is the stronger claim and the one `NFR-01` wants.
* Good, because most of the suite sits at layer 1, which ADR-0009's thin adapters make possible, and
  runs in seconds with no infrastructure.
* Good, because a turn's effect is its tool calls, which the harness records, so layer 4 needs no
  judge and costs less than it would in a product whose output is prose.
* Good, because evals run with no stack and no CFOKit credential, against the published contract.
* Bad, because a conformance corpus is hand-built and grows slowly. It covers what someone took the
  trouble to encode, where a differential oracle covers whatever you throw at it.
* Bad, because deferring the oracle means the arithmetic is unchecked against an independent
  implementation until lots activate. Property tests reduce that exposure; they do not remove it.
* Bad, because four layers is more testing apparatus to explain than one oracle, and the boundaries
  between them will occasionally be argued.
* Neutral, because Beancount stays a pinned CI-only dependency, dormant rather than removed.

### Confirmation

Layer 1 runs inside the ordinary suite and gates every commit, as do the schema invariants of
layer 3. Layer 2 carries `NFR-01` while the oracle stays deferred, which is why every case cites
its published source: a case without one is a unit test that has been misfiled. The protocol half
of layer 3 drives both adapters as a client does, and CI gate 5 diffs what they publish against
the committed copies (ADR-0015). Layer 4 runs only through `uv run task eval` and the `eval`
label, which neither `uv run task check` nor `ci.yml` calls, so it cannot accidentally join the
per-commit gate. `scripts/review_policy.py` reads the result the label leaves, and
`tests/test_review_policy.py` holds the cases: a plugin change with no result, or a failing one,
goes to a person.

**Provenance is gated at layer 2 and reviewed everywhere else.** `tests/test_conformance_corpus.py`
reads every case in the corpus and refuses one whose manifest names no published source, no
expired copyright and no scan, so a unit test cannot enter the corpus claiming to be conformance
evidence — which is the layer carrying `NFR-01` while the oracle stays deferred, and so the one
where the control has to be mechanical. It is parameterised over the fixture directory rather
than over a named case, or it would hold only for the cases that exist today, and it sits outside
the integration tier so it gates every commit rather than only the runs with a stack up. Elsewhere it
is review: nothing distinguishes an invariant derived from `LED-03` from one derived by running the
code, and nothing detects a judge used where a call assertion was available. A review rule is weak
here, because the reviewer and the author are the same process. Treat every ungated rule in this
section as a statement of what the gated ones are for, rather than as a control of equal standing.

## Pros and Cons of the Options

### Four layers, with a conformance corpus and the oracle deferred

* Good, because it keeps independence while removing the translation layer that independence was
  costing.
* Good, because each layer catches a class the others structurally cannot, and only one needs a model.
* Bad, because the corpus grows by hand and covers only what was encoded.
* Bad, because it is more apparatus than a single oracle.

### The differential oracle now, as the primary correctness evidence

ADR-0010 as written, and the option this narrows rather than replaces.

* Good, because a differential comparison covers whatever inputs it is given, without anyone having
  to know the right answer in advance. That is a genuine advantage over a hand-built corpus.
* Good, because it is already scaffolded — the marker exists and the dependency group is decided.
* Bad, because its coverage today is four of twenty ledger requirements, and the two it would serve
  best are deferred.
* Bad, because it needs a translator into Beancount syntax, and a defect there yields false agreement
  as readily as false divergence.
* Bad, because the divergence register would be dominated by "Beancount has no concept of this",
  which is noise that buries signal.

### Self-written tests only — API contract tests plus evals

The cheapest option, and the one that looks sufficient.

* Good, because it needs no external source, no corpus, and no second format. Everything is code the
  team already writes.
* Good, because contract tests and evals are needed regardless, so this is a strict subset of the
  work rather than different work.
* Bad, because every assertion is written by whoever wrote the logic, which is exactly the blind spot
  ADR-0010 named and which generated assertions are reported to share. A misunderstanding of
  double-entry semantics passes every test in this option.

### Prohibiting model-written assertions

The rule this section's provenance rule replaces, and the one that looks like the answer.

* Good, because it names a real failure. An assertion written against an implementation encodes that
  implementation, defects included, and the eval literature reports generated assertions sharing the
  blind spot ADR-0010 identified in self-written tests.
* Bad, because nothing can enforce it here and nothing ever will. Every commit in this repository is
  generated, tests included, so the rule is violated by the process that writes it — and a corpus
  asserting a control it does not have is worse than one asserting none, because it stops anyone
  looking for the real control. ADR-0028's Confirmation claimed an `import-linter` contract that did
  not exist, and the rule keeping SQL in one place was review-enforced for as long as the record said
  it was gated.
* Bad, because authorship is the wrong variable. Someone who writes an assertion by running the code
  and recording its output has made the error whether they are a person or a model, and someone who
  takes the expected figure from `LED-04`'s published acceptance has not. The provenance of the
  expected value is what separates the two, and it is the half that can be cited and checked.

### A second differential oracle from the same family — Ledger or hledger

* Good, because it is cheap to add once a translator exists, and gives a third opinion.
* Bad, because shared conceptual ancestry means correlated errors: the plain-text ledger family
  descends from common design, so agreement between two of them is much weaker evidence than it
  appears.
* Bad, because it multiplies the translation-layer problem rather than removing it.

### LLM-as-judge as the primary check on agent behavior

* Good, because it needs no state model and can score things no assertion can express.
* Bad, because it is unnecessary here. An agent's turn leaves records rather than prose, so nearly
  every question worth asking is answerable by reading them, and a judge introduces non-determinism
  into the check as well as into the thing being checked.
* Bad, because a judge is itself a model that can be wrong in the same direction as the agent.
* Bad, because a mock can drift from the contract it stands in for, and an eval against a mock that
  answers what the ledger never would passes when it should fail.
* Neutral, because the cases ship inside the plugin, to every machine that installs it.

## More Information

**Follow-on obligations.**

- A conformance corpus location, with each case citing the published source of its expected answer.
- Evals for the acceptance criteria already written as such: `PLT-23`'s embedded-instruction case and
  ADR-0030's closed-period refusal are eval cases, not unit tests.
- A regression case for every real failure, filed at the layer that should have caught it.
- Eval cases for the bookkeeper skill's decision points, asserting on calls as this record
  requires: that `open_import` precedes `import_entries` and `reconcile_import`, that a
  refused import is abandoned rather than forced, that skipped rows are reported rather than
  repaired. Those are the places the
  skill either respects a boundary the ledger enforces or talks its way around one, and prose
  about the divergence is not evidence either way.
- `NFR-01` is amended alongside this record: it named a mechanism — "an independent implementation" —
  where what it wants is independence.

**Reversal cost. Low.** All of this is test infrastructure. The oracle is deferred rather than
removed, and turning it on is the work ADR-0010 already describes.

Related: [ADR-0010](0010-beancount-as-test-oracle.md) holds the oracle and now its activation
trigger; ADR-0008 makes the engine pure enough for layer 1; ADR-0015 holds the contract half of layer
3 and the committed tool descriptions layer 4's mocks are written from.

## Revisit when

* `LED-18` and `LED-19` activate, which turns the oracle on and is the trigger ADR-0010 now carries.
* A divergence or a conformance failure needs adjudicating and there is no agreed authority to settle
  it. That is the gap the corpus's source citations are meant to prevent, and its first occurrence
  will show whether they do.
* Evals become the bottleneck on releases, which would mean the cadence rather than the approach
  needs changing.
* A permissively licensed, independently derived double-entry implementation of comparable maturity
  appears, which would lower the cost of the deferred oracle.
* The harness cannot express a case the layer needs — an exchange the mocks cannot model, or an
  assertion its graders cannot make. That replaces the harness, not the layer.
