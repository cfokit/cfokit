# CFOKit — Product Vision

> **This is the source document for product positioning.** The root `README.md` derives a
> marketing-oriented introduction from it; the two are not maintained independently. When
> positioning changes, change it here first.
>
> This document states *why CFOKit exists and who it serves*. Requirements and architecture
> both derive from it, so it cites neither.

## Tagline

**Open source books your agent keeps.**

## Mission

Give every business a finance function it can afford to run.

## Identity

| | |
|---|---|
| **Name** | CFOKit |
| **GitHub** | `github.com/cfokit/cfokit` |
| **Domain** | cfokit.ai |
| **Brand** | The open source CFO toolkit |
| **Licence** | MIT |

## The problem

### What a CFO actually does

A CFO owns capital, cash, and the plan. Raising money and managing the people who supplied
it, whether that is a board, an investor, or a lender. Treasury, meaning payroll clears,
working capital does not strangle the business, and someone has a view on when to pay and
how hard to chase. The operating model and the budget, and the account of why actuals
diverged from it. Pricing and unit economics. Whether to hire, build, buy, or shut
something down. Risk, which covers insurance, fraud exposure, contract terms, entity
structure, and tax strategy.

The role is forward-looking and externally facing, and the person is accountable for
outcomes rather than for documents. Financial statements are an input to nearly all of it.

Producing those statements is two other jobs. A bookkeeper records and reconciles through
the month; a controller closes it and stands behind the result. A CPA then works from the
closed year and files against it.

### What small companies actually have

Below a certain size a company has neither of the other two, and a CPA only if it engages one. The recording and
closing still has to happen, so it lands on whoever is nearest and gets done late,
inconsistently, and under deadline pressure. Everything downstream inherits that condition: the forecast, the board
pack, the loan application, the return.

The name CFOKit describes the shape of the answer. It is a kit of Agent Skills that serves a
CFO by doing the work beneath one, so that whoever holds the CFO role — a founder, a
fractional CFO, or an owner-operator — has something worth working from.

## Who it serves

**The company owns its books, in every case.** Whether CFOKit runs on the company's own
machine or is hosted for it, the account belongs to the company — never to its accountant or
its fractional CFO, who work inside it at the company's invitation. Who operates the product
and who recommends it both vary, and conflating those three roles produces bad positioning, so
they are kept separate throughout this document.

Two segments arrive at the problem from different directions.

### Segment 1 — The tech company

Delaware C-corp, or an LLC before the first raise. Outside investors and an outside board,
or an intention to have both. The same company walks all four stages, and each one is defined
by something that changed at the company rather than by who happens to be doing the books.

| Stage | What changed | Who operates the books | Who advocates |
|---|---|---|---|
| **0.** Founding | No outside money and no finance help of any kind | Founder | Peers, on Hacker News and Reddit |
| **1.** Revenue | Enough cash to stop doing the books personally | Founder, plus a bookkeeping service | None yet |
| **2.** Seed to Series A | Institutional money arrives, and a board and reporting obligations with it | Fractional CFO, alongside the founder | The fractional CFO |
| **3.** Scaling operations | Headcount and volume outgrow a part-time finance function | Controller and staff accountants | The controller, internally |

A CPA sits alongside most rows of that table, and alongside much of segment 2. That is why the
CPA channel matters more than any single stage in it.

Stage 0 can last for years. Nothing about the transitions is a churn event for the company,
so CFOKit either follows it up the sequence or is replaced at one of the boundaries. That is
why the ledger's shape has to anticipate more than the product currently does. Accrual becomes
unavoidable when institutional money arrives, and it needs the obligation and the settlement
recorded as separate related events — which is not a formatting choice that can be added
later.

### Segment 2 — The owner-operator

An LLC or an S-corp that is deliberately not scaling. No outside investors, no board, no
plan to hire an accounting team. An independent consultancy that may never have full-time
employees, or a business with a modest number of hourly workers — a restaurant, a retail
shop, a construction firm.

There is no stage sequence here, because the company is not trying to become something else.
Their financial questions are about paying themselves, whether they can afford someone, what
they owe in tax, and whether a particular job or location makes money. The only professional
in the loop, where there is one at all, is a CPA seen once a year.

### Two kinds of complexity, and which one arrives first

Both segments meet both kinds. What differs is the order they arrive in and what sets them
off.

**Structural complexity** — accrual reporting, consolidation across entities, equity and the
cap table — is triggered by obligations to other people. Investors and lenders want accrual
statements; a second entity forces consolidation. A tech company usually meets this at stage 2,
because that is when the money arrives and brings the obligations with it. An owner-operator
meets it too, just from a different cause: a restaurant group running three locations has to
consolidate them, and an S-corp owner has distributions and basis to keep straight.

**Operational complexity** — payroll for hourly staff, sales tax, inventory, job costing and
progress billing — is triggered by what the business physically does. An owner-operator often
meets it on day one, because holding stock or employing hourly workers *is* the business. A
tech company meets it too: a sales team spread across states creates payroll obligations and
sales-tax nexus in every one of them, and SaaS is taxable in a growing number of jurisdictions.

Neither list belongs to a segment, and neither is universal. A solo consultancy may never hold
stock, never employ an hourly worker, never collect sales tax, and never answer to anyone
outside the business — none of it ever applies to them. What decides is what an entity actually
does and who it actually owes, which is why each of these is gated on a trigger rather than on
a stage number.

### Advocates, and other people in the room

**Fractional CFOs are advocates, not account owners.** They carry four to eight clients at five to
ten hours per week each, which caps the practice at roughly one person's capacity. A client
whose ledger is already current and closed does not consume the first month of an engagement
in reconstruction, which lets the fractional CFO scope to strategy, planning, and compliance,
and lets them tell the client to drop the bookkeeping service. They only appear in segment 1
from stage 2 onward, and a company can decline to have one at all, so this channel is real but
narrow.

**CPAs are the structural channel.** Filing is not optional and the deadline is fixed, and most
companies past the simplest returns engage someone to prepare theirs — which makes this the
relationship worth building around. It is not universal: plenty of owner-operators prepare and
file their own returns, and nothing about CFOKit assumes otherwise. The channel is broad rather
than total.

The mechanism is the one Vanta built with SOC 2 auditors. Vanta's audit partners pull evidence
directly from the platform, which cuts their fieldwork and sometimes their fee, so they
recommend it to clients — and the audited company pays, never the auditor. A CPA preparing a
return spends much of the engagement chasing the client for detail that already exists
somewhere. A CPA who can query the ledger directly, against books closed on a schedule with
every assignment traceable to a rule, finishes faster and can price accordingly. The client
gets a cheaper return and the CPA gets a reason to put the next client on CFOKit.

This makes the ad hoc query surface a CPA-facing feature rather than only an owner-facing one,
and it sets the standard for tax work: the measure is whether a preparer can answer their own
questions without emailing the client. The persona itself is not developed in detail yet.

**Contributors** are developers who want the system to exist and to extend it. They write the
connector for their own bank and the compliance rules for their own state, which is what
the connector protocol boundary is for. They overlap with segment 1 founders only
incidentally.

## Value proposition

CFOKit is a kit of Agent Skills that does bookkeeper and controller work against a
double-entry ledger the company owns.

Transactions arrive from bank, card, and payment-processor feeds and are assigned by stored
rules that run deterministically. The same transaction against the same rule set produces the
same result, and the rule that produced it stays on the record.

A payee name alone is frequently not enough to decide. An Amazon charge might be office
supplies one week and marketing materials the next, so rules match on more than the merchant,
and anything the rule set cannot resolve is asked rather than guessed. Approval is sought for
the rule, so the same question is not asked twice.

Periods close on a schedule. Corrections are reversing entries rather than edits, so the
history is complete by construction. Statements come out in a form a lender, a board, or an
accountant will accept.

The ledger is reachable over MCP and a documented HTTP API, so the questions do not have to be
anticipated in advance. An owner can ask what they spent on contractors last quarter. A CFO
can ask something considerably harder. Guardrails live in the skill: entity scope is enforced
server-side regardless of what is asked, answers come from the books rather than from
estimation, and the skill declines what the data cannot support.

The CFO seat is never empty. Where no professional holds it, the founder or the owner-operator
does, on top of running the business, and a guidance skill answers the questions that person
actually asks about runway, margin, and whether a hire is affordable. It states its limits, and
sends anything turning on tax election, entity structure, or financing to a professional.

The software is MIT licensed and runs on a laptop with no cloud account. The hosted service
is the same software, operated under third-party audit.

### What it displaces

| Today | Monthly |
|---|---|
| QuickBooks Online, Simple Start through Plus | $38–115 |
| Outsourced bookkeeping, typical small business | $300–900 |
| **Combined** | **$340–1,000** |

A fractional CFO retainer of $4,000–8,000 per month is not displaced. It gets re-pointed at
the work it was engaged for.

> **Figures.** QuickBooks tiers reflect Intuit's May 2026 increase of 15–25%, the largest in
> the product's history. Bookkeeping and retainer ranges are 2026 market surveys. Sources are
> listed at the end of this document.

### Why this beats a bookkeeping service

Measurable criteria, not adjectives:

| | Human service | CFOKit |
|---|---|---|
| **Latency** | Close lands two to six weeks after month end | Books current to yesterday |
| **Consistency** | Staff turnover means re-teaching the business | Rules are stored data and outlive any staffing change |
| **Question volume** | The same recurring charge queried monthly | Rules approved once; queries trend to zero |
| **Traceability** | A finished P&L, no visible reasoning | Every posting names its rule and source transaction |

### What pristine books make possible

The advantage compounds at the moments that matter most, and it accrues to a human rather
than to the software. An equity event, an acquisition, a legal settlement, an audit, a
forensic review — each one is an expert asking hard questions of historical data, and what
determines whether they can answer is the quality of the record they inherit.

A CFO working from books maintained continuously, assigned by traceable rules, and closed on
schedule can ask things that are unavailable against a ledger reconstructed under deadline
pressure. A forensic accountant gets a complete append-only history instead of a file with a
retention-limited audit log behind it.

**The competitor is Intuit, not a bookkeeping firm.** Intuit has put over $2B into AI on the
platform, and Intuit Assist with "Continuously Clean Books" is shipping into the higher
tiers now. *"AI does your bookkeeping"* is the incumbent's current roadmap and is not a
differentiator. Consistency and traceability are, and both are hard to reach from a
probabilistic categoriser sitting on a retention-limited audit log.

## Objectives

What success looks like, each with the measure that settles it. An objective without a measure is
a slogan; these are the statements CFOKit can be held to.

**The books.**

| | Objective | Measure of success |
|---|---|---|
| **OBJ-1** | The company's books are kept without the company keeping them | Transactions are recorded, classified, and reconciled with no person performing the recording. A person is involved only to answer what the stored rules cannot resolve, and to approve the rule that settles it; an approved pattern is not asked about again |
| **OBJ-2** | The books are current, and a close is never waiting on CFOKit | A transaction is recorded within one day of reaching the system, rather than of its transaction date. Anything the rules cannot resolve is asked as it arrives, not discovered at period end. A period is ready to close on the day the entity scheduled, with nothing left to decide; where it is not, an unanswered question is the only permissible cause, and what is outstanding and how long it has waited are visible throughout |
| **OBJ-3** | The numbers are exact, and nothing posted changes afterwards | Every amount is recorded exactly: no representation error, no accumulated drift, a balance that is the exact sum of its postings. Booking agrees with an independent implementation of double-entry, with every divergence documented. A posted record is never altered or deleted — a correction is a new entry, and both remain visible. An operation repeated or retried books once |
| **OBJ-4** | Every number explains itself | Any posting resolves to what caused it and what decided it — the source transaction and the rule that assigned it, the person who entered it, the entry it reverses, or the migration that carried it in — and that attribution survives for the life of the record |

**What they are worth.**

| | Objective | Measure of success |
|---|---|---|
| **OBJ-5** | The recurring cost of keeping the books goes away, in whichever form the company pays it | A company paying for an accounting subscription and a bookkeeping service cancels both. An owner who kept the books personally stops spending the hours. Which of these applies depends on what the company did before; that at least one is removed in full does not |
| **OBJ-6** | The people the company answers to accept its output as it stands | Statements are produced in a conventional form, on the entity's declared basis, and every line resolves to the detail supporting it without leaving the system. A preparer, a lender, or a board works from what CFOKit produces without asking the company to reconstruct anything |
| **OBJ-7** | A company is never forced off CFOKit by growing | The books absorb what growth brings — a second entity, a change of basis, more people holding distinct roles, an advisor working across clients, payroll, sales tax, obligations to lenders and boards — as changes to existing books rather than as reasons to leave. A company that genuinely outgrows CFOKit has left the small-business segment, not exceeded the product |

**Control and assurance.**

| | Objective | Measure of success |
|---|---|---|
| **OBJ-8** | Only the people an entity has authorised reach its books | Cross-entity access does not occur, and is prevented at the data layer rather than by convention. Every access resolves to the principal that made it — the person, and the skill acting for them where one did — and to the role held at the time. Authority is determined server-side, whatever the caller asserts |
| **OBJ-9** | The company can prove all of this to an examiner | The system supplies, from its own records, the access, change, and processing evidence a SOC 1 and a SOC 2 Type II examination require, over a period of operation rather than at a moment. What the software cannot evidence — the operator's own controls — is stated rather than implied |

**Independence.**

| | Objective | Measure of success |
|---|---|---|
| **OBJ-10** | The company can leave with everything, at any time | Two exports, both self-service and available in any entity state short of deletion: one another accounting system can read, and one that reproduces the entity's books, their history, and their attribution in another CFOKit deployment |
| **OBJ-11** | The system runs with no vendor relationship | The books can be kept end to end — in, classified, posted, reconciled, closed, reported — with no cloud account, no signup, and no third-party credential. Every external service is optional and additive, and what is lost without each one is stated |
| **OBJ-12** | It is a project outsiders can work on | A newcomer builds, tests, and runs the whole system from a clean checkout, with the full suite passing, no credentials, and no account. Adding a feed provider, a delivery channel, or a rule set is an additive change against a stable boundary rather than a fork |

## The commercial thesis

CFOKit is MIT licensed and stays that way. Anyone can run it, fork it, or build on it without
asking, and the self-hosted build is complete rather than a limited edition.

The commercial product is the hosted service, and what it sells is assurance.

Nobody reads the source to decide whether to trust their general ledger to it. Early
adopters trust it because trying it costs nothing and because people they recognise are
already running it. Everyone downstream — a fractional CFO, an accountant, a lender —
trusts it because an independent auditor has attested to how the hosted service is operated.
That report is the one asset a fork cannot copy, and the operating history behind it takes
years to accumulate.

This is the position argued at [kindnessflywheel.org](https://kindnessflywheel.org): as AI
compresses the cost of building software, the software stops being the defensible part, and
what remains is trust and the willingness to behave well over a long period. CFOKit both
applies that hypothesis and tests it.

### Cost structure

CFOKit ships as an Agent Skill that installs into an agentic runtime the user already has,
and that runtime supplies its own inference. The end user carries the token cost, the same
way they carry the cost of the machine the agent runs on.

What CFOKit hosts is the ledger, the MCP surface, the API, and the compliance posture around
them. That is a conventional SaaS cost structure of Postgres, compute, and storage, and it
does not move with token prices. Pricing is therefore a question about the value of the stack
being displaced, decided on ordinary SaaS margins.

This also shapes the product surface. Because the intelligence sits in the user's runtime
rather than behind our API, what we expose has to be a complete, well-described data
interface and not only a fixed menu of reports.

The standard statements are standard: a profit and loss, a balance sheet, a cash flow
statement, and a receivables ageing report have settled definitions, and CFOKit produces them
deterministically rather than composing them afresh each time somebody asks. The data interface
is what answers the questions nobody wrote a report for.

### What the thesis constrains

Two things follow, and they bind the product:

- **Leaving has to be genuinely easy**, or the software is not really free. Export is
  continuous and complete, and the self-hosted build stays at parity with the hosted one.
  Bench's collapse in December 2024 locked roughly 12,000 customers out of their own books
  days before tax season, with no clean export path. That is the failure this constraint
  exists to prevent.
- **Honesty about ordinary things** — an outage, a slipped date, a price increase — is the
  only evidence of character available before a crisis, and it is what makes the rest
  credible.

## Positioning by audience

**For the founder.** Your books are essential and non-differentiating. You need them and you
need to trust them, and the return on your own time in them stops the moment they are correct.
Nothing you do above that threshold makes the business better. CFOKit keeps them current and
shows you why every transaction landed where it did, so trusting them is not an act of faith.
It costs nothing to try. Move to the hosted service when you would rather not run your own
Postgres.

**For the owner-operator.** You already pay for QuickBooks and still do the work. CFOKit does
the work: transactions categorised as they arrive, books that are current rather than
reconstructed in April, and straight answers about what you can afford.

**For the fractional CFO.** You were hired for the plan and the capital, and the first month
of every engagement goes to making an inherited ledger trustworthy. A client on CFOKit
arrives closed, current, and traceable, so the engagement is the work you sell.

**For the developer.** MIT licensed, so you can run it, fork it, or build on it without asking
anyone. It comes up in one command with no cloud account and no signup, the booking engine is
tested against an independent implementation rather than against its own assumptions, and
adding a bank or a payment provider is an additive change against a stable extension point.

## Community identity

The project succeeds when people describe themselves in these terms unprompted.

**Users say:**

- "I run my company's books on CFOKit"
- "As a fractional CFO, I get every client onto CFOKit"
- "CFOKit keeps my books current so I only think about them once a quarter"

**Contributors say:**

- "I'm a CFOKit maintainer"
- "I built the CFOKit Stripe integration"
- "Contributing S-corp compliance rules to CFOKit"

A contributor can only say "I built the CFOKit Stripe integration" if adding a provider is an
additive change behind a stable protocol, so provider-specific code has to sit behind one and
the connector package cannot be named after a vendor.

## Launch messaging

The audience for launch is the part of segment 1 at stage 0 that will self-host, the one group
whose trust comes from the software being free rather than from an audit report.

**Hacker News:** "Show HN: CFOKit – Open source double-entry books your AI agent maintains"

**Reddit (r/smallbusiness, r/startups):** "I replaced my $500/month bookkeeping service with
open source agents – here's the ledger design"

**Announcement post:**

> Introducing CFOKit
>
> Open source, agent-maintained books.
>
> • Bank and card feeds in, categorised by rules you approve once
> • Real double-entry, append-only, tested against Beancount
> • Statements a lender or your accountant will accept
> • MIT licensed, runs on your laptop, no cloud account
>
> github.com/cfokit/cfokit

## What CFOKit is not

These are decided, and they bound what the positioning may promise:

- **Not a CFO.** It does the bookkeeper and controller work a CFO relies on. The role itself is
  never vacant — a fractional CFO holds it where one is engaged, and otherwise the founder or
  the owner-operator does. Where that person wants help with the judgement rather than with the
  books, the guidance skill answers a bounded set of questions and states its limits.
- **Not a web application.** CFOKit is agents and an API rather than a dashboard you log into.
  This is a **gate, not a prohibition**: a web UI or an admin console takes a deliberate
  decision to reverse, not a drift. Rendered report output has not been decided either way.
- **Not a bank.** It reads financial data and keeps books; it does not move money.
- **Not a filing agent.** It produces the closed year, the schedules, and the supporting
  detail a preparer works from. Whoever prepares the return files it.
- **Not a SaaS-only product.** Self-hosting is a product promise, which is why the local stack
  needs no cloud account. The
  reason is control, cost, and freedom from lock-in. It is not the trust mechanism — that is
  the attestation on the hosted service.

## Sources

Market figures used above, checked August 2026.

- [Eightx — fractional CFO cost and engagement size, 2026](https://eightx.co/blog/fractional-cfo-cost-pricing-guide)
- [CFO Advisors — fractional CFO hourly rate benchmarks, 2026](https://cfoadvisors.com/blog/fractional-cfo-hourly-rates-2026-benchmarks)
- [ProjectionHub — client load and hours per client](https://www.projectionhub.com/post/how-to-become-a-fractional-cfo)
- [Cocountant — outsourced bookkeeping costs, 2026](https://cocountant.com/blog/bookkeeping/outsourced-bookkeeping-costs-2026-pricing-guide/)
- [Steph's Books — QuickBooks Online price increase, May 2026](https://stephsbooks.com/news/quickbooks-online-price-increase-2026)
- [Beancount.io — QuickBooks Online cost breakdown, 2026](https://beancount.io/blog/2026/07/26/quickbooks-online-price-increase-2026-cost-breakdown-guide)
- [Inc. — Bench customers on the shutdown](https://www.inc.com/brian-contreras/benchs-jilted-customers-say-the-accounting-startups-problems-began-long-before-its-abrupt-shutdown/91102407)
- [Vanta — auditor partner network](https://www.vanta.com/partners/auditors)
