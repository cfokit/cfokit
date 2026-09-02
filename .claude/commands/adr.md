---
description: Draft a new decision record from the MADR template at the next free number
argument-hint: [short title naming the problem and the chosen solution]
allowed-tools: Read, Write, Bash(ls:*), Glob, Grep
---

Draft a new decision record for: **$ARGUMENTS**

## Steps

1. **Find the next free number.** List `docs/decisions/` and take the highest existing number plus
   one. Numbers are sequential with no gaps. Note that some numbers are
   listed in the deferred table of `docs/decisions/README.md` without having files yet — if
   `$ARGUMENTS` matches a deferred entry, **use that reserved number** rather than a new one.

2. **Read `docs/decisions/adr-template.md`** and follow its structure exactly. It is
   [MADR 4.0.0](https://adr.github.io/madr/) with two local rules. Read
   `0001-documentation-structure.md` to match the house voice before writing — it is the only
   record currently written to the standard.

3. **Check whether this decision is already made.** Search the existing records and `CLAUDE.md`.
   If it supersedes an earlier record, note which. Never edit the old record's reasoning — set
   its `status` to `superseded by ADR-NNNN` and leave it in place.

4. **Decide the `kind`.** Ask: would this decision change if the requirements changed?
   - Yes → `kind: "requirement-driven"`. It **must** cite at least one requirement id.
   - No → `kind: "substrate"`. A choice any project of this shape must make — language, package
     manager, tooling, formats. It cites no requirement, and inventing one to justify it is worse
     than citing none.

5. **Write to `docs/decisions/NNNN-kebab-case-title.md`** with YAML frontmatter: `status:
   "proposed"`, the `kind`, today's date, `decision-makers: [Geoff]`, and `consulted` / `informed`
   where they apply.

6. **Update the index** in `docs/decisions/README.md`, and remove the entry from the deferred table
   if it was there.

## What makes this record worth writing

- **`Considered Options` and `Pros and Cons of the Options` are mandatory here**, though MADR
  marks the second optional. Each option gets its own subsection: give the rejected ones their
  strongest case first, then the specific reason they lost. Cite numbers, limits, licences, and
  version facts. "Didn't feel right" is not a rejection reason. A record that names alternatives
  without refuting each one does not prevent re-litigation, which is the main thing it is for.
- **`Context and Problem Statement` states what forces the decision** — constraints, workload
  facts, scale, regulatory, team size — with enough detail that someone with no memory of the
  discussion can judge whether the reasoning still holds. Do not put the answer here.
- **`Decision Drivers` names the evaluation criteria before the options**, so they cannot be
  reverse-engineered from the answer.
- **`Decision Outcome` is imperative and one or two sentences**, followed by `Consequences` as
  Good / Bad / Neutral bullets and `Confirmation` saying how the decision is enforced. If nothing
  enforces it, say so plainly.
- **`More Information` carries follow-on obligations and reversal cost.** Be honest about reversal
  cost; that is what tells a future reader whether to revisit or live with it. Follow-on
  obligations often become `CLAUDE.md` rules — say so where they do.
- **`Revisit when` needs concrete triggers**, not "periodically". A threshold crossed, a
  dependency reaching GA, a limit hit in production. If nothing would trigger a revisit, say that
  explicitly.

## Rules

- One decision per file. If the title needs "and", split it.
- **State what is, not the history of how the decision was reached.** No account of earlier drafts,
  prior repo states, or how the thinking evolved. Rejected alternatives are the exception — they
  refute options, not history.
- Derivation runs vision → requirements → decision records → `CLAUDE.md` rules, and citation never
  runs against it. Requirements never cite a decision record.
- Only decision records cite decision records by number.
- Verify facts rather than recalling them — especially licences and version numbers, since
  existing records exist precisely because a dependency relicensed. Say so if you could not verify
  something.
- Do not mark it `accepted` yourself. Leave it `proposed` and tell the user what to review.

Finish by running `uv run task test` — a documentation test checks that no rule cites a record
missing from both the accepted set and the deferred table.
