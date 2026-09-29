"""Import: landing a company's books from the system it already runs (`IMP-01` to `IMP-08`).

**The first module** under ADR-0022, and a sibling of the ledger rather than part of it. The
ledger owns the double-entry primitive and "knows nothing about customers, invoices, banks" —
understanding what a QuickBooks export is, is exactly the domain knowledge that boundary keeps
out. Reading our own books *out* stays in the ledger (`EXP-01`, `EXP-02`) because that needs no
foreign vocabulary; reading someone else's books *in* needs a great deal of it.

**In-process, not a separate component.** ADR-0022 § 3 makes in-process the default and
separation something to be earned. An import holds no third-party credential today, and its
one real claim to separation — that a third party could build a Xero reader against the API —
is about an extension point that does not exist (`NFR-12`). A boundary drawn around that guess
is the mistake the deleted `connectors` package already made once (ADR-0012, ADR-0031).

**Named for the capability.** Not `quickbooks`, which names a vendor, and not `ingest`, which
names a mechanism. `imports` rather than `import` only because the latter is a keyword.

**Two calls, because `IMP-05` requires two.** `plan` reads the file and says what would happen;
`apply` does it. The operator sees what will be created and what will not, and can abandon it.
`apply` re-validates rather than trusting the plan it was handed: a plan is a description, not
a permission.

**The file never passes through a model.** `plan` and `apply` take an archive and return a
summary; the transactions themselves go from the file to the database without an intermediate
that has to hold them all. That is an engineering constraint before it is anything else — an
export of this size does not fit usefully in a context, and a model asked to carry it is a
lossy pipe that adds nothing. What a model is *for* here is reading the loaded books
afterwards, where `PLT-02` puts the runtime in the organization's own hands.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cfokit.imports.source import (
    SourceAccount,
    SourceBooks,
    SourceEntry,
    StatedStatement,
)
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.engine.postability import MINIMUM_POSTINGS
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.presentation import SourceBalance, present_reconciliation
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account
from cfokit.ledger.service.authorization import authorize_own_act
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.reports import (
    balance_sheet,
    journal_totals,
    profit_and_loss,
    trial_balance,
)
from cfokit.ledger.service.write import WriteContext, record_transaction

__all__ = [
    "Comparison",
    "Opened",
    "Posted",
    "Refusal",
    "TotalAgreement",
    "check_total",
    "compare",
    "nets_to_zero",
    "open_books",
    "post_entries",
]

# An account the source states no type for. The chart admits five types and none of them means
# "unknown", so something has to be chosen; `asset` is inert for a trial balance, which groups
# by sign rather than by type. Recorded in the plan so the operator sees it rather than
# discovering it in a statement.
FALLBACK_TYPE = "asset"


@dataclass(frozen=True, slots=True)
class Refusal:
    """One thing the import will not do, and why.

    `IMP-05` requires the operator to see "what will be created, **and what will not**". A
    refusal is part of the plan, not an error that stops it: an export with three malformed
    rows out of eleven thousand should import the rest and say so.
    """

    reference: str
    when: date | None
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class Opened:
    """An import's chart, created and ready for entries (`IMP-05` step two)."""

    import_id: str
    accounts_created: int
    accounts_already_present: int


@dataclass(frozen=True, slots=True)
class Posted:
    """What one batch of entries did.

    `posted` and `replayed` answer different questions and are never summed. An operator
    re-running an import wants to see the second rise and the first stay at zero — that is the
    retry working rather than the file half-importing (ADR-0029).
    """

    posted: int
    replayed: int
    refusals: tuple[Refusal, ...] = ()


def _create_chart(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    accounts: tuple[SourceAccount, ...],
) -> tuple[dict[str, str], int]:
    """Create every account the source uses that this entity does not have.

    Sorted, so a parent is created before anything under it: a path sorts before every path it
    prefixes, which is the ordering the chart's foreign key needs.

    Idempotent by observation rather than by a key — an account already present is skipped — so
    a client that retries the opening step creates nothing twice.
    """
    known: dict[str, str] = {}
    with database.entity_write(entity_id) as write:
        known = {account.code: account.account_id for account in write.chart()}

    created = 0
    for account in sorted(accounts, key=lambda a: a.code):
        if account.code in known:
            continue
        known[account.code] = create_account(
            database,
            entity_id=entity_id,
            principal=principal,
            request_id=request_id,
            code=account.code,
            name=account.name,
            account_type=(
                account.account_type if account.account_type != "unknown" else FALLBACK_TYPE
            ),
            parent_id=known.get(account.parent) if account.parent else None,
        )
        created += 1
    return known, created


def open_books(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    books: SourceBooks,
) -> Opened:
    """Create the chart an import needs, and name the import (`IMP-01`).

    The first of three calls, because the entries arrive in batches and something has to exist
    for them to post into. Takes the shape with `entries` empty: an opening call carrying a
    company's whole journal would be the single enormous request this shape exists to avoid.

    **A person's act, like `apply`.** ADR-0007 puts it plainly — the agent proposes and a
    person's confirmation posts — and creating a company's chart of accounts is the first half
    of that act rather than a preliminary to it.
    """
    with database.entity_write(entity_id) as write:
        authorize_own_act(write, principal)

    blocked = _blocking_shape(database, entity_id=entity_id, principal=principal, books=books)
    if blocked is not None:
        raise ImportRefused(blocked)

    _, created = _create_chart(
        database,
        entity_id=entity_id,
        principal=principal,
        request_id=request_id,
        accounts=books.accounts,
    )
    return Opened(
        import_id=_import_id(books.fingerprint),
        accounts_created=created,
        accounts_already_present=len(books.accounts) - created,
    )


def post_entries(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    system: str,
    fingerprint: str,
    entries: Sequence[SourceEntry],
) -> Posted:
    """Post one batch of entries (`IMP-02`).

    Each entry is its own write through the ledger's ordinary path, with a key derived from
    the file's fingerprint and the source's own reference. A batch sent twice is a replay rather
    than a second set of books (ADR-0029), which is what lets a client that dies mid-import
    resume by sending the same batches again.

    A refusal the plan could not foresee — a closed period, or an account the chart will not
    take — is reported rather than swallowed. `NFR-01` resolves disagreements rather than
    tolerating them, and a transaction the ledger declined is one.
    """
    import_id = _import_id(fingerprint)
    with database.entity_write(entity_id) as write:
        authorize_own_act(write, principal)
        accounts = {account.code: account.account_id for account in write.chart()}

    posted = replayed = 0
    refusals: list[Refusal] = []
    for entry in entries:
        problem = _unpostable(entry, accounts)
        if problem is not None:
            refusals.append(problem)
            continue
        try:
            written = record_transaction(
                database,
                WriteContext(
                    entity_id=entity_id,
                    principal=principal,
                    request_id=request_id,
                    idempotency_key=_entry_key(fingerprint, entry.reference),
                ),
                entry=Entry(
                    transaction_date=entry.transaction_date,
                    postings=tuple(
                        Posting(
                            account_id=accounts[line.account_code],
                            amount=line.amount,
                            commodity=line.commodity,
                        )
                        for line in entry.lines
                    ),
                    description=entry.description or None,
                ),
                post=True,
                derived_from={
                    "system": system,
                    "import_id": import_id,
                    "reference": entry.reference,
                },
            )
        except LedgerError as refusal:
            refusals.append(
                Refusal(
                    reference=entry.reference,
                    when=entry.transaction_date,
                    code=refusal.code,
                    detail=str(refusal),
                )
            )
        else:
            if written.replayed:
                replayed += 1
            else:
                posted += 1
    return Posted(posted=posted, replayed=replayed, refusals=tuple(refusals))


def _unpostable(entry: SourceEntry, accounts: dict[str, str]) -> Refusal | None:
    """Why this entry will not post, decided before the write is attempted.

    The two checks a whole file used to be scanned for, plus the one only a batch can make:
    an account the opening call did not create. A batch naming an unknown account is a client
    that skipped the opening step or sent a file's entries against another file's chart.
    """
    if len(entry.lines) < MINIMUM_POSTINGS:
        return Refusal(
            entry.reference,
            entry.transaction_date,
            "transaction_incomplete",
            f"{len(entry.lines)} posting(s); a movement of value needs {MINIMUM_POSTINGS}",
        )
    difference = sum(line.amount for line in entry.lines)
    if difference != 0:
        return Refusal(
            entry.reference,
            entry.transaction_date,
            "unbalanced",
            f"debits and credits differ by {difference}",
        )
    missing = sorted({line.account_code for line in entry.lines} - set(accounts))
    if missing:
        return Refusal(
            entry.reference,
            entry.transaction_date,
            "unknown_account",
            f"this entity has no account {missing[0]!r};"
            " open the import before posting entries",
        )
    return None


def _blocking_shape(
    database: Database, *, entity_id: str, principal: Principal, books: SourceBooks
) -> str | None:
    """Whether this shape may be imported into this entity at all.

    Read from the entity rather than taken from the caller: `IMP-06` refuses an import whose
    basis conflicts with the entity's declared one, and a caller who could state the basis could
    state its way past that refusal.
    """
    report = trial_balance(database, entity_id=entity_id, principal=principal, as_of=date.max)
    return _blocking(books, report.accounting_basis, report.functional_currency)


class ImportRefused(LedgerError):
    """The import cannot proceed at all, as opposed to skipping rows within one."""

    code = "import_refused"
    status = 422


def _import_id(fingerprint: str) -> str:
    """This import's identity, derived from the file rather than minted.

    A uuid5 so `derived_from.import_id` keeps the shape every other identifier has, while
    naming the same import on a re-run. A minted uuid4 would make a retry look like a second,
    unrelated import of the same books.
    """
    return str(uuid.uuid5(_IMPORT_NAMESPACE, fingerprint))


def _entry_key(fingerprint: str, reference: str) -> str:
    """The idempotency key for one imported entry (ADR-0029).

    **Derived, not minted, and this is what makes an import safe to retry.** An import is
    thousands of writes in a loop, so the interesting failure is not the first call — it is a
    client that times out partway through and sends the request again. With a fresh key per
    entry that retry posts every transaction a second time, and under append-only the only
    correction available is a reversing entry per duplicated transaction (ADR-0007). With this
    one, each entry meets the key its first attempt used, and `claim` returns the stored result
    instead of doing the work.

    `(file, row)` rather than `(file, content)`: ADR-0029 rejects content hashing for deciding
    whether two requests are the same operation, because two five-dollar coffees on the same day
    are two transactions. The source's own reference is what distinguishes them, and `IMP-04`
    already requires it to survive into `derived_from`.

    Keys are scoped per entity by `idempotency_key`'s primary key, so importing one file into
    two entities is two imports rather than a replay of the first.
    """
    return f"import:{fingerprint[:32]}:{reference}"


# A fixed namespace, so `_import_id` is stable across processes and deployments. Arbitrary and
# permanent: changing it would make every already-imported file importable again.
_IMPORT_NAMESPACE = uuid.UUID("6f9b1d2c-0e77-5a41-9c3e-2a5d8f4b6e10")


def _blocking(books: SourceBooks, basis: str, commodity: str) -> str | None:
    """Whether the import is refused outright, and why.

    Two conditions, both from the requirements and both about the *file* rather than its rows.
    A row-level problem skips a row; these mean the file is the wrong file for this entity.
    """
    if books.basis != "unknown" and books.basis != basis:
        # IMP-06, and only about the *entries*. Importing cash-basis entries into accrual books
        # would land figures no posting path can reconcile, because basis is a presentation
        # property and nothing branches on it (ADR-0037).
        #
        # `books.balances_basis` is deliberately not checked here. That is the method a *report*
        # in the same file was run on; it explains a divergence rather than causing one, and
        # refusing on it would reject an accrual journal because a cash-basis report sat beside
        # it. `unknown` does not block either — a source that states no method for its raw
        # record has not disagreed with anything.
        return (
            f"the source states {books.basis} basis and this entity is {basis}"
            " — importing would land figures the books cannot reproduce"
        )
    # The declared commodity and the entries' commodities are checked separately, because the
    # batched surface opens an import before it has sent a single entry — a file declaring GBP
    # against books kept in USD has to be refused then, not eleven thousand rows later. Where
    # entries are present the per-line check still runs, so a top-level field that lied about
    # them is caught too.
    stated = {line.commodity for entry in books.entries for line in entry.lines}
    if books.commodity:
        stated.add(books.commodity)
    foreign = sorted(stated - {commodity})
    if foreign:
        # IMP-07, on the same terms as any other foreign amount (`LED-15`).
        return f"the source carries {', '.join(foreign)} and this entity is {commodity}"
    return None


@dataclass(frozen=True, slots=True)
class TotalAgreement:
    """The source's own journal total against ours (`IMP-08`, ADR-0050).

    **Basis-free.** Every report in an export is run on whichever basis the company keeps, so a
    per-account comparison against one diverges on the obligation accounts by exactly what is
    unsettled. The journal prints no basis, because it is the record rather than a view, so this
    comparison holds whatever the reports say.

    It proves the file was read completely and at the right magnitude. It proves nothing about
    which account a row landed in — two accounts transposed total the same — which is what the
    per-account comparison is for.
    """

    stated_debits: Decimal
    stated_credits: Decimal
    our_debits: Decimal
    our_credits: Decimal

    @property
    def agrees(self) -> bool:
        return self.our_debits == self.stated_debits and self.our_credits == self.stated_credits

    @property
    def difference(self) -> Decimal:
        """How far our debits are from theirs — the figure to go looking with."""
        return self.our_debits - self.stated_debits


def check_total(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    books: SourceBooks,
    as_of: date | None = None,
) -> TotalAgreement | None:
    """Our totals against the total the source states for its own journal.

    `None` where the source prints none. Not computed in that case: summing the rows ourselves
    and comparing that against the books we loaded them into would be comparing our arithmetic
    against itself, which is the thing `IMP-08` exists to avoid (`NFR-01`).

    Totalled over the whole entity rather than over this import, because that is what the source
    stated — an export's journal is the company's history, and a second import into the same
    books would make the two figures answer different questions. A reconciliation run against
    books that already held transactions is one an operator should read as such.
    """
    if books.journal_total is None:
        return None
    ours = journal_totals(
        database, entity_id=entity_id, principal=principal, as_of=as_of or date.max
    )
    return TotalAgreement(
        stated_debits=books.journal_total.debits,
        stated_credits=books.journal_total.credits,
        our_debits=ours.debits,
        our_credits=ours.credits,
    )


def nets_to_zero(divergences: Sequence[tuple[str, Decimal, Decimal]]) -> bool:
    """Whether a set of divergences is consistent with an accounting-basis difference.

    **Cash basis excludes whole transactions.** An unpaid invoice is a debit to receivables
    and a credit to income; dropping it removes both. So the difference between an accrual
    journal and a cash-basis report is composed of balanced transactions and sums to zero in
    posting signs.

    A set that nets is reported as a basis difference. A set that does not is a defect, and
    `NFR-01` forbids carrying it either way — this is what makes the reported difference an
    arithmetic result rather than a note somebody has to agree with (ADR-0050).

    **Necessary, not sufficient.** A transaction posted to the wrong account also nets to zero.
    The guard against that is the accounts that agree exactly, and the journal total above.
    """
    return sum((ours - theirs for _, ours, theirs in divergences), Decimal(0)) == 0


def _reconcile(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    books: SourceBooks,
    as_of: date | None = None,
) -> tuple[int, int, tuple[tuple[str, Decimal, Decimal], ...]]:
    """`IMP-08`: agreement with the source demonstrated rather than assumed.

    Against the balances the source states for itself, which is the source's own arithmetic
    over its own data. Summing the journal ourselves and calling it an oracle would be
    comparing our arithmetic against itself.

    An account the source states zero for is absent from ours, because `RPT-01` reports
    non-zero balances. Left out of the comparison rather than counted as a divergence: the two
    systems state the same figure in different ways, and calling that a disagreement would
    bury the ones that are real.
    """
    if not books.balances:
        return 0, 0, ()
    # The caller's date where it has one, and the journal's last otherwise. The batched surface
    # reconciles from a request that carries balances and no entries, so there is nothing there
    # to take a period from; `date.max` is "all dates", which is what the source's own reports
    # were run over.
    if as_of is None:
        as_of = max((entry.transaction_date for entry in books.entries), default=date.max)
    report = present_reconciliation(
        trial_balance(database, entity_id=entity_id, principal=principal, as_of=as_of),
        [
            SourceBalance(account_code=balance.account_code, balance=balance.balance)
            for balance in books.balances
        ],
    )
    stated = [
        comparison
        for comparison in report.comparisons
        if not comparison.only_ours and not (comparison.only_theirs and comparison.theirs == 0)
    ]
    divergences = tuple(
        (
            comparison.account_code,
            comparison.ours or Decimal(0),
            comparison.theirs or Decimal(0),
        )
        for comparison in stated
        if not comparison.agrees
    )
    return len(stated) - len(divergences), len(stated), divergences


# A statement prints income, liabilities and equity as positive; a posting signs them negative,
# because positive is a debit. The two conventions meet here and nowhere else — translating in
# the reader would bury it, and translating in the ledger would be the ledger learning what a
# statement looks like.
_PRINTED_AS_CREDIT = {"income", "liability", "equity"}


@dataclass(frozen=True, slots=True)
class Comparison:
    """One statement, ours against theirs."""

    report: str
    their_basis: str
    our_basis: str
    agreed: int
    divergences: tuple[tuple[str, Decimal, Decimal], ...] = ()
    only_ours: tuple[str, ...] = ()
    only_theirs: tuple[str, ...] = ()
    unmatched: tuple[str, ...] = ()

    @property
    def compared(self) -> int:
        return self.agreed + len(self.divergences)

    @property
    def agrees(self) -> bool:
        return self.compared > 0 and not self.divergences


def compare(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    books: SourceBooks,
    since: date | None = None,
    as_of: date | None = None,
) -> tuple[Comparison, ...]:
    """Every statement the source printed, against the one CFOKit produces (`IMP-08`).

    **Against the source's own figures**, which is what makes this evidence rather than a
    self-check: summing our own postings twice and comparing the results would prove only that
    addition is deterministic (`NFR-01`).

    The period is the source's: "all dates", so the whole span of what it carries. A statement
    over a different period would differ for a reason that says nothing about correctness.

    An account on one side only is reported rather than dropped. A line silently missing from a
    comparison is a difference that reads as agreement.
    """
    if not books.entries and not books.statements:
        return ()
    # As above: the period is the caller's where it states one, and the journal's otherwise.
    # `date.min` to `date.max` is "all dates", which is what a source's own statements are run
    # over and therefore the only period that compares like with like.
    if since is None:
        since = min((entry.transaction_date for entry in books.entries), default=date.min)
    if as_of is None:
        as_of = max((entry.transaction_date for entry in books.entries), default=date.max)

    comparisons: list[Comparison] = []
    for stated in books.statements:
        if stated.report == "profit_and_loss":
            report = profit_and_loss(
                database,
                entity_id=entity_id,
                principal=principal,
                since=since,
                as_of=as_of,
            )
            ours = {row.code: (row.balance, row.account_type) for row in report.rows}
            basis = report.accounting_basis
        else:
            sheet = balance_sheet(
                database, entity_id=entity_id, principal=principal, as_of=as_of
            )
            # `unclosed` holds the income and expense balances that have not been moved to
            # equity yet, which is how our sheet balances (`LED-12`). A printed balance sheet
            # shows them as one "Net Income" line instead, so comparing them here would report
            # every income account as ours-only — and they are compared, by account, in the
            # profit and loss above.
            ours = {row.code: (row.balance, row.account_type) for row in sheet.rows}
            basis = sheet.accounting_basis

        comparisons.append(_compare(stated, ours, basis))
    return tuple(comparisons)


def _compare(
    stated: StatedStatement,
    ours: dict[str, tuple[Decimal, str]],
    our_basis: str,
) -> Comparison:
    theirs = {line.account_code: line.balance for line in stated.lines}
    agreed = 0
    divergences: list[tuple[str, Decimal, Decimal]] = []

    for code, printed in theirs.items():
        if code not in ours:
            continue
        balance, account_type = ours[code]
        as_printed = -balance if account_type in _PRINTED_AS_CREDIT else balance
        if as_printed == printed:
            agreed += 1
        else:
            divergences.append((code, as_printed, printed))

    return Comparison(
        report=stated.report,
        their_basis=stated.basis,
        our_basis=our_basis,
        agreed=agreed,
        divergences=tuple(sorted(divergences)),
        only_ours=tuple(sorted(set(ours) - set(theirs))),
        only_theirs=tuple(sorted(set(theirs) - set(ours))),
        unmatched=stated.unmatched,
    )
