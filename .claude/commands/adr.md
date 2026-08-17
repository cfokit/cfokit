---
description: Draft a new Architecture Decision Record from the template at the next free number
argument-hint: [short imperative title of the decision]
allowed-tools: Read, Write, Bash(ls:*), Glob, Grep
---

Draft a new ADR for: **$ARGUMENTS**

## Steps

1. **Find the next free number.** List `docs/adr/` and take the highest existing number plus
   one. Numbers are sequential and never reused; gaps are fine. Note that some numbers are
   listed in the backlog table of `docs/adr/README.md` without having files yet — if
   `$ARGUMENTS` matches a backlog entry, **use that reserved number** rather than a new one.

2. **Read `docs/adr/0000-template.md`** and follow its structure exactly. Read two accepted
   ADRs — `0002-postgres-as-sole-storage-backend.md` and
   `0019-identity-provider-conformance-contract.md` — to match the house voice before writing.

3. **Check whether this decision is already made.** Search the existing ADRs and `CLAUDE.md`.
   If it supersedes an earlier ADR, set `Supersedes:` and note which. Never edit the old ADR's
   reasoning — set its status to `Superseded by ADR-NNNN` and leave it in place.

4. **Write to `docs/adr/NNNN-kebab-case-title.md`** with status `Proposed`, today's date, and
   `Deciders: Geoff`.

5. **Update the index** in `docs/adr/README.md`, and remove the entry from the backlog table
   if it was there.

## What makes this ADR worth writing

- **Alternatives rejected is the most important section, and it is mandatory.** Each
  alternative gets its own subsection: why it was attractive, then the specific reason it was
  rejected. Cite numbers, limits, licences, and version facts. "Didn't feel right" is not a
  rejection reason. An ADR without this section does not prevent re-litigation, which is the
  main thing an ADR is for.
- **Context states what forced the decision** — constraints, workload facts, scale,
  regulatory, team size — with enough detail that someone with no memory of the discussion can
  judge whether the reasoning still holds. Do not put the answer here.
- **Decision is imperative and one or two sentences.**
- **Consequences covers accepted costs, follow-on obligations, and reversal cost.** Be honest
  about reversal cost; that is what tells a future reader whether to revisit or live with it.
  Follow-on obligations often become `CLAUDE.md` rules — say so where they do.
- **Revisit when needs concrete triggers**, not "periodically". A threshold crossed, a
  dependency reaching GA, a limit hit in production. If nothing would trigger a revisit, say
  that explicitly.

## Rules

- One decision per file. If the title needs "and", split it.
- Verify facts rather than recalling them — especially licences and version numbers, since two
  existing ADRs exist precisely because a dependency relicensed. Say so if you could not verify
  something.
- Do not mark it `Accepted` yourself. Leave it `Proposed` and tell the user what to review.

Finish by running `uv run task test` — a documentation test checks that no rule cites an ADR
missing from both the accepted set and the backlog.
