# CFOKit — Accounting Policy

- **Status:** Draft
- **Date:** 2026-08-20
- **Owner:** Geoff

**Audience: you, your accountant, and your auditor.** This document states what CFOKit does to
your numbers and why you can rely on it. It is written to be handed to a professional who has
never seen the codebase.

Every policy cites the decision record holding its reasoning. If you disagree with a policy,
read the ADR first — it will contain the alternative you are about to propose, and the specific
reason it was not chosen.

> **Draft.** Policies marked *Pending* are decided but not yet written up, or not yet decided.
> Do not rely on a Pending policy; it may change. Nothing here is implemented yet — CFOKit is
> pre-implementation, and this document exists so the policies are settled before code assumes
> them.

## Summary for the impatient

| Policy | CFOKit | QuickBooks / Xero |
|---|---|---|
| Editing a posted transaction | Never. Corrections are reversing entries | Permitted |
| Ledger retention | Indefinite by default; documents 7 years | Audit log retained for a limited period, then gone |
| Accounting basis | A property of the entity, like fiscal year | Chosen per report run |
| Categorisation | Deterministic stored rules; you approve rules, not transactions | Rules applied inconsistently |
| Period close | Advisory, and not what guarantees your audit trail | Optional; off by default in QBO |
| Reproducing a past statement | Exact, from the ledger itself | Not supported |
| Deleting a transaction | Never | Permitted |

The short version: CFOKit is stricter than the SMB tools and roughly as strict as an
enterprise ledger. That is deliberate, and the reason is in [ADR-0006](../adr/0006-append-only-from-posting-reversing-corrections.md).

---

## 1. Basis of accounting

**Double-entry.** Every transaction balances to zero per commodity, and CFOKit refuses to
record one that does not. This is enforced by the database, not only by application code, so it
cannot be bypassed by a bug in a code path. (REQ-A1, ADR-0005)

**Exact decimal arithmetic.** Monetary values are never stored or computed as binary floating
point, anywhere — including in test fixtures. All monetary columns carry ten decimal places.
Your cents do not drift. (REQ-A3, ADR-0004)

**The accounting basis is a property of the entity, not of a report.**

Each entity declares its accounting basis once, alongside its fiscal year end — both are
company-level settings, and both are consequential rather than cosmetic. Your declared basis is
the one every statement uses by default, and it appears on the face of every statement so no
reader has to guess.

**Changing an entity's basis is a significant event, not a preference.** For tax purposes the
method is *elected*, and switching generally requires filing Form 3115 with the IRS. CFOKit
treats a basis change accordingly: it is recorded in the audit trail with an effective date, and
statements spanning the change say so.

**You can still see the other view.** Running a cash-basis P&L for an accrual-basis entity is
legitimate and often useful — accrual shows economic reality, cash shows liquidity and runway.
Such a report is produced on request and **labelled as an alternate basis**, so it can never be
mistaken for the entity's books.

> **Why this differs from QuickBooks.** QuickBooks asks you to pick cash or accrual each time you
> run a report, which makes it easy to hand someone a cash-basis statement for an accrual-basis
> business without either of you noticing. Making the basis a property of the entity means the
> default is always right and the exception is always visible.

**Accrual reporting is not built yet.** Cash basis is what CFOKit produces today. The ledger
records the obligation and the settlement as separate related events from the first schema
version, which is what accrual needs and what cannot be added later — but producing accrual
statements from those events is not implemented. An entity that must report on an accrual
basis is not yet supported. (REQ-A8)

**What this requires of the ledger, and why it cannot be retrofitted.** Cash and accrual are not
two ways of formatting the same data — they need different events. An invoice raised in March and
paid in May is March revenue on an accrual basis and May revenue on a cash basis, so the ledger
must record *both* the obligation and the settlement, and know they are related. A system that
records only the payment can never produce accrual statements. This is why the decision belongs
in the data model from the start (REQ-A8).

---

## 2. The life of a transaction

This is the policy that most distinguishes CFOKit, so it is worth understanding before you
start.

```
     ingested                 reviewed & confirmed         period reviewed
          |                            |                          |
       DRAFT  ──────────────────▶   POSTED   ──────────────────▶  CLOSED
   freely editable              immutable forever          advisory marker
                                corrections = reversals    (soft, not a lock)
```

### Draft

Most transactions arrive by **ingestion** from a bank, card, or payment-processor feed, with no
account assigned and nobody keying them in. Two other routes exist and are ordinary: an
adjusting entry recorded directly by you or your accountant (§ 5), and history imported from a
system you used previously (§ 12). All three arrive as drafts.

Assignment then happens through **categorisation and matching** — see § 3 — which is the
bookkeeper's actual work.

While a transaction is a draft it is **freely editable**. Assigning an account, adjusting an
amount, correcting a date, splitting it across accounts — all ordinary edits, leaving no
reversal behind. A draft may be temporarily unbalanced while it is still being worked on.

**Drafts do not appear in your financial statements.** They are not part of your books yet.

### Posted

Posting is the point of no return. Once posted, a transaction is **never modified and never
deleted**. Specifically, these can never change on a posted transaction:

- amount
- commodity or currency
- account
- transaction date
- entity

Notes, tags, and attachments can be *added* afterwards, but existing ones are never rewritten —
new annotations are appended, so nothing is overwritten. (ADR-0006)

### Closed

Closing a period marks it as reviewed. It is **advisory**: a workflow signal to you and your
colleagues that the period is finished, not the mechanism that protects your audit trail.
Append-only posting already does that, which is why close does not need to lock anything.

This differs deliberately from QuickBooks and Xero, where the lock *is* the protection and is
optional. In CFOKit you get the protection whether or not you ever close a period.

---

## 3. Categorisation and matching

How a draft transaction acquires its account. This is the bookkeeper's actual work, and CFOKit's
approach differs deliberately from what you may be used to.

**Rules are data. Applying them is deterministic.**

- A rule is a stored, inspectable record: *this pattern, under these conditions, posts to this
  account*. Conditions can include the payee, an amount range, description text, line-item
  detail where the feed supplies it, and which account the money moved through.
- Applying stored rules is ordinary deterministic code, tested like any other booking logic. The
  same transaction against the same rules produces the same assignment, every time.
- The agent's job is to **propose rules**, never to judge each transaction afresh.

**One payee is often not enough to decide.** An Amazon charge might be office supplies one week
and marketing materials the next. A rule forcing both into a single account would be
consistently wrong rather than usefully deterministic, so rules match on more than the merchant,
and anything the rule set cannot resolve is **asked rather than guessed**. CFOKit does not pick
the likeliest account and move on.

Determinism here is a claim about inputs. The same transaction against the same rule set
produces the same assignment. It is not a claim that every charge from one payee belongs in one
account, which is frequently untrue.

**Why this design.** If a language model judged each transaction independently, assignment would
be non-deterministic *by construction*: identical transactions could land in different accounts
in the same month for no recorded reason, and correcting one instance would teach the system
nothing. Storing the decision as a rule is what makes "it remembers" literally true rather than
approximately true.

**What you experience:**

1. New transactions are ingested, and you are told they arrived.
2. Anything matching an approved rule is assigned automatically and identically every time. You
   never remind it.
3. Anything unmatched is surfaced with a proposed rule, for your approval.
4. Every assignment records **which rule made it**, so "why is this in Office Supplies?" always
   has a specific answer.

**You approve rules, not transactions.** That is the difference between a bookkeeper who learns
and software that guesses. Approving a rule means the question is not asked again for that
pattern; approving a transaction one at a time is what makes bookkeeping feel endless.

**Changing a rule affects future assignments only.** It never silently re-categorises what is
already posted — that would be editing a financial field, which § 2 forbids. Re-categorising
something posted is a correction, with a visible reversing entry.

**The standard CFOKit holds itself to:** assignment should be at least as consistent as a
competent human bookkeeper, and consistency here means *deterministic*, not *usually right*.

---

## 4. Corrections

**Errors are corrected by recording more data, never by erasing history.** This is the
professional standard, and the reason is that an auditor must be able to see the original error
in order to establish that it was an error rather than an attempt to conceal something.

To correct a posted transaction, CFOKit records a **reversing entry** that cancels it, then the
correct transaction. All three remain in your books permanently.

**What this means in practice.** If you posted $4,500 where you meant $450, your books will
show the $4,500 entry, a −$4,500 reversal, and a $450 entry. Your balances are correct. Your
history shows exactly what happened and when. A tool that let you simply edit the 4,500 would
leave your balances equally correct and your history silently wrong.

**How to avoid it.** Fix things while they are still drafts. That is what the draft state is
for, and it is where CFOKit expects most correction to happen.

### When an agent makes the mistake

CFOKit's agents propose entries as **drafts by default**; confirming them posts them. When an
agent does post something wrong, the correction is a visible reversing entry like any other.

This is intentional. The property is narrow and worth stating precisely rather than overselling:
**a correction made by an agent is an entry in your books, not an event in a log you would have to
think to check.**

Note what this does *not* claim. QuickBooks and Xero record changes too — their audit logs cannot be
disabled, so an edit there is not invisible. The differences are that their log is retained for a
limited period, that you have to go looking, and — the part that actually changes with agents —
that reviewing a log written at human pace is feasible while reviewing one written at agent pace is
not. An audit trail sized for a bookkeeper making a few corrections a month is not sized for
software making hundreds of decisions.

It also does not protect you from a wrong entry. Immutability governs whether a posted entry can be
silently revised; it does nothing about whether it was right in the first place. That is what the
draft state and rule approval are for (§ 3).

---

## 5. Backdating

Recording a transaction dated earlier than today. It is routine and legitimate — a receipt surfaces
late, an accountant posts year-end adjusting entries in February dated 31 December, a feed delivers a
settlement date that differs from the posting date. CFOKit permits it. (ADR-0013)

**Every transaction carries two dates**, so backdating is always visible:

| Date | Meaning |
|---|---|
| **Transaction date** | When it economically occurred. What reports are periodised by. |
| **Recorded at** | When it entered your books. Assigned by the system; you cannot set it. |

Backdating is simply these diverging. There is no way to record one without it being evident, which
means the risk was never backdating — it was *undetectable* backdating.

**Into an open period:** permitted, unremarkable, no ceremony.

**Into a closed period:** permitted, but never silent. It requires explicit acknowledgement, is
recorded as a close-crossing in the audit trail, and flags any statement already issued for that
period as affected.

**Reversals follow the period.** Reversing an entry in an open period restates that period, which is
correct because nothing has been reported yet. Reversing one in a closed period books the correction
to the current open period by default, so figures you have already given someone stand. Restating the
closed period instead is available, and is itself a close-crossing.

**There is no date floor.** A cut-off would forbid legitimate late adjustments and would be worked
around. Visibility is the property worth having, not prohibition.

> **Note for when investments arrive.** With lot tracking (§ 6), a backdated *acquisition* changes
> which lots later disposals consumed, so prior gains recalculate. That does not apply today, because
> lots are deferred — which is why this policy is currently much simpler than it will need to be.


---

## 6. Cost basis and lot selection — *not yet implemented*

**This applies to you if you hold inventory or investments, and CFOKit does not implement it
yet.** An entity that needs lot selection is therefore not yet supported. A retail shop or a
restaurant needs it from its first stock purchase; a consultancy with a checking account never
does. The policy is documented here so it is settled before it is built rather than improvised
once it is needed.

**When it applies.** Lot selection arises only when you hold *fungible units in a pool, acquired at
different costs, and dispose of some of them*. Inventory is the familiar case, but it is not the
only one, and it is far from universal:

| Needs lot selection | Does not |
|---|---|
| Inventory (cost of goods sold) | **Interest income** — there is no basis, no disposal, no gain |
| Equities, bond funds, ETFs | Ordinary income and expenses |
| Crypto | Fixed assets — each is tracked individually, so nothing must be *selected* |
| Foreign currency balances you spend | Anything you do not hold and later dispose of |

**Interest on a checking account needs none of this.** It is income when earned. If that is the
only investment income you have, this section stays inert.

**The policy when it activates: FIFO, strictly.** Disposals consume the earliest lots first, exactly
rather than approximately. Where a disposal is ambiguous, CFOKit refuses to guess rather than
choosing something plausible. (ADR-0007 — *decided, write-up pending*)

**Why FIFO and nothing else.** Specific identification lets you nominate which units you sold and so
optimise the tax outcome — but it requires that you identified them *at the time of sale*, with
contemporaneous records. It cannot be elected retroactively. **CFOKit ingests transactions after
they have happened, so it cannot make an election it was not present for.** FIFO is also the method
assumed when none was specified. It is therefore not merely the simplest choice; it is the only one
CFOKit can compute honestly from a feed.

**Why the method matters to you.** It changes your tax, and not always in the obvious direction.
Buying 10 units at \$10 in 2024 and 10 at \$30 in 2025, then selling 10 at \$40: FIFO produces a
\$300 gain taxed at long-term rates, while last-in-first-out would produce a \$100 gain at
short-term rates. The smaller gain is not automatically the better outcome — the rate matters too.

**Instrument-dependent in practice.** A stable-NAV money market fund sells at \$1.00, so basis
equals proceeds and there is effectively no gain; income arrives as dividends. Treasury bill
discount is accreting *interest income*, not capital gain — a different mechanism entirely. Bond
funds, ETFs and equities are where real lot selection begins. Confirm treatment with your
accountant for your specific holdings.


---

## 7. Financial statements and reporting

**Reports are derived, never authored.** A statement is computed from your postings at the
moment you ask for it. There is no separate report data that can drift from your ledger.

**Any past statement can be reproduced exactly.** Because postings are append-only, CFOKit can
render your books as they stood at any earlier point. Two consequences worth knowing:

- "What did we tell the bank in March?" is answerable, precisely, at any time.
- If two versions of a statement differ, the difference is explainable — it is exactly the
  postings recorded between the two points.

**Issued statements — *Pending*.** The mechanism for marking a statement as final and issued,
and the form it takes when shared, is still being decided. See the open question in
[`vision.md`](vision.md).

**Reporting periods are arbitrary.** Trial balance as of any date, profit and loss for any
period, journal filtered by account, payee, or tag. Nothing is restricted to calendar months.
(REQ-A7)

---

## 8. Audit trail

**Every change is recorded.** Each state-changing operation writes exactly one audit row,
attributed to an actor and a request. Because nothing is ever overwritten, the trail is complete
by construction rather than by a logging feature that could be misconfigured. (REQ-E4, ADR-0011)

**Retention is your policy, not a limit of the software** — and it is layered by record class,
not a single number. Two different obligations are easy to conflate:

- **Append-only** governs whether a record can be *silently altered*. It cannot, ever.
- **Retention** governs how long each class of record is *kept before disposal*.

### The schedule

| Record class | CFOKit default | Why |
|---|---|---|
| **General ledger, postings, financial statements, chart of accounts** | **Indefinite** | Standard professional guidance places these in the permanent tier, and no mainstream ERP deletes them |
| Supporting documents — attachments, receipts, statements, raw ingested feed payloads | 7 years | The tier the "seven year rule" actually refers to |
| Fixed asset records | Life of asset + 7 years | Basis must survive as long as the asset does |
| Audit log | Follows the record it describes | An audit trail outliving nothing is pointless; one that dies first is worse |
| **Destruction log** | **Permanent** | It must survive the records it documents, or disposal is undocumented |

**The ledger is retained indefinitely by default.** This is not CFOKit being unusually strict — it
is what mid-market ERPs already do. NetSuite will not delete posted transactions in closed periods
at all, and its archiving tools explicitly keep data retrievable rather than destroying it. So an
append-only ledger is the *normal* posture for a system of record, not an eccentricity.

**"We keep financial records for seven years" is a statement about documents, not the ledger.**
Worth being precise about, because the two get conflated constantly.

### Disposal

Where disposal does apply, it follows the standard records-management procedure, and it is
deliberately not automatic:

1. Records reaching end of retention are **listed as candidates**, never destroyed silently.
2. **Legal hold is checked at disposal time and overrides the schedule entirely.** Nothing under
   hold is disposed of, regardless of age.
3. A **named approver** authorises each batch.
4. Disposal is executed, and a **permanent destruction record** captures what, when, by whom, and
   under what authority.

**Consistency is the protection.** Destruction in the ordinary course of a written, uniformly
applied schedule is defensible; selective or conveniently-timed destruction is not. An
inconsistently applied schedule is worse than no schedule, which is why disposal here is a
deliberate, logged, approved act rather than a background job.

**Why the default leans toward keeping.** The penalty for destroying too early is not symmetric
with the cost of keeping too long: SOX 802 / 18 U.S.C. § 1519 applies to private companies as well
as public ones, carries up to twenty years' imprisonment, and reaches *contemplated* investigations
— so exposure can exist before anyone knows an investigation does. Storage is cheap by comparison.

**Seven years is a default, not a legal answer.** Obligations vary by record type and
jurisdiction; the seven-year figure is a convenient envelope rather than a single statutory rule.
Set the schedule with your accountant and counsel.

**Contrast with QuickBooks.** Its audit log is retained for a limited period — commonly reported
as two years — with periodic CSV export as the documented mitigation. That is a *software* limit
you must work around. CFOKit's history is the ledger itself, so retention is a decision you make
rather than a ceiling you discover.

**What is never written to logs.** Token values, posting amounts, account numbers, and payee
names are never logged at informational level. Diagnostics reference identifiers and counts.

---

## 9. Multi-entity separation

**One deployment, many entities, no bleed.** No operation reads or writes across an entity
boundary without an explicit grant, enforced on the server regardless of what any access token
claims. This is what makes it safe for a fractional CFO to hold many clients' books in one
deployment. (REQ-A2, ADR-0011, ADR-0019)

---

## 10. Asking questions of your books

**You are not limited to a fixed menu of reports.** Your books are exposed over a documented
interface, so questions nobody anticipated can still be answered. Your accountant can ask what a
return needs. You can ask what you spent on contractors last quarter.

**Where an answer comes from, and where it does not.** Every figure is computed from your
postings at the moment you ask. Nothing is estimated, inferred from surrounding context, or
recalled from an earlier conversation. Where the books cannot support an answer, CFOKit says so
and says why instead of producing a plausible number.

**Entity scope is enforced by the server.** A question cannot reach books you hold no grant for,
however it is phrased (§ 9). Rephrasing is not a route around authorisation.

**Bounded guidance — *Pending*.** Where the CFO role falls to you rather than to a fractional
CFO or an employee, CFOKit will answer a limited set of questions about runway, margin, and
affordability. What it declines matters more than what
it answers, and that boundary is not yet settled. Anything turning on a tax election, entity
structure, financing, or jurisdiction is referred to a professional. (REQ-B8, REQ-B9)

---

## 11. Sales tax — *Pending*

**Tax you collect is a liability, never revenue.** Money taken from a customer on behalf of a
taxing authority is an obligation to that authority, and is reported as what is owed, to whom,
for which period.

Recording that liability is ordinary double entry. Everything else about sales tax is
jurisdictional — whether you have nexus, which rate applies to which product at which address,
and when each authority expects a filing — and how much of it CFOKit owns is undecided. Until it
is, treat sales tax as unsupported rather than partially supported. (REQ-A10)

---

## 12. Imported history — *Pending*

Books arriving from a system you used previously are books CFOKit did not produce, and that
distinction matters to anyone relying on them.

**Imported transactions are posted history**, governed by § 2 like anything else: no editing,
corrections by reversal. What is undecided is how much arrives. An opening trial balance carries
balances forward and nothing else. A full transaction import carries detail CFOKit cannot
independently verify, since it was not present when any of it happened. Those give your
accountant very different things to work with, and the choice is not yet made.

**Imported records are marked as imported, with their source, and a statement covering an
imported period says so on its face.** You should never have to remember which figures CFOKit
produced and which it inherited. (REQ-C5)

---

## 13. Independent assurance — *Pending*

**This document describes what the software does. On its own it is not evidence that the hosted
service operates the way it says.** The distinction matters if you are being asked to rely on
these books.

The source is public and the claims here are checkable in principle, which is worth something but
is not how a professional establishes reliance. For the hosted service that comes from an
independent third-party examination. Which report is not yet chosen: SOC 2 Type II is the widely
recognised one, and SOC 1, which addresses controls over financial reporting, may be more
relevant for a system whose output feeds a return.

**Until such a report exists, treat the hosted service as unattested** and read this document as
a statement of intent rather than of verified fact. A self-hosted deployment is operated by you,
and no attestation of ours would cover it in any case. (REQ-E8)

---

## 14. What CFOKit does not do

- **It does not file.** It produces the closed year, the schedules, and the supporting detail
  your preparer works from. A CPA prepares and files.
- **It does not move money.** It reads financial data and keeps books.
- **It does not give tax or legal advice.** It reports what the books say and flags what looks
  like it needs a professional.
- **It does not decide your accounting policy.** Whether something is capitalised or expensed,
  and how a nonstandard transaction is treated, is your decision.

---

## Open policy questions

Tracked here so nothing is assumed by omission.

| Question | Status | Blocks |
|---|---|---|
| Whether an issued statement can be superseded | Undecided | REQ-B3 reporting |
| Jurisdictions and entity types supported for tax work | Undecided | REQ-B4 |
| Compliance rule extension mechanism | Undecided | REQ-B5 |
| How much of sales tax CFOKit owns, and how much it delegates | Undecided | REQ-A10 |
| What fidelity an import promises — opening balance or full history | Undecided | REQ-C5 |
| What bounded guidance declines to answer | Undecided | REQ-B9 |
| Which assurance report the hosted service obtains | Undecided | REQ-E8 |
| Multi-currency revaluation treatment | Not yet raised | — |
| Whether ledger disposal is ever offered, and how GDPR erasure interacts with an append-only ledger | Undecided | REQ-E7 |
