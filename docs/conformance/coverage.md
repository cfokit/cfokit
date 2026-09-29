# Conformance coverage

What CFOKit claims about each area of financial accounting, and what evidences the claim.
ADR-0043 sets the three bands; ADR-0044 sets which sources may supply evidence.

**This map lists every area, including the ones where CFOKit does nothing.** A conformance
document naming only strengths is an advertisement. The rows marked `gap` are the honest
answer to "what is missing", and the rows marked `declined` are the honest answer to "what
will you never do".

**Status is the claim; Evidence is what currently stands behind it.** They are different
facts and the map states both. An area can be enforced by the ledger — genuinely impossible to
violate — and still carry no case, which means the claim rests on our own tests and ADR-0036
§ 5 says that is not evidence. A row reading `enforced` / `none` is not a defect. A row reading
`enforced` / `case` that has no case is.

`tests/test_conformance_corpus.py` checks this file against the corpus on every commit, in both
directions: every area whose Evidence is `case` carries at least one case of the matching kind,
every area whose Evidence is `none` or `—` carries none, every case maps to an area defined
here, and every requirement id cited below is live in `docs/product/requirements.md`. The
second direction is the one that matters over time — it stops a case being added while the map
still says nothing evidences the area, and stops the map claiming evidence that was deleted.

## Where this stands

Counted rather than asserted: `tests/test_conformance_corpus.py` recomputes these from the
tables below and fails if this section is wrong, so it cannot quietly go stale.

| | `case` | `shape` | `internal` | `none` | total |
|---|---|---|---|---|---|
| **Band 1** — enforced | 2 | — | 5 | 7 | 14 |
| **Band 2** — presented | 3 | — | 3 | 3 | 9 |
| **Band 3** — recordable | 3 | — | — | 3 | 6 |
| declined | — | — | — | — | 12 |
| gap | — | — | — | — | 4 |

**Eight areas out of twenty-nine claimed ones carry a published answer, from six cases.**
That is the honest headline and it should be read before the tables. The apparatus around
the corpus — the map, the gate, the provenance rules, the evidence classes — is further along
than the corpus itself, and apparatus is not evidence.

Depth has caught up a little: six of the eight evidenced areas now rest on more than one
case, so a single bad transcription would be caught rather than believed. `recording` and
`balance-sheet` still rest on one apiece. The thirteen `none` rows are the work, and every
one of them is a question some examiner has already set and published an answer to.

## Status values

| Status | Meaning | Evidence |
|---|---|---|
| `enforced` | The ledger enforces this. It is not possible to record books that violate it. | A conformance case: someone else's published answer. |
| `presented` | The ledger produces this, and the figures are right. | A conformance case whose published answer is a statement. |
| `recordable` | CFOKit does not decide the treatment. Given a treatment, the postings are recorded and presented correctly. | A recognition case: a cited rule, our fact pattern. |
| `declined` | Out of scope by ADR-0043. CFOKit does not decide it and does not check yours. | None. The absence of code that decides is the claim. |
| `gap` | It should exist and does not. | None. Only building it closes the row. |

## Evidence values

| Evidence | Meaning |
|---|---|
| `case` | A published answer somebody else computed agrees with ours. The strongest kind, and available for a band 3 area too wherever an examiner happened to set that problem. |
| `shape` | A recognition case pins the booking shape against a cited rule. **Much weaker — see below.** |
| `none` | Claimed, not yet evidenced, and a published answer could exist. This is the to-do list. |
| `internal` | Our own tests, only. No published answer can exist, because the question is not one accountancy asks. |
| `—` | No evidence is possible or wanted: the row is `declined` or `gap`. |

**`shape` is worth much less than `case`, and the distance is not a matter of degree.** A
recognition case supplies its own journal, so it shows that CFOKit adds up entries we handed
it — which is nearly tautological. What it is actually for is pinning a treatment's booking
shape against a cited rule *before* `BKP-06`'s rules exist to produce it, so that when they
do, the expected output is already written down with an authority attached. It is a
specification with a citation, not evidence of conformance, and a reader should discount it
accordingly.

**`internal` is an admission, not a status.** ADR-0036 § 5: agreement with our own tests is
not evidence, because they encode the same understanding as the code. These rows are marked
`internal` because no 1907 examiner ever set a problem on who wrote a transaction or whether
a report states its basis on its face — the question is real, and the independent answer to
it does not exist to be transcribed. Where such a row is wrong, nothing in the corpus will
find it.

ASC topic numbers index the area against the FASB Codification where one applies. They are a
finding aid for a reader who knows the Codification, not a claim of conformance with it.

## Band 1 — mechanics the ledger enforces

| Area | ASC | Status | Evidence | Requirements |
|---|---|---|---|---|
| **chart-of-accounts** | 105 | `enforced` | `none` | LED-01, LED-02 |
| **recording** | — | `enforced` | `case` | LED-03, LED-04 |
| **allocation** | — | `enforced` | `none` | LED-05, LED-06 |
| **draft-posted** | — | `enforced` | `internal` | LED-07 |
| **reversal** | 250 | `enforced` | `none` | LED-08 |
| **cut-off** | 270 | `enforced` | `internal` | LED-09, LED-13 |
| **opening-balances** | — | `enforced` | `none` | LED-10 |
| **period-close** | 270 | `enforced` | `none` | LED-11 |
| **year-end-close** | — | `enforced` | `none` | LED-12 |
| **adjusting-entries** | — | `enforced` | `case` | LED-04, RPT-01 |
| **obligation-settlement** | 310 | `enforced` | `none` | LED-17, AR-16 |
| **functional-currency** | 830 | `enforced` | `internal` | LED-15 |
| **attribution** | — | `enforced` | `internal` | LED-20 |
| **assignment** | — | `enforced` | `internal` | BKP-06, BKP-08, BKP-09, BKP-11, BKP-12 |
| **foreign-currency** | 830 | `gap` | — | LED-16 |

`foreign-currency` — `LED-16` is `Could`/Deferred and `LED-15` refuses any commodity other
than the entity's functional currency, so the refusal is enforced and the conversion is not
built. Deferred is not the same as absent, and the row says which.

## Band 2 — presentation the ledger produces

| Area | ASC | Status | Evidence | Requirements |
|---|---|---|---|---|
| **trial-balance** | — | `presented` | `case` | RPT-01 |
| **income-statement** | 220 | `presented` | `case` | RPT-02 |
| **balance-sheet** | 210 | `presented` | `case` | RPT-03 |
| **account-detail** | — | `presented` | `none` | RPT-05 |
| **comparatives** | 205 | `presented` | `none` | RPT-07 |
| **basis-disclosure** | 235 | `presented` | `internal` | RPT-10, LED-14 |
| **rounding** | — | `presented` | `none` | RPT-12 |
| **as-at-reproduction** | — | `presented` | `internal` | RPT-11 |
| **statement-issuance** | — | `presented` | `internal` | RPT-17 |
| **cash-flows** | 230 | `gap` | — | RPT-04 |
| **receivables-aging** | 310 | `gap` | — | — |
| **journal-query** | — | `gap` | — | RPT-06 |
| **consolidation** | 810 | `declined` | — | RPT-21 |
| **budget-variance** | — | `declined` | — | RPT-20 |

`cash-flows` — the largest gap in band 2. `RPT-04` is `Should`/Approved and there is no
cash-flow code at all.

`receivables-aging` — **no requirement defines it.** It was named once, in `RPT-09`'s list of
reports that "are defined, tested capabilities", and nowhere else in the corpus; that sentence
has been corrected to reference `RPT-01` to `RPT-05` instead. Outstanding obligations are
derived (`service/receivables.py`), but an aging report is neither built nor required, so the
row cites nothing. Whoever wants one writes the requirement first.

`consolidation`, `budget-variance` — `Could`/Deferred with named activation triggers. Declined
until the trigger fires, not refused in principle.

## Band 3 — recognition and measurement

CFOKit does not decide any of these. Where a row is `recordable`, a recognition case shows
that a treatment someone else decided is recorded and presented correctly.

| Area | ASC | Status | Evidence | Requirements |
|---|---|---|---|---|
| **cash-accrual-method** | — | `recordable` | `none` | LED-14, AR-16 |
| **prepaid-expenses** | 340 | `recordable` | `case` | LED-04, BKP-04 |
| **accrued-liabilities** | 405 | `recordable` | `none` | LED-04, BKP-04 |
| **depreciation** | 360 | `recordable` | `case` | BKP-04 |
| **internal-transfers** | — | `recordable` | `none` | BKP-14 |
| **bad-debts** | 310 | `recordable` | `case` | AR-18 |
| **revenue-recognition** | 606 | `declined` | — | — |
| **leases** | 842 | `declined` | — | — |
| **inventory-costing** | 330 | `declined` | — | LED-18, LED-19 |
| **income-taxes** | 740 | `declined` | — | — |
| **contingencies** | 450 | `declined` | — | — |
| **impairment** | 360 | `declined` | — | — |
| **fair-value** | 820 | `declined` | — | — |
| **business-combinations** | 805 | `declined` | — | — |
| **share-based-payment** | 718 | `declined` | — | — |
| **materiality** | — | `declined` | — | — |

`assignment` was the largest hole in this map and is now built (ADR-0045). It is `internal`
rather than `case` for the reason the label exists: no examiner ever set a problem on whether
a bookkeeping system replays its own decisions, so there is no published answer to transcribe
and our own tests are the only evidence there can be. `BKP-06`'s acceptance — "replaying the
full history against an unchanged rule set reproduces every assignment identically" — runs in
`tests/integration/test_assignment.py`, and the determinism it depends on is property-tested
without infrastructure in `tests/test_assignment_engine.py`.

What remains unbuilt beside it is getting transactions in (`BKP-01`, `BKP-02`, `BKP-03`), so
today the caller supplies the candidates.

`materiality` is declined in `docs/product/requirements.md` in terms: it "is not used as a
system threshold anywhere in this document, and that is deliberate… an accountant's judgment
about a set of statements, not a setting the system holds, and CFOKit does not offer to make
it."

`inventory-costing` cites `LED-18` and `LED-19` because both are `Could`/Deferred and carry the
activation trigger. Their activation also turns on the Beancount differential oracle
(ADR-0010), which is where lot semantics get independent evidence.
