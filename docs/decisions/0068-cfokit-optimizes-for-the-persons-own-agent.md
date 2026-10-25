---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0068: After getting started, where the person's own agent and the browser trade off, CFOKit optimizes for the agent

**Requirements served:** `PLT-01`, `PLT-02`, `PLT-24`, `IAM-10`, `IMP-09`, `NFR-19`.

## Context and Problem Statement

A person reaches CFOKit in three places: their own agent, such as Claude Desktop or claude.ai with
CFOKit connected (`PLT-01`, `PLT-02`); CFOKit's web pages (`PLT-24`); and, with managed bookkeeping,
CFOKit's own runtime, which hosts the same skills, tools and panels as their agent does (ADR-0034
§ 4). All three are supported. But most capabilities fit one of them better, and each time one is
designed the same question comes up: which comes first, and which gets the compromise.

Getting started is decided separately (ADR-0058): a person who arrives on the web stays there until
their books are in, because connecting an agent before they have seen anything of their own costs
more people than it serves. This record covers everything after.

The cost of deciding each time is that every capability splits differently and nobody can say
which surface the product is built around. A person ends up using pages for some things and the
conversation for others, with no rule about where each lives.

Facts that bear on the answer:

* **The person's agent already knows the business.** In a customer discovery interview, a
  founder setting up a two-member LLC said their Claude already holds the
  business's structure, contracts, policies and the state's statutory requirements, and that not
  starting over was the attraction of bringing their own model, more than which model it is. Setting
  up books is mostly answering questions about how the business works, and that context is where
  the answers are.
* **Setup is advice, not configuration.** In the same interview, the founder wanted to say how the
  business works and be told what applies, what the choices are and what to connect, and resented
  features that do not apply, and had no patience left for configuring more business software. They
  expected the work to be conversation, with little or no custom interface.
* **Owners rarely look at their books.** They look when something forces them to, often at tax
  time. Whatever surface they use, they arrive cold and want to ask something.
* **Some steps cannot happen in an agent.** A password, an MFA code or a bank's credential never
  passes through a model (`IAM-10`). Plan and payment happen at a payment processor. Granting
  someone authority over the books is a decision made by the person as themselves, not by an agent
  acting for them.
* **A model must not carry the books in bulk** (`IMP-09`). A 5,556-transaction export is about
  74,000 tokens re-emitted (ADR-0041 § 6).
* **MCP App panels render CFOKit's own components inside an agent's conversation.** They read a
  file locally and call tools the model cannot see (ADR-0058, More Information). The same standard
  is what CFOKit's own runtime hosts (ADR-0034 § 4).

## Decision Drivers

* **Meet the person where their context already is**, so they do not explain their business
  twice.
* **As little configuration as possible** for someone who runs a business rather than keeps books
  (`NFR-19`).
* **No credential and no bulk figures through a model** (`IAM-10`, `IMP-09`).
* **Build each capability once** for every host, rather than a page and a conversation version.
* **A rule that settles the next trade-off** without reopening this one.

## Considered Options

* Optimize for the person's own agent; the browser holds what an agent cannot do
* Optimize for the browser, with CFOKit's own chat as the main experience
* No primary surface; decide for each capability
* Everything in the agent, including sign-in and payment

## Decision Outcome

Chosen option: "Optimize for the person's own agent", because that is where the context about the
business already is, and the standard it uses for skills, tools and panels is the one CFOKit's own
runtime hosts too. A capability built for it serves both offerings.

> After getting started, when a capability cannot serve the person's own agent and the browser
> equally well, it is built for the agent. The browser holds what an agent cannot do: sign-in, plan
> and payment, entering a credential for another service, and granting authority.

### 1. In what order a capability is built

1. **Conversation first**, through the skill and the published tools.
2. **A panel where conversation is wrong**: where a model must not carry the data, where a file is
   read, or where the person needs to see something laid out to decide. Panels are built to the MCP
   Apps standard, so the same panel renders in the person's agent and in CFOKit's runtime.
3. **A web page only for what the browser holds**, or as a second shell around a panel's components
   for a host that cannot render panels.

### 2. What the browser holds

* Plan, subscription and payment.
* Registration, sign-in, MFA and passkeys, on the issuer's pages (`IAM-10`).
* Entering a credential for another service, such as connecting a bank feed.
* Granting authority over a company: roles, and which agents may act.
* Connecting an agent: the Settings page.

Each of these hands back to the agent when it is done, with a link or a drafted prompt, rather than
continuing on the web.

### 3. The web client's home is CFOKit's chat

Where the deployment runs CFOKit's agent (ADR-0075), a company's home in the web client is its chat
with that agent, and a signed-in person with a company lands there. The chat is not a page in § 1's
sense: it hosts the same skill and the same published tools as the person's own agent, so a
capability built conversation first serves it unchanged, and the order in § 1 stands. The pages in
§ 2 hand back to the chat, or to the person's own agent, when they are done.

Getting started still ends offering Claude first (ADR-0058 § 1), with the chat beside it and the same
first question drafted in it. A deployment that runs no agent has no chat, and its web client keeps
the pages it had.

### Consequences

* Good, because setup and migration draw on what the person's agent already knows about the
  business, instead of asking for it again.
* Good, because a panel is built once and serves the person's own agent and CFOKit's runtime.
* Good, because the next trade-off has an answer.
* Bad, because CFOKit's experience depends on hosts it does not control. A host that renders no
  panels gets the page shell instead, and one that changes its panel support can break a flow
  CFOKit tested.
* Bad, because a person moves between the browser and the agent for the steps the browser holds.
  Nothing returns a browser tab to a specific chat (ADR-0058), so each hand-off back is a new
  chat or a copied prompt.
* Bad, because a person who chose the browser at the end of getting started (ADR-0058) gets less
  than one who connected an agent where the deployment runs no agent of its own. Where it runs one,
  the chat brings them what is built for the agent (§ 3).
* Neutral, because pages do not go away. They narrow to what the browser holds.

### Confirmation

Review. A design that puts a capability on a web page outside § 2 cites this record and says why
the agent cannot do it. No check enforces it.

## Pros and Cons of the Options

### Optimize for the person's own agent; the browser holds what an agent cannot do

* Good, because it meets every driver.
* Bad, because the product's experience is partly in hosts CFOKit does not control.

### Optimize for the browser, with CFOKit's own chat as the main experience

The strongest alternative. CFOKit would control the whole experience, choose the model for each
task, capture what the model saw for `SOC1-06` (ADR-0034), and test one surface end to end. It
also fits the eventual need for CFOKit's own chat in managed bookkeeping.

* Good, because every screen and every model call is CFOKit's to design, test and evidence.
* Good, because a person who has no agent of their own gets the best experience.
* Bad, because the person's context about their business is in their own agent, and CFOKit's chat
  would have to ask for it again. That is the configuration the founder interviewed said they will not do.
* Bad, because `PLT-01` and `PLT-02` make the person's own agent a supported surface regardless,
  so optimizing for the browser makes the hosted backend's main surface the compromised one.
* Bad, because the hosted backend would carry CFOKit's inference cost for the main experience,
  where the vision's cost structure has the person's runtime supply it.

### No primary surface; decide for each capability

* Good, because each capability gets the surface that suits it best.
* Bad, because the trade-off is reopened for every capability, and the answers will not agree with
  each other.

### Everything in the agent, including sign-in and payment

* Good, because the person would never leave the conversation.
* Bad, because a credential would pass through or near a model, which `IAM-10` forbids, and a
  payment processor's and an issuer's pages are browser pages by design.

## More Information

**Follow-on obligations.**

* The agent door of ADR-0058 follows this order: the conversation, then a panel for the import.
* The vision's "Not a dashboard" position and the out-of-scope row on the web client state where the
  work after getting started happens, and follow this record.

**Reversal cost.** Moderate. Panels are the web client's components in another shell, so moving a
capability to a page is a new shell around the same screens. The skill's conversational flows
would carry over to CFOKit's own chat unchanged, since it hosts the same skills.

**Evidence.** One interview, with a founder who uses AI heavily. They argued that anyone who started
a business recently leans on AI whatever the business, which is their opinion, not data.

Related: ADR-0034 (the runtime that hosts the same surface), ADR-0058 (getting started, which this
record does not govern),
ADR-0049 (the web client).

## Revisit when

* Interviews with owners who do not use an agent show they are the majority of those buying, so
  the person's own agent is not where the context is.
* A host that most customers use stops supporting MCP App panels, or never adds them.
* CFOKit's own chat becomes the main surface for most paying customers, through managed
  bookkeeping.
