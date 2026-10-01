---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-30
decision-makers: [Geoff]
---

# ADR-0053: An issued invoice is a page, and what is delivered depends on the deployment's public address

**Requirements served:** `AR-07`, `AR-08`, `AR-09`, `AR-14`, `AR-17`, `AR-19`, `IAM-20`, `NFR-06`,
`SOC2-15`.

## Context and Problem Statement

An issued invoice has to reach the entity's customer. `AR-07` makes it a shareable artifact an
operator can deliver by any means. `AR-08` makes its link work without sign-in, because requiring a
customer to hold an identity before they can see a bill is an obstacle to being paid. `AR-09` has
CFOKit deliver it where a delivery channel is integrated, and `AR-19` has CFOKit record what it
actually knows about the invoice reaching its customer. `AR-17` has reminders distinguish an invoice
never opened from one opened and unpaid.

Deployments differ in two ways that decide what is possible. Some have a mail relay and some do not
([ADR-0052](0052-notifications-are-records-delivered-after-commit.md)). And some have a public
address — a `PUBLIC_BASE_URL` the entity's customers can reach — while a deployment on one machine
does not: a link to it reaches no one but its operator.

## Decision Drivers

* A customer can see what they owe without an account (`AR-08`).
* What a customer sees online and what they receive as a document never differ.
* A deployment on one machine can still invoice.
* An invoice's figures never pass through a relay; only a link does.
* CFOKit records what it knows about an invoice reaching its customer, whichever way it went.

## Considered Options

* The invoice is a page; its PDF is the page rendered; delivery depends on the public address
* The invoice is a PDF, attached to an email
* The invoice is always a link, on every deployment
* The invoice page requires the customer to sign in

## Decision Outcome

Chosen option: "The invoice is a page; its PDF is the page rendered; delivery depends on the public
address", because it gives every customer the same invoice by link or document, keeps figures out of
the relay, and still works on a deployment no customer can reach.

> An issued invoice is a page at its stable link, needing no sign-in. Its PDF is that page rendered.
> With a public address and a relay, CFOKit emails the customer the link. Otherwise the operator
> delivers the link or, with no public address, the PDF. Every view of the page is recorded.

### 1. The page is the invoice, and the PDF is the page rendered

The invoice page, reached by its stable link, shows the invoice and anything that has since
corrected it — a credit note or a reversal stays visible to the customer (`AR-14`). The PDF is that
page rendered for download, from the same source, so the document a customer holds and the page
they open never differ.

### 2. What is delivered depends on the public address

| Deployment | The customer receives | Who delivers it |
|---|---|---|
| A public address and a relay | The link, by email from CFOKit (`AR-09`) | CFOKit |
| A public address and no relay | The link or the PDF | The operator, by any means |
| No public address | The PDF | The operator, by any means |

"By any means" includes by hand and through the operator's own agent, drafting the email from their
own mailbox (`AR-07`). CFOKit sends no invoice email where it has no public address, even with a
relay configured: the link would reach no one, and the invoice itself never goes through a relay.

### 3. Who may be sent an invoice

An invoice email is not a notification. It is a message whose subject is the invoice, sent through
ADR-0052's channels by the module that owns invoices, and recorded with its relay events as
ADR-0052 § 4 sets out. The customer holds no role in the entity, so it is authorized by the invoice:
it is sent only to the contact on the customer the invoice was issued to, by a person or rule
allowed to issue it.

### 4. The link is how the page is reached

The page and its PDF are reached by the invoice's link, not by a token from the issuer, so neither
audience validation nor entity grants apply to them. The link is a read path of the kind `IAM-20`
defines, and so one of the exceptions `SOC2-15` allows to entity isolation: it carries a random
token that cannot be guessed, reaches one invoice, reads it and nothing else, and stops working when
revoked.
Because the token exists only in this deployment's records, a link that resolves is one meant for
this deployment (`NFR-06`). A view acts for no person: it writes one audit row naming the link, by
its identifier and never its token, as the actor. These routes are not part of the published REST
interface (ADR-0015): what a customer holds is a link, and it keeps working because the invoice's
link is stable (`AR-08`).

### 5. What CFOKit records

CFOKit records what it knows (`AR-19`): that it sent the link, and every event the relay reports on
that email, where it sent it; that the PDF was downloaded or the link copied, where the operator
delivered it; and every view of the page, by whatever route its link travelled — forwarded to a
customer's accounts team, pasted into a chat, or clicked from CFOKit's email. A view of the page is
what tells an invoice opened from one never opened (`AR-17`).

Where CFOKit emails the link, the relay tracks opens and clicks as ADR-0052 sets out. Click tracking
routes the invoice's link through SendGrid, and that link opens the invoice without sign-in. That is
accepted: SendGrid is already trusted with the recipient's name and address, the link reaches one
invoice and nothing else, and it can be revoked.

### Consequences

* Good, because a customer always sees the current invoice, corrections included, without an
  account.
* Good, because a deployment on one machine invoices by PDF with nothing public.
* Good, because figures never pass through a relay.
* Good, because page views record an invoice being opened however its link travelled.
* Bad, because a customer of a deployment with no public address receives a document rather than a
  link, and sees no later correction unless it is sent to them too.
* Bad, because rendering the page as a PDF is a capability CFOKit has to provide.
* Bad, because the invoice's link passes through SendGrid where CFOKit emails it with click
  tracking.

### Confirmation

* A test asserts that a deployment without a public address sends no invoice email, whatever relay
  is configured.
* A test asserts that an invoice email is refused to any address other than the contact on the
  invoice's customer.
* A test asserts that a view of an invoice's page is recorded against the invoice, and that the PDF
  and the page render the same figures.
* A test asserts that an unknown or revoked link serves nothing, that a link serves only its own
  invoice, and that a view writes one audit row carrying the link's identifier and not its token.

## Pros and Cons of the Options

### The invoice is a page; its PDF is the page rendered; delivery depends on the public address

* Good, because it meets every driver.
* Bad, because it asks CFOKit to render a page as a document.

### The invoice is a PDF, attached to an email

The most common practice among small businesses.

* Good, because a customer has the document in their mailbox, with nothing to click.
* Bad, because every invoice's figures pass through the relay and sit in its logs.
* Bad, because a later credit note or reversal never reaches the copy the customer already holds.
* Bad, because nothing records the invoice being opened.

### The invoice is always a link, on every deployment

* Good, because there is one path.
* Bad, because on a deployment with no public address the link reaches no one.

### The invoice page requires the customer to sign in

* Good, because nothing is readable without an identity.
* Bad, because `AR-08` rules it out: an account is an obstacle to being paid.

## More Information

**Reversal cost.** Low. The page, the PDF and the delivery rules are presentation and routing over
an invoice that is already a posting (`AR-03`).

**Follow-on obligation.** `CLAUDE.md` names a link of `IAM-20`'s kind, such as the invoice's, as
one of the two ways an entity's data is reached without a token from the issuer (ADR-0052).

Related: ADR-0049 (the web client that serves the page), ADR-0052 (the channels and relay).

## Revisit when

* Customers ask for the invoice attached to the email, which is the case for sending the PDF as well
  as the link.
* A deployment on one machine gains a public address, by a tunnel or a hosted front, which moves it
  to the link path without any change here.
