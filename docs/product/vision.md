# CFOKit — Product Vision

- **Status:** Draft
- **Date:** 2026-08-17
- **Owner:** Geoff

> **This is the source document for product positioning.** The root `README.md` derives a
> marketing-oriented introduction from it; the two are not maintained independently. When
> positioning changes, change it here first.
>
> This document states *why CFOKit exists and who it serves*. It does not describe
> capabilities — those are in [`requirements.md`](requirements.md) — and it does not make
> architectural commitments, which live in [the ADRs](../adr/README.md).

## Tagline

**Every business needs a CFO. Now every business can have one.**

## Mission

Make CFO-level financial intelligence accessible to every business, regardless of size.

## Identity

| | |
|---|---|
| **Name** | CFOKit |
| **GitHub** | `github.com/cfokit` |
| **Domain** | cfokit.com |
| **Brand** | The open source CFO toolkit |
| **Licence** | MIT |

## The problem

CFO-level financial work — bookkeeping, tax preparation, cash flow monitoring, compliance
tracking, financial reporting — is necessary at every company size but only affordable
above a certain one. A full-time CFO costs around $200K/year. Below that threshold the
work does not disappear; it lands on a founder at the end of a quarter, or on a fractional
CFO absorbing operational bookkeeping across a dozen clients instead of advising.

## Value proposition

CFOKit gives you AI agents that handle the work a CFO would do: bookkeeping, tax
preparation, cash flow monitoring, compliance tracking, and financial reporting. Deploy
once, manage multiple clients through Slack.

## Who it serves

| Audience | Situation |
|---|---|
| Solo founders | Managing S-corps and LLCs without finance staff |
| Small business owners | Cannot justify a full-time CFO hire |
| Fractional CFOs | Managing 5–15 clients simultaneously |
| Consultants and service businesses | Tech-savvy, want automation over process |

## Positioning by audience

**For business owners.** You need CFO-level financial intelligence. You can't afford a
$200K/year hire. CFOKit gives you an AI CFO team for $15/month.

**For fractional CFOs.** Manage 10+ clients without the bookkeeping burden. CFOKit handles
the operational work in dedicated Slack channels per client. Save 15+ hours per client per
month.

**For developers.** Open source, modular architecture. Skills-based system. Cloud-native.
Extensible via MCP. Built with Claude AI.

## Community identity

The project succeeds when people describe themselves in these terms unprompted.

**Users say:**

- "I use CFOKit to manage my startup's finances"
- "As a fractional CFO, CFOKit is my secret weapon"
- "CFOKit handles the CFO work while I focus on product"

**Contributors say:**

- "I'm a CFOKit maintainer"
- "I built the CFOKit Stripe integration"
- "Contributing S-corp compliance rules to CFOKit"

That second list is a design constraint, not an aspiration. A contributor can only say "I
built the CFOKit Stripe integration" if adding a provider is an additive change behind a
stable protocol — which is why provider-specific code sits behind one
([ADR-0003](../adr/README.md)) and why the connector package is not named after a vendor.

## Launch messaging

Held here so the eventual marketing README stays consistent with it.

**Hacker News:** "Show HN: CFOKit – Open source AI agents that act as your CFO team"

**Press angle:** "Former [company] CTO open sources CFOKit, giving every startup an AI CFO"

**Reddit (r/entrepreneur, r/startups):** "I automated my S-corp's CFO work with open
source AI agents – here's how"

**Announcement post:**

> Introducing CFOKit 🎯
>
> Every business needs a CFO.
> Now every business can have one.
>
> Open source AI agents for:
> • Bookkeeping automation
> • Tax preparation
> • Cash flow monitoring
> • Compliance tracking
>
> Perfect for solo founders, small businesses, and fractional CFOs.
>
> ⭐ github.com/cfokit

## Open questions

Tracked here rather than settled, because each needs a decision before it can be built on.

| Question | Why it is open |
|---|---|
| The $15/month price point | Implies a managed tier with billing and metering, none of which is specified or decided. |
| "AI CFO team" as plural agents | Whether the bookkeeper, tax, cash-flow, and compliance roles are separate skills or one skill with several modes is undecided. |
| How reports and dashboards are rendered | REQ-B3 promises statements "a human can hand to a lender or board", which a chat message is not. Options range from a static generated file to a served report URL. The scope gate (ADR-0012) is now written, so this needs an ADR passing that gate — as Slack did in ADR-0022. A served URL additionally has to answer ADR-0018's rejection of a second authentication path. |
| Repository naming in launch copy | Announcement copy has referenced `cfokit/core`; the repository is `cfokit/cfokit`. Correct the copy, not the repository. |

## What CFOKit is not

Drawn from binding scope decisions ([ADR-0012](../adr/README.md)) so positioning cannot
quietly promise them:

- Not a web application. CFOKit is agents and an API, not a dashboard you log into. Note
  this is a **gate, not a prohibition** — scope discipline forbids building a web UI or
  admin console *without an ADR*, and rendered report output is an open question below,
  not a settled no.
- Not a bank. It reads financial data and keeps books; it does not move money.
- Not a filing agent. It prepares tax work; a human files.
- Not a SaaS-only product. Self-hosting is a product promise
  ([ADR-0003](../adr/README.md)), which is why the local stack needs no cloud account.
