# Customer journey

From first click to books worth talking about, and on into the work CFOKit exists for. One
journey for both offerings; where they differ, the row says so. **Draft.**

Getting started (stages 1–7) happens on web pages, before any agent is involved. Everything after
is built as skills, MCP tools and MCP App panels, so it runs wherever the agent does: Claude
Desktop for an organization bringing its own agent, CFOKit's runtime for managed bookkeeping. The
runtime is the web app; mobile apps follow, and a desktop app if warranted.

Getting the books in delivers nothing by itself. It is a chore, and the measure of it is how little
of the person it takes. Everything after it is the product.

## Getting started

| # | Stage | Commercial (hosted) | Self-hosted | Where |
|---|---|---|---|---|
| 1 | **Arrive** | A call to action on the marketing site | The README, once the stack is running | Web |
| 2 | **Lead** | Name, email, phone, kept in the lead system, not in CFOKit | — | Web |
| 3 | **Plan** | Managed bookkeeping, or the hosted backend with their own agent; subscribe through Stripe | — | Web |
| 4 | **Account** | The issuer's registration page, name, email and phone filled in: a password or Google/Microsoft, and MFA | The same page, empty | Issuer, in the browser |
| 5 | **Export** | Export from QuickBooks (shown how) and choose the file; it is read in the browser | Same | Web |
| 6 | **Company** | Confirm what the export states — name, basis, fiscal year end, currency — and fill in what it does not, such as the time zone | Same | Web |
| 7 | **Import** | See what will land, confirm; posted in batches and reconciled | Same | Web |
| 8 | **Connect** | Managed: nothing. Own agent: add CFOKit to Claude (a connector, or the plugin) | Own agent: the same, against their own stack | Web, guiding; Claude |
| 9 | **First insight** | Managed: in the runtime. Own agent: **Continue in Claude** opens a chat with the first question drafted, with a copy block beside it | Own agent: the same | Web → Claude |

**The first question** after an import is "did it all come across?", and the second "how's the
business doing?". The drafted prompt asks both:

> My books are imported into CFOKit. Confirm they match QuickBooks and explain any differences,
> then summarize this year's profit and loss and my cash position.

## After that — the product

Not yet mapped. Each needs the same treatment as the stages above: what the person does, what
CFOKit does for them, and where — the web app, the chat, or a panel in the chat.

* Keeping current: bank and card activity arriving, categorized by stored rules, exceptions asked about
* Statements: reconciling an account against what the bank says
* Closing a month, and a year
* Questions about the books, answered from the books
* Receivables: invoicing, what's outstanding, chasing it
* Reports for a lender, an accountant, a buyer — and the export that means leaving is easy

## Open questions

* **More than one company.** A fractional CFO, or a founder who also keeps a nonprofit's books,
  holds several entities under one account. Adding a second company is a getting-started flow that
  happens after the agent is already in use, which argues for company creation and import as a
  panel rather than web pages — and the books of each must stay apart in the person's agent.

* Prefilling name and phone on the issuer's registration page: OIDC's `login_hint` covers the
  email only.
* `claude://claude.ai/new?q=` opens Claude Desktop with a drafted prompt (documented); confirm it
  from a web page, with the "Open Claude?" prompt a browser shows the first time.
* Stages 5–7 on the web reverse ADR-0058, which put them in a panel in the chat. Panels remain for
  the work after.
