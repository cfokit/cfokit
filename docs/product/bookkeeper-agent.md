# The bookkeeper agent

How the agent that keeps a company's books works, and what it is like to use. One agent, in two
places: the person's own Claude, on the desktop, with CFOKit as its connector and skill; and
CFOKit's own runtime in the web app, for managed bookkeeping. The same skills, tools and panels
serve both ([journey](journey.md)).

The agent is designed by playing it. Each scenario below is a conversation as the owner would
have it, written before anything is designed, and what the agent must know and do is read off
the conversations. What they show becomes requirements and design decisions; this document holds
the experience they are measured against.

## Where it runs

| | The person's own Claude | CFOKit's runtime |
|---|---|---|
| **Offering** | The hosted backend, or a self-hosted stack, with the person's own agent | Managed bookkeeping |
| **Who answers** | The person | CFOKit's agent; only what is the company's own call reaches the person |
| **What it already knows** | The person's own context about the business, in their Claude | Only what the company has told CFOKit |
| **How work reaches the person** | A notification that opens a chat with its question drafted (`PLT-07`) | A notification that opens the web app on the question (`PLT-07`, `PLT-24`) |
| **Where answers land** | The chat, with CFOKit's panels in it | The same panels, in the web app, on a desktop or a phone |

## What it is like

* **It comes to the person.** Work arrives on a schedule and is settled by rules; the person hears
  about what no rule settles (`BKP-12`, `PLT-07`). Owners look at their books rarely, and arrive
  cold with a question.
* **It asks once per pattern.** A person approves a rule, not a transaction, and is not asked about
  an approved pattern again (`BKP-09`).
* **It never guesses.** Where it cannot be certain, it asks; it never parks an item quietly
  (`BKP-12`).
* **It shows its work.** Any figure traces to its postings, and a posting to the rule and the
  principal that produced it (`RPT-08`, `BKP-10`, `LED-20`).
* **It names the company with every figure**, and keeps to the company the person chose
  (`SOC2-16`).
* **It speaks as someone who runs a business would**, not as an accountant (`NFR-19`).
* **It bothers people rarely.** Questions are batched, and one notification carries them.

## What it knows about the business

The bookkeeping skill is the same for every company: versioned, shipped, and a financial control
in its own right (`SOC1-34`). What the agent learns about how one company works extends that skill
for that company alone, and belongs to the company (`BKP-22`). The extension is kept in the shape
this repository keeps its own rules: a **thin summary** the agent works from at runtime, and the
**decision records** each part of the summary rests on — as a skill keeps a short body and loads
its reference files when it needs them. Together they are the company's operating procedures:
readable by a person without the agent, and exported with the books (`BKP-24`).

* **The skill prevails.** The procedures add to how the business is handled; they never relax what
  the skill requires or the ledger enforces (`BKP-28`).
* **The server supplies them.** The plugin is the same for everyone and the company is chosen in the
  conversation, so the procedures reach the agent through the tool contract once it is. That is
  what makes them the same whichever agent keeps the books (`BKP-23`). A person's own Claude keeps
  its general knowledge of the person; what concerns the company's books goes into the procedures,
  so switching agent or model does not start the learning over.
* **They are version-controlled documents.** Removing a statement is a revision like any other, and
  the summary can be reproduced as it stood on any date. Every entry records the version in force
  (`BKP-26`). Markdown files with their history are the natural form, and a candidate for carrying
  the knowledge to another model.
* **Approval turns data into instruction.** The procedures are learned from conversations and feed
  data the company did not author. Until a person approves a change, the agent treats it as data
  (`BKP-27`).

**They improve by a continuous-improvement cycle**, run each closed period by default (`BKP-25`):

1. **Check** — review the period's measures: corrections, reversals, questions the agent had to
   ask, items it could not resolve, rules overridden, reconciliation differences (`SOC1-37`).
2. **Plan** — propose changes to the procedures, each as a decision record carrying the evidence
   that prompted it (`BKP-26`).
3. **Approve** — a person approves; nothing changes without one, and a period's proposals reach
   them together, once. A period with nothing to propose reaches no one (`BKP-27`).
4. **Act** — the approved records update the summary, and the next period runs on it.

## What an examiner sees

The skill, the procedures and their decision records together are what a SOC 1 examiner reviews
for how transactions come to be categorized. The report covers CFOKit as the service organization,
so the two halves fall differently:

* **CFOKit's control is the process** — how procedures are learned, reviewed, approved, versioned,
  and kept for every company. An examiner tests that it operated, by sampling across companies.
* **Each company's approval is the company's control** — a complementary user entity control
  (`CUEC-6`). A company's own auditor may read its procedures; CFOKit's examiner tests that the
  approval happened.

**Evidence that it works** comes from the same measures the cycle reviews (`SOC1-37`), attributed
to the skill, model and procedure versions in force, so a change's effect is visible on either side
of it. The review is management's monitoring control, and its record each period — including a
period that proposes nothing — is the evidence that monitoring operated (`BKP-25`). The rest is
already required: what an approver was shown (`SOC1-05`), an entry explainable without re-running a
model (`SOC1-06`), exceptions and their dispositions (`SOC1-32`), and the evidence for a period
(`PLT-18`).

## Designing a scenario

Each scenario is written and reviewed in this order, and played in both places the agent runs:

1. **Context** — who is asking, what state the books are in, which offering and which surface.
2. **Dialogue** — the conversation as the owner would experience it. Written before any design.
3. **Must know / must do** — the data and actions the agent needs at each turn.
4. **Hack risks** — the turns where a smooth experience would need a workaround with the design as
   it stands. This is the detector for an agent that has to be hacked around.
5. **Acceptance checks** — testable statements, asserting on records rather than prose, so they can
   become evals.
6. **State changes** — what is written to the ledger, the rules, the decision records and the
   procedures.

Once about eight scenarios are written, their sections 3 and 4 merge into a capability matrix,
from which the tool contract, the state the agent keeps, its unattended work, the roles it acts
under and its output formats are derived.

## Scenarios

*Rests on* names the requirements a scenario exercises. *Not yet required* names what it needs
that no requirement states.

### Understanding the books

| Id | Scenario | Rests on | Not yet required |
|---|---|---|---|
| **UC-01** | Explain a variance: "why was marketing so high last month?" | `RPT-07`, `RPT-08`, `BKP-07`, `BKP-10`, `BKP-17`, `LED-20` | Prepaid and deferred expenses released on a schedule; likely-duplicate charges flagged |
| **UC-04** | "Can I afford it?" — cash, runway, obligations, and an S-corp distribution | `RPT-15`, `RPT-16`, `LED-17` | Forecasting from known obligations; an owner's basis and reasonable compensation |
| **UC-05** | "What do I owe, and when?" — deadlines and estimated taxes | — | A compliance calendar, which is out of scope today |
| **UC-06** | Ad hoc lookups: "what did I pay contractor X this year?" | `RPT-06`, `RPT-16` | Contractor reporting thresholds; tables readable on a phone |

### The daily rhythm

| Id | Scenario | Rests on | Not yet required |
|---|---|---|---|
| **UC-02** | Morning triage: a few unresolved items answered in one reply ("1=cogs 2=trip") | `BKP-09`, `BKP-12`, `PLT-07` | Several answers in one reply; a lesson from an answer reaching the procedures (`BKP-25`) |
| **UC-03** | A receipt arrives, as a photo or a forwarded email, and is matched to a transaction | `BKP-13`, `BKP-17`, `BKP-18`, `BKP-20` | A document matched to a transaction already in the books; documents arriving by email |
| **UC-18** | Quick capture: "paid the plumber $400 cash" — captured first, clarified later | `BKP-04`, `BKP-13`, `LED-07` | — |

### Trust and correction

| Id | Scenario | Rests on | Not yet required |
|---|---|---|---|
| **UC-07** | Correct an entry in a closed period, after the CPA already has the numbers | `LED-08`, `LED-09`, `LED-11`, `SOC1-17`, `RPT-17` | Telling whoever received an issued statement that it changed |
| **UC-08** | "You got that wrong": a bad rule touched 40 transactions | `BKP-10`, `BKP-11`, `LED-08` | Reversing every entry one rule produced, as one act |
| **UC-09** | The owner pushes back on a compliance call — meals, a home office | — | Citing authority, holding a position, deferring to a CPA |
| **UC-16** | A risky request: backdating, "make the numbers look better for the bank" | `LED-08`, `LED-09`, `IAM-16` | — |

### The periodic cycle

| Id | Scenario | Rests on | Not yet required |
|---|---|---|---|
| **UC-10** | Month-end close: reconcile, flag, approve, lock, and produce the package | `BKP-15`, `LED-11`, `PLT-14`, `RPT-13`, `RPT-14` | The package as a spreadsheet; the review cycle running at close (`BKP-25`) |
| **UC-11** | The CPA handoff, and the CPA's follow-up questions | `RPT-18`, `IAM-01`, `IAM-02`, `IAM-09`, `EXP-01` | — |
| **UC-12** | An S-corp compliance check: reasonable compensation, distributions against basis | — | Which part is a stated fact and which is the model's judgment |

### Getting started and staying connected

| Id | Scenario | Rests on | Not yet required |
|---|---|---|---|
| **UC-13** | First run: connect the bank, import a QuickBooks export, initial cleanup | `IMP-01`–`IMP-09`, `BKP-01` | — |
| **UC-14** | A bank feed breaks, or reconnects with duplicates | `BKP-16`, `BKP-21`, `NFR-03` | — |
| **UC-17** | The agent asks a question and the owner answers two days later | `BKP-12`, `PLT-07` | Reminders for a question still open |

### Several companies

| Id | Scenario | Rests on | Not yet required |
|---|---|---|---|
| **UC-15** | A fractional CFO: "which of my clients have unreviewed items?" | `IAM-08`, `PLT-04`, `SOC2-16` | A digest across companies that keeps each one's books apart |

## What UC-01 showed

**Must know and must do:**

* Compare an account to its trailing average and list the entries behind the gap.
* Read an attached document — an invoice's event date — when judging an entry.
* For any entry, say which rule assigned it, which past correction the rule came from, and who
  approved it.
* Handle prepaid and deferred expenses with a scheduled release.
* Flag likely duplicates — the same card, minutes apart — and say plainly that it cannot confirm
  one without the provider's billing page.
* Propose a reclassification, post it on approval in an open period, and link the approval to the
  conversation that gave it.
* Change a rule, and carry the correction that prompted it into the procedures.

**Hack risks:**

* A rule matching on the vendor alone, ignoring the memo, produced the error. Rules match on more
  than the payee (`BKP-07`), and need checking against the example they came from.
* "How did this get assigned?" fails without a stored record; reconstructing it afterwards is a
  hack. The record is required (`BKP-10`, `LED-20`).
* Deferral needs first-class scheduling, not a reminder to do it by hand.
* Linking a posted change to the conversation that approved it needs an id from the start.

**Acceptance checks:**

* Given a rule created from a marketing example, a same-vendor entry with a different memo is not
  assigned by it.
* Every posted entry records the rule that assigned it and who approved it.
* A deposit for a future-dated event lands in a prepaid account, with its release scheduled.
* Explaining a variance never invents an entry: every entry it cites exists in the ledger.

## Open questions

* **Confidence.** Posting automatically above a confidence threshold conflicts with assignment by
  stored rules applied deterministically, with nothing guessed (`BKP-06`, `BKP-12`). Whether
  confidence has any place — ordering questions, say, rather than posting — is undecided.
* **Compliance and tax judgment.** UC-05 needs a compliance calendar, which is out of scope today.
  UC-09 and UC-12 touch jurisdiction-specific tax rules, which statutory localization excludes, and
  the CFO seat, which is always a person's. Each needs a business decision before it is scripted.
* **The procedures' format.** Whether an established convention for standard operating procedures
  fits, and what form carries the business's knowledge to another agent or model. The exported,
  human-readable procedures serve until a standard for that emerges.
* **Erasing from the procedures.** Whether anything written in by mistake — personal data, another
  party's information — must be erased from every version rather than revised away.
* **A lesson and a rule.** Whether a lesson from the review cycle becomes a proposed rule
  (`BKP-09`), guidance in the procedures, or either.
