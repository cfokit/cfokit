---
description: Add a conformance case from a published worked problem, without contaminating its answer
argument-hint: [an area from docs/conformance/coverage.md, or a source to work from]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, Task
---

Add a conformance case for: **$ARGUMENTS**

The corpus carries `NFR-01` while the differential oracle stays deferred (ADR-0010, ADR-0036
§ 2). A case is only worth what its independence is worth, and the threat to that is not
ignorance — it is the transcription drifting toward what CFOKit already does, because whoever
transcribes it has the implementation in context.

## Steps

1. **Pick the cell, not the source.** Read `docs/conformance/coverage.md` and choose an area
   whose Evidence is `none`, preferring `enforced` and `presented` rows. Then go and find a
   problem for it. Working the other way — finding a nice problem and deciding what it covers
   — produces a corpus that is thick where sources are easy and thin where risk is.

2. **Vet the licence before transcribing anything.** ADR-0044: `public-domain` or `cc0`, and
   nothing else. Check the specific item, never the collection — the AICPA historical
   collection holds both public-domain and in-copyright items, and OpenStax's accounting
   titles are NC-SA where most OpenStax titles are CC BY. Record which basis applies:
   `term-expired` (before the cutoff in `tests/test_conformance_corpus.py`), `not-renewed`
   (needs `pd_determination`, a URL to a determination **someone else published** — never a
   renewal search of our own), or `us-government`.

   Good veins: pre-1931 US accountancy texts and state and AIA examination problems with
   published solutions, on archive.org and HathiTrust; US Government works, which carry no
   copyright at all. Prefer the raw OCR (`archive.org/download/<id>/<id>_djvu.txt`) over a
   summarising fetch — a model that paraphrases a figure has destroyed the case.

3. **Transcribe double-blind.** One pass reads the *problem statement only* and writes
   `accounts.csv` and `journal.csv`. A separate pass reads the *published solution only* and
   writes the expected answer. Neither pass reads CFOKit's source or output. Use sub-agents:
   the isolation is the control, and it is cheap.

4. **Choose the answer shape honestly.** A source that prints a trial balance gives a
   `trial_balance` answer, compared account by account. A source that prints a *statement*
   gives `profit_and_loss` or `balance_sheet`, compared against the **totals it printed** —
   because a published statement of this era summarises, and mapping its summary lines back
   onto account codes is a step the source never took. Assert only the figures the source
   actually states; if a total depends on how we chose to model an account, it is ours and
   not evidence.

5. **Run the arithmetic pre-check before CFOKit sees it.** A throwaway script, importing
   nothing from `cfokit`: every entry sums to zero, the source's own printed totals are
   reproduced from the transcribed figures, and the accounting equation holds. A failure here
   is a transcription error, and catching it now keeps it out of the triage below. Look for a
   second, independent tie in the source — a column total, a partner's closing balance, a
   figure that appears in two statements — and check that too. It is the cheapest evidence
   that a digit was read correctly.

6. **Write the manifest**, modelled on an existing case. `[source]`, `[coverage]` naming
   areas and live requirement ids, `[expected]`, and a `[transcription]` block recording every
   OCR repair, every choice the source left open, and every cross-check that confirmed a
   figure.

7. **Update `docs/conformance/coverage.md`** — set the area's Evidence to `case`. The gate
   fails in both directions, so a case added without this fails, and so does a map claiming a
   case that was deleted.

8. **Run it**, and triage any disagreement into exactly one of three, never silently:

   - **a CFOKit defect** — fix the code. This is the case the corpus exists for, and it is the
     only outcome that is good news.
   - **a transcription error** — fix the case, and record what was misread under
     `[transcription]`.
   - **a genuine difference of period or practice** — record it under `[divergence]` with its
     reason, the way ADR-0010 requires of the oracle's register.

   **A case may not be edited into passing without a `[divergence]` entry.** Adjusting an
   expected figure until it matches is how a corpus becomes a mirror.

9. **Verify both tiers.**

   ```
   uv run task lint
   uv run task test tests/test_conformance_corpus.py
   docker compose --profile test build test      # source is copied, not mounted
   docker compose --profile test run --rm test
   ```

## Refused outright

- **A fact pattern nobody published.** In the corpus that is a unit test that has been
  misfiled. If the rule is published but the fact pattern is ours, it is a *recognition* case
  and belongs in `tests/fixtures/recognition/` under its own gate — weaker evidence, kept
  apart deliberately (ADR-0044).
- **An expected value obtained by running CFOKit.** ADR-0036 § 5: that pins current behaviour
  including its defects, which is the blind spot layer 2 exists to close.
- **A source consulted but not redistributable** — a sample company file, an illustration read
  under a standard setter's own terms, an NC-licensed exercise. Lawful to read, and it may
  reveal a defect. It may never supply an expected value. What it finds enters the repository
  as a fix plus a test resting on an invariant or a Tier A citation.
