---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-01
decision-makers: [Geoff]
---

# ADR-0056: A notification is open until its question is answered or its recipient dismisses it, and open notifications are read through the published interface

**Requirements served:** `PLT-07`, `NFR-04`, `NFR-16`, `IAM-11`, `SOC2-15`.

## Context and Problem Statement

[ADR-0052](0052-notifications-are-records-delivered-after-commit.md) makes a notification a record:
written in the same commit as the act that raises it, addressed to one person who holds a role in
one entity, carrying a class, an opaque reference to its subject, and the link that answers it. It
says every deployment shows a person their notifications in the web client and through the agent.
It does not say which notifications are shown, what a person can do with one, or when one stops
being shown.

Those are the questions this record answers, and they are forced by `PLT-07`: CFOKit reaches
people "when something needs them". A list that shows everything ever raised stops saying what
needs them within a week. So a notification has to stop needing them at some point, and that point
has to be a fact CFOKit can establish, not a guess.

What a notification asks varies by class. "A transaction no rule resolves" is answered by an act in
the books: the transaction is categorized. "A scheduled run did not complete" is answered by a
later run that does. "Cash moved beyond your threshold" has no act that answers it; the person only
needs to have seen it.

Four constraints bear on the answer:

* Rows are append-only (ADR-0052 § 1). Nothing about a notification changes by update; what happens
  to it is recorded as rows of its own.
* An agent acts for a person with the intersection of their authority (`IAM-11`), and keeps the
  books in the same conversation the notification would be read in. A question the agent raised is
  one the agent could make disappear.
* `NFR-16` forbids parking something so that it looks resolved when it is not.
* Entity isolation is enforced at the data layer, with no query path around it (`SOC2-15`), while a
  person who holds roles in several entities wants one list.

The web client cannot be told that a notification arrived: websockets and server-sent events stay
behind ADR-0012's gate, because an open connection keeps a scale-to-zero instance running and
billed for as long as it is open (ADR-0017).

## Decision Drivers

* The list shows what needs the person now, and nothing else (`PLT-07`).
* Whether a notification is open is derived from records, never from an agent's say-so (`NFR-16`).
* A person's notifications are theirs: nobody else's are shown to them, and no entity's leak into
  another's scope (`NFR-04`, `SOC2-15`).
* The agent reads the same notifications the web client shows, through the published interface.
* Append-only, like every other record.
* No new runtime shape: no held connection, no polling process on the server.
* Nothing built for a need no requirement states.

## Considered Options

* Open until the answering act closes it or the recipient dismisses it; open notifications read
  through the published interface
* Read and unread, marked as the person views them
* Open until dismissed, with no closing by the answering act
* Closed by the agent once it believes the question is answered
* A notifications module owning the records and the interface
* The whole history, paged, as the read

## Decision Outcome

Chosen option: "Open until the answering act closes it or the recipient dismisses it; open
notifications read through the published interface", because it is the only option in which what
the list shows is established by records rather than by whoever last touched it.

> A notification is open until a closing row exists for it. Two things write one: the act that
> answers its question, in that act's own transaction, which closes every recipient's notification
> about that subject; and the recipient, dismissing their own, as themselves and never through an
> agent. A person reads their open notifications through REST and MCP, across every entity they
> hold a role in, each read under that entity's scope.

### 1. The answering act closes the question

When a module commits an act that answers a question — the transaction is categorized, the run
completes — it writes, in the same transaction, a closing row for the open notifications of that
class about that subject. The ledger stores the row with the same generic columns as the
notification: an entity, a class, an opaque subject reference. It learns no domain meaning, as it
learns none from `audit_log`.

The closing is per subject, not per recipient. When two owners were each asked about one
transaction and one of them answers it, both notifications close, because the question no longer
needs either of them. The closing row names the act that closed it, so "answered by this posting"
is recorded rather than inferred.

A class declares whether an act answers it. A class with no answering act — a cash threshold
crossed — is closed only by dismissal.

### 2. The recipient dismisses their own, as themselves

A person may dismiss a notification addressed to them, which writes a dismissal row against it and
closes it for them alone. It is a state-changing call: it carries an idempotency key (ADR-0029) and
writes one `audit_log` row.

Dismissal is refused to a principal acting for another. A request whose token carries an `act`
claim is refused, the second condition of [ADR-0042](0042-person-only-acts-are-a-capability.md)
§ 2, so an agent cannot dismiss a question it raised and leave it looking resolved (`NFR-16`). It
needs no capability beyond being the recipient: what is dismissed is the person's own, and only the
person's. Dismissal is therefore a REST operation the web client calls, with no MCP tool.

A dismissed notification whose subject is later answered gains a closing row as well; nothing
re-opens.

### 3. There is no read or unread

What the list counts is what is open. A notification the person has looked at and not answered
still needs them, so it stays; one that was answered while they were away is gone without being
viewed. No row records that a person viewed a notification.

### 4. The read

* **REST, `GET /notifications`** — the caller's open notifications across every entity in which
  they hold a role. It is answered by reading each such entity under its own scope and combining
  the results; no query reads across the entity boundary (`SOC2-15`).
* **REST, `GET /entities/{entity_id}/notifications`** — the same, for one entity.
* **REST, `POST /entities/{entity_id}/notifications/{notification_id}/dismissal`** — § 2.
* **MCP, `open_notifications`** — the read, with an optional entity, for the agent acting for a
  person. It returns that person's notifications, under the intersection of the agent's grants and
  theirs (`IAM-11`).

Each notification is returned with its identifier, entity, class, subject reference, link and the
time it was raised: what ADR-0052 § 6 lets it carry, and no figures. Only open notifications are
returned. Closed ones, with their closing and dismissal rows, stay in the entity's records and its
complete export (ADR-0052 § 7).

A caller sees only notifications addressed to them. A co-owner's are not listed, even within an
entity both hold.

These are additions to the published interfaces and go through gate 5 like any other (ADR-0015).

### 5. The web client asks again; it is not told

The web client reads the open list when it loads, again when its tab regains focus, and at an
interval while the tab is visible, and stops while the tab is hidden. A person who is not looking
is reached by a channel (ADR-0052), not by the open tab. Live updates to an open tab remain behind
ADR-0012's gate.

### 6. A closed notification is not delivered

ADR-0052 § 3 retries an undelivered notification at the entity's next hand-off. A notification
closed before that hand-off is not delivered: it no longer asks anything, and a message for a
question already answered is noise. Its undelivered state stays recorded.

### Consequences

* Good, because the list is exactly what needs the person, derived from records.
* Good, because an agent can read what it was asked and answer it by doing the work, and cannot make
  a question disappear any other way.
* Good, because a question raised to several people closes for all of them when one answers.
* Good, because the read needs no new runtime shape and costs nothing while nobody is looking.
* Bad, because every module that raises a class with an answering act must also write its closing
  row, and a module that forgets leaves questions open after they are answered. That failure is
  visible — the person sees a question they already answered — rather than silent.
* Bad, because a notification arrives in an open tab only at its next read, up to one interval late.
* Bad, because there is no "unread" badge; the count is of open questions, which is the number that
  matters and not the one most products show.
* Neutral, because a person who wants an answered question back has it in the entity's records and
  export, not in the list.

### Confirmation

* A test asserts that an act answering a notification's subject writes its closing row in the same
  transaction, that a rolled-back act closes nothing, and that every recipient's notification about
  that subject closes.
* A test asserts that each notification class with an answering act is closed by it — one test per
  class, added with the class.
* A test asserts that a dismissal with an `act` claim is refused, that a dismissal of another
  person's notification is refused, and that a valid one closes it for its recipient alone and
  writes one audit row.
* A test asserts that `GET /notifications` returns a person's open notifications from each entity
  they hold a role in, none from an entity they do not, and none addressed to someone else.
* A test asserts that a notification closed before its retry is not delivered.
* Gate 5 holds the new routes and the tool as published contract.
* Not gated: that a module adding a class with an answering act writes the closing row. That is
  the per-class test above, which review requires.

## Pros and Cons of the Options

### Open until the answering act closes it or the recipient dismisses it

* Good, because it meets every driver.
* Bad, because closing is a duty on every module that raises an answerable class.

### Read and unread, marked as the person views them

What most products do, and what a person expects from a badge.

* Good, because it is familiar, and tells a person what is new to them.
* Bad, because viewing is not answering. A question looked at and left still needs the person, and
  marking it read hides it in exactly the way `PLT-07` is meant to prevent.
* Bad, because it writes a row for every view, and "viewed" is a fact about a screen, not about the
  books.

### Open until dismissed, with no closing by the answering act

The smallest design: one closing mechanism, owned by the person.

* Good, because no module needs to know about notifications beyond raising them.
* Bad, because a person who categorizes a transaction in the conversation still finds the question
  waiting in the web client, and has to clear by hand what they already did. The list fills with
  answered questions, and stops meaning anything.

### Closed by the agent once it believes the question is answered

* Good, because the agent is usually the one who knows.
* Bad, because the agent raised the question, and a question that can be closed by the party that
  asked it is the parking `NFR-16` forbids. An act in the books closes it; a belief does not.

### A notifications module owning the records and the interface

Cleaner on its face: notifications are a capability, and `CLAUDE.md` names packages for
capabilities.

* Good, because the ledger would hold one fewer kind of record.
* Bad, because every module raises and closes notifications inside its own transaction, so every
  module would depend on the notifications module, and modules never depend on each other
  (ADR-0022). The ledger is the one thing they all depend on, which is why ADR-0052 put the records
  beside `audit_log`, with generic columns. The channels are already a package of their own.

### The whole history, paged, as the read

* Good, because a person could look back at what they were asked.
* Bad, because no requirement asks for it, and the history is already in the entity's records and
  export. It is an addition when a screen needs it.

## More Information

**Follow-on obligations.**

* Each notification class states, where it is defined, whether an act answers it and which.
* `GET /notifications` is the first read across a person's entities; its implementation reads each
  under that entity's scope, and the pattern is reused, not reinvented, by the next such read.

**Reversal cost.** Moderate. The closing and dismissal rows are records and stay; changing what
closes a notification later is a change to which rows are written, not to rows already written.
The routes and the tool are published, so removing one is a breaking change (ADR-0015).

Related: ADR-0052 (notifications as records), ADR-0042 (acting as oneself), ADR-0012 (the gate on
live connections), ADR-0049 (the web client), ADR-0022 (modules never depend on each other).

## Revisit when

* A screen needs live updates — watching the agent work, several people in one entity at once —
  which is the trigger for a record passing ADR-0012's gate for server-sent events.
* A requirement asks a person to see what they were asked in the past, which adds the history read.
* A notification class turns out to need closing by something other than an act or a dismissal,
  such as expiry after a period.
