# Customer journey

From first click to books worth talking about, and on into the work CFOKit exists for. One
journey for both offerings; where they differ, the row says so.

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

Everything after getting started runs where the agent does: Claude Desktop with the hosted backend,
CFOKit's runtime with managed bookkeeping. The same skills, tools and panels serve both; what
differs is who answers. With the hosted backend, the person does. With managed bookkeeping,
CFOKit's agent does, and only what is the company's own call reaches the person.

**The rhythm is CFOKit coming to the person, not the person coming to CFOKit.** Work arrives on a
schedule and is settled by rules; what no rule settles becomes a notification (`PLT-07`), and the
notification opens the conversation with the question already asked — the same hand-off as the
first question.

| Area | The person | CFOKit | Where |
|---|---|---|---|
| **Keeping current** | Answers what no rule resolves, once per pattern: picks the account, approves the rule (`BKP-09`, `BKP-12`) | Takes in account activity as it arrives (below); assigns it by stored rules (`BKP-06`); matches transfers and payments already expected (`BKP-13`, `BKP-14`); asks about the rest | Notification → a panel of unresolved transactions in the chat |
| **Closing a month** | Supplies any statement CFOKit could not get; reviews and closes the period (`LED-11`); reopens one if needed, which only a person can do (`SOC1-17`) | Reconciles every bank and card account against the bank's own statement (`BKP-15`), explaining any difference; says when the month is ready — every account reconciled, nothing unresolved — and what stands in the way when it is not (`PLT-14`) | Notification → a close panel; differences explained in the chat |
| **Closing a year** | Confirms the year | Closes income and expense to retained earnings (`LED-12`); assembles what a tax preparer needs (`RPT-18`) | Panel; the package as a document and a link |
| **Questions** | Asks anything about the books | Answers the standard statements from defined tools, never composed (`RPT-09`); traces any figure to its postings and the rule that assigned them (`RPT-08`); answers the unanticipated from what is posted (`RPT-16`) | Chat; a statement shown in a panel |
| **Cash** | Sets the threshold that matters | Reports position and runway, and raises a change past the threshold unasked (`RPT-15`) | Notification → chat |
| **Receivables** | Drafts and issues invoices (`AR-02`, `AR-04`); decides a write-off (`AR-18`) | Numbers them without gaps (`AR-05`); delivers them, by email where the deployment has it and always as a link (`AR-07`, `AR-09`); sends reminders until paid (`AR-17`); applies deposits to the invoices they settle (`AR-13`); reports what is outstanding by age and customer (`AR-15`) | Invoice panel; aging in the chat |
| **Reports for others** | Asks for the statement a lender, board or accountant needs; marks it issued (`RPT-17`) | Produces it with its basis on its face (`RPT-10`), as a document and a link (`RPT-13`), reproducible as it stood (`RPT-11`) | Chat → report panel with the link |
| **Leaving** | Takes the books, at any time, without asking anyone (`EXP-03`) | Exports them for another system, or complete for another CFOKit (`EXP-01`, `EXP-02`) | Panel; the archive as a download |

**Where account activity comes from.** One destination, by whichever route reaches the account:

* **A feed** — bank, card and processor activity synchronized on a schedule with no one triggering
  it (`BKP-01`, `BKP-02`, `BKP-16`). With managed bookkeeping and the hosted backend this is
  Plaid; a self-hosted deployment can bring its own.
* **The bank's statement** — what reconciliation is against, because a feed's balance comes from
  the same source as its transactions and proves nothing about them. Fetched with the feed where
  the provider offers it (Plaid does, for checking and savings), otherwise supplied by the person
  at close.
* **An uploaded file** — any account nothing else reaches (`BKP-03`). Every deployment has this,
  and it needs no third party.

A Cowork skill that signs nothing in itself but downloads statements from the person's own
bank session, in their browser, is a convenience offered where it proves feasible — not a route
the close depends on.

## Open questions

* **More than one company.** A fractional CFO, or a founder who also keeps a nonprofit's books,
  holds several entities under one account. Adding a second company is a getting-started flow that
  happens after the agent is already in use, which argues for company creation and import as a
  panel rather than web pages — and the books of each must stay apart in the person's agent.

* **A notification for a person using their own agent.** CFOKit can push to the installed web
  app, but the answer belongs in Claude. Opening the notification should start a chat with its
  question drafted, as the first question does — through the web app, or straight to Claude.
