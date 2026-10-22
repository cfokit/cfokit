---
status: "proposed"
kind: "substrate"
date: 2026-10-20
decision-makers: [Geoff]
---

# ADR-0074: A documentation clip is cut from a passing end-to-end run of the use case it shows

## Context and Problem Statement

User documentation lives in `docs/tutorials/`, `docs/how-to/` and `docs/explanation/` (ADR-0001).
A page that shows a person doing something reads better with the doing in it: a few seconds of the
screen, the prompt typed, the answer arriving. The question is where those clips come from, and
what keeps them true.

Facts that bear on the answer:

* **Every commit is generated, so the product changes fast.** A screen, a label or a step in a
  flow can change several times a week. A clip that is not remade when its flow changes is wrong
  within days, and nothing about a video says it is out of date.
* **One clip is already made this way.** The getting-started screencast in the README is the video
  of `web/e2e/onboarding.spec.ts`, a Playwright test that signs up, imports the synthetic export and
  checks the books over REST. CI runs it against `compose.yaml` paced for a person to follow
  (`E2E_PACE`, 1,200 ms a screen, about fifteen seconds added), converts the video with ffmpeg to an
  MP4 and a GIF, and publishes both as release assets. It records only on a push to main that
  changes a path the flow shows. It is one long video; a page wants short clips, one per step.
* **Most of the work happens in a conversation.** After getting started, a capability is built for
  the agent first (ADR-0068), and CFOKit's own runtime is the web app, hosting the same skills,
  tools and panels as the person's own agent (ADR-0034 § 4). So the clips most pages need are of a
  conversation, not a page.
* **Some work starts with nobody typing.** A statement arrives or a feed synchronizes, the queue
  runs a pass (ADR-0061), and the person meets the result, or the questions it left, the next time
  they open the conversation.
* **The person's own agent belongs to someone else.** Claude, claude.ai and ChatGPT draw their own
  interface and change it on their own schedule. A custom connector cannot reach `localhost`
  (`docs/how-to/connect-claude.md`), so driving one against the compose stack needs a public
  deployment and a signed-in account. Consumer terms for these products restrict automated access
  outside their APIs; the current wording was not verified for this record.
* **A model's output varies between runs**, even with the model pinned. The records a turn leaves
  can be checked; its prose cannot be checked as a value (ADR-0036 § 4).

## Decision Drivers

* **A clip shows what the current build does**, and when the flow changes the clip is remade or
  the build says it cannot be, rather than going stale unnoticed.
* **Expected values come from outside the implementation** (ADR-0036), so a clip never shows a
  figure that nothing checked.
* **Runs on the local stack**, `compose.yaml` without the dev overlay, as the rest of the suite does
  (ADR-0004, ADR-0018), needing no account anywhere but the inference credential a conversation
  needs.
* **Shows the conversation**, including unattended work that ends there, since that is where most
  of the product is used (ADR-0068).
* **Depends on no interface CFOKit does not control.**
* **Costs nothing on a pull request that changes no recorded flow**, and adds no gate a model can
  fail.

## Considered Options

* Cut each clip from a passing end-to-end run of its use case, with conversations in CFOKit's runtime
* Record clips by hand with a screen recorder
* Automate the person's own agent's interface, such as claude.ai, in a browser
* Replay a stored transcript into a rendered conversation
* Screenshots only, taken by the same tests

## Decision Outcome

Chosen option: "Cut each clip from a passing end-to-end run of its use case, with conversations in
CFOKit's runtime", because it is the only option in which a clip cannot outlive the behavior it
shows, and it extends the one clip that already exists rather than adding a second way to make one.

> A clip in user documentation is cut from a Playwright run of the use case it shows, against
> `compose.yaml`, that asserted on the records the use case leaves and passed.

### 1. A documented use case is a recorded spec

Each tutorial or how-to page with clips has one Playwright spec in `web/e2e/` that performs its use
case as a person would. The page names its spec, and the spec names its page. Each step the page
shows is a `test.step`, and its title is the clip's caption.

A use case starts the way it starts in the product:

* **A page the person opens**, as getting started does.
* **A prompt typed into the runtime's chat window**, the web app of ADR-0034 § 4.
* **An unattended trigger**: the spec causes it the way the product does, such as recording a
  statement through the published API as the person, waits for the run it enqueues, and then opens
  the chat, where the clip shows what the person meets.

Every use case that involves the agent ends in the chat.

### 2. The assertions are on records

A spec asserts on what the use case leaves: the transaction and whether it is draft or posted, its
postings, the audit row, an open notification. Expected values come from the fixture's own stated
figures or another source outside the implementation (ADR-0036). A spec never asserts on the
agent's prose.

### 3. Clips are cut at step boundaries, from a passing run only

The recording run is paced (`E2E_PACE`). A reporter writes each step's start and end, and the
recording job cuts one MP4, one still and one WebVTT caption track per step from the run's video,
after the test step has passed. A failed run publishes nothing, and the page keeps its last good
clips.

### 4. When a recording is made and published

* **A spec with no model in it** is a protocol integration test (ADR-0036 layer 3): it runs unpaced
  on every pull request that changes code, records on a push to main that changes a path its flow
  shows, and publishes automatically, as getting started does.
* **A spec with a model in it** is an eval (layer 4): it does not run on a pull request and gates
  no commit. It records on the same trigger, against the pinned model, and its clips are kept as a
  workflow artifact. A person reviews them and publishes them by running the publish job by hand.

### 5. Conversations are recorded in CFOKit's runtime

A conversation is recorded in the runtime's chat window, never in a third-party host. The runtime
hosts the same skills, tools and panels as the person's own agent, so the conversation is the
same one; the page says the clip shows CFOKit's web app, and that it reads the same in the person's
own agent. A step that happens only in a third-party host, such as adding the connector in Claude,
is shown with stills or text and is outside this record.

### Consequences

* Good, because a clip can only be made by a run that passed, so a changed flow either re-records or
  fails visibly in CI.
* Good, because each recorded spec is also a test, and the evals that ADR-0036 layer 4 lacks gain
  cases as pages are written.
* Good, because it reuses the getting-started pipeline: Playwright's video, the pace, ffmpeg, the
  path-triggered `record` output and release assets.
* Good, because nothing depends on an interface CFOKit does not control.
* Bad, because a page that needs a conversation clip waits for the runtime's chat window, which
  this record does not build.
* Bad, because a reader using Claude sees CFOKit's chat rather than their own host's, with
  different surroundings around the same conversation.
* Bad, because conversation clips cost tokens on every re-recording and a person's review before
  they are published, and their prose changes from one recording to the next.
* Bad, because each paced flow adds its pauses to the recording job, and each new spec adds its
  paths to the `record` list by hand.
* Neutral, because clips have no narration. Captions come from the step titles.

### Confirmation

Partly by the pipeline and partly by review:

* **The pipeline:** the recording job cuts clips only after the test step succeeds, so a failing
  spec publishes nothing. A spec with a model in it publishes only when a person runs the publish
  job.
* **Review:** a page with a clip names its spec; a recorded spec's paths appear in the `record` list
  in `.github/workflows/ci.yml`; a spec asserts on records and not prose. No check enforces these.

## Pros and Cons of the Options

### Cut each clip from a passing end-to-end run of its use case, with conversations in CFOKit's runtime

* Good, because it meets every driver.
* Bad, because conversation clips depend on the runtime being built, and show its chat rather than
  the reader's own host.

### Record clips by hand with a screen recorder

The strongest case for it: the best-looking result, with narration, chosen moments and no
infrastructure, and a person can record any host, Claude's included, signed in as themselves.

* Good, because the clip can be polished, narrated and edited.
* Good, because it can show any interface, including third-party hosts.
* Bad, because nothing notices when it goes stale. A changed label or step leaves the clip wrong
  until someone happens to see it, and with the product changing several times a week that is most
  clips most of the time.
* Bad, because remaking a clip costs a person's time for every flow change, which grows with every
  page.

### Automate the person's own agent's interface, such as claude.ai, in a browser

The most authentic clip a reader on Claude could see: their own host, exactly as they will use it.

* Good, because the reader sees their own host's interface.
* Bad, because it cannot run against the compose stack. A custom connector cannot reach
  `localhost`, so it needs a public deployment and a signed-in account with a session that expires.
* Bad, because the interface is someone else's and changes without notice, so a recording breaks
  for reasons outside the repository.
* Bad, because consumer terms for these products restrict automated access outside their APIs.

### Replay a stored transcript into a rendered conversation

Deterministic: the same conversation every time, so its clips could gate a pull request and need no
review and no tokens.

* Good, because the clip is identical on every run and costs nothing to remake.
* Bad, because it shows what a model said once, not what the current skill and tools do. A change
  to either leaves the transcript in place and the clip wrong, which is the staleness the first
  driver exists to prevent.
* Bad, because assertions against a replayed run check the transcript, not the product.

### Screenshots only, taken by the same tests

Cheap, stable and searchable, and the same specs would take them.

* Good, because a still is small, never varies in timing, and is easy to keep beside the text.
* Bad, because a conversation's order is what a person needs to see: the prompt, the agent working,
  a panel, a question back. Stills lose the order and the waiting.
* Neutral, because nothing here prevents a page from also using stills from the same run.

## More Information

**Follow-on obligations.**

* The recording job gains the step reporter and cuts per step, replacing its single conversion of
  the whole video; getting started becomes the first page cut this way.
* A publish job a person runs by hand, for clips from a spec with a model in it.
* The runtime's chat window gives the transcript and the prompt field accessible roles and names,
  so a spec addresses them as a person and a screen reader would, as the getting-started spec does
  the pages.
* The runtime starts an agent run from a queued job as well as from a typed prompt, so an
  unattended use case has a run to wait for. That is the runtime's to decide (ADR-0034).
* Probable `web/CLAUDE.md` rules: a page with clips names its spec; a recorded spec adds its paths to
  the `record` list.

**Reversal cost.** Low. Clips are outputs. Dropping them leaves pages with text, and the specs stay
as tests.

**Not decided here.** Narration, and where pages are published beyond the repository.

**A page shows a still, not an animation.** GitHub's Markdown shows an image from a release inline
but does not play an MP4, so each step appears as a still of how it leaves the screen, linking to
its MP4. A still shows the screen the text describes, and a page of looping animations is too busy
to read. The README's one GIF of the whole run stays, where a single moving preview is the point.

Related: ADR-0001 (where user documentation lives), ADR-0034 (the runtime whose chat window is
recorded), ADR-0036 (the layers a recorded spec belongs to), ADR-0049 (the web client), ADR-0061
(unattended work), ADR-0068 (conversation first).

## Revisit when

* The runtime is not the web app, so there is no chat window of CFOKit's to record.
* The recording job takes longer than ten minutes, so pacing every flow on every change stops being
  cheap.
* Reviewers reject more than one in five conversation recordings, so recording against the live
  model costs more than it returns.
* A host most readers use offers a sanctioned way to drive and record its interface.
