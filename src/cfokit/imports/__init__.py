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
afterwards, where `PLT-02` puts the runtime in the organisation's own hands.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
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
from cfokit.ledger.errors import LedgerError, NotAPerson
from cfokit.ledger.presentation import SourceBalance, present_reconciliation
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import balance_sheet, profit_and_loss, trial_balance
from cfokit.ledger.service.write import WriteContext, record_transaction

__all__ = [
    "Comparison",
    "Opened",
    "Plan",
    "Posted",
    "Refusal",
    "Result",
    "apply",
    "compare",
    "open_books",
    "plan",
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
class Plan:
    """What an import would do, before anything is posted (`IMP-05`)."""

    system: str
    basis: str
    balances_basis: str
    commodity: str
    accounts_to_create: tuple[str, ...]
    accounts_already_present: tuple[str, ...]
    untyped_accounts: tuple[str, ...]
    transactions: int
    postings: int
    earliest: date | None
    latest: date | None
    refusals: tuple[Refusal, ...]
    blocked: str | None = None

    @property
    def can_apply(self) -> bool:
        """Whether `apply` would do anything. A blocked plan is abandoned, not forced."""
        return self.blocked is None

    @property
    def oracle_differs_in_basis(self) -> bool:
        """Whether the reconciliation will diverge for a reason that is not a defect.

        An accrual journal checked against cash-basis balances differs by exactly what is
        unsettled — receivables, and the income not yet recognised against them, equal and
        opposite. ADR-0037 predicts that, and the prediction is what makes a *different* figure
        a defect. Surfaced so an operator reads two divergences as expected rather than as
        broken.
        """
        return self.balances_basis not in {"unknown", self.basis}


@dataclass(frozen=True, slots=True)
class Result:
    """What an import did."""

    import_id: str
    accounts_created: int
    transactions_posted: int
    # Entries a previous run of this same file already posted, returned by ADR-0029's replay
    # rather than posted again. Non-zero means a retry met work already done, which is the
    # mechanism working; it is not a count of anything that went wrong.
    transactions_replayed: int = 0
    refusals: tuple[Refusal, ...] = ()
    agreed: int = 0
    compared: int = 0
    divergences: tuple[tuple[str, Decimal, Decimal], ...] = field(default_factory=tuple)

    @property
    def reconciled(self) -> bool:
        """`IMP-08`: agreement demonstrated rather than assumed, with no tolerance."""
        return self.compared > 0 and self.agreed == self.compared


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


def plan(
    database: Database, *, entity_id: str, principal: Principal, books: SourceBooks
) -> Plan:
    """What importing `books` into this entity would do. Posts nothing, writes nothing.

    Reads the entity's own settings rather than taking them from the file: `IMP-06` refuses an
    import whose basis conflicts with the entity's declared one, and a caller who could state
    the basis could state its way past that refusal.
    """
    report = trial_balance(database, entity_id=entity_id, principal=principal, as_of=date.max)
    existing = {row.code for row in report.rows}
    with database.entity_write(entity_id) as write:
        existing |= {account.code for account in write.chart()}

    blocked = _blocking(books, report.accounting_basis, report.functional_currency)
    refusals = tuple(_refusals(books))
    refused = {refusal.reference for refusal in refusals}
    entries = [entry for entry in books.entries if entry.reference not in refused]
    dates = [entry.transaction_date for entry in entries]

    return Plan(
        system=books.system,
        basis=books.basis,
        balances_basis=books.balances_basis,
        commodity=books.commodity,
        accounts_to_create=tuple(
            account.code for account in books.accounts if account.code not in existing
        ),
        accounts_already_present=tuple(
            account.code for account in books.accounts if account.code in existing
        ),
        untyped_accounts=tuple(
            account.code for account in books.accounts if account.account_type == "unknown"
        ),
        transactions=len(entries),
        postings=sum(len(entry.lines) for entry in entries),
        earliest=min(dates, default=None),
        latest=max(dates, default=None),
        refusals=refusals,
        blocked=blocked,
    )


def apply(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    books: SourceBooks,
) -> Result:
    """Create the chart and post the journal. Re-plans first, and refuses a blocked plan.

    **Re-validated rather than trusting a plan it was handed.** A plan is a description of what
    would happen, not a permission for it, and the books may have moved since one was taken.

    Each transaction is its own write through the ledger's ordinary path — the same
    `record_transaction` an adapter calls, with its own idempotency key and its own audit row.
    One enormous transaction would be atomic and would also mean an eleven-thousand-line
    rollback over a single malformed row, which is the opposite of what `IMP-05` asks for.

    **Applying the same file twice imports it once.** Each entry's idempotency key is derived
    from the file's fingerprint and the source's own reference for the row (`_entry_key`), so a
    second call meets the keys the first one claimed and ADR-0029's replay returns the stored
    result rather than repeating the write. That matters more here than on any single write: a
    client that times out partway through eleven thousand transactions and retries would
    otherwise post a whole company's books twice, and append-only leaves no correction for that
    short of a reversing entry per duplicate (ADR-0007). `Result.transactions_replayed` counts
    what a previous run had already done.

    Every entry carries `derived_from` naming this import and the reference it came in under,
    which is `IMP-04`'s "identifiable as imported and names the system it came from" and the
    lineage `SOC1-14` wants.

    **A person's act, never a delegated agent's.** ADR-0007 puts it plainly — the agent
    proposes and a person's confirmation posts — and this is the largest single act of posting
    the system offers: a company's whole history, in one call. `plan` is the proposing half and
    holds no such restriction, which is the division ADR-0030 already drew around reopening a
    closed period.

    Checked on `actor_class`, which comes from the shape of the token and never from a claim
    the caller sets (ADR-0033). A token carrying no delegation is a person's; one carrying an
    RFC 8693 `act` claim is an agent acting for someone, and it is that second shape this
    refuses.
    """
    _require_person(principal)

    proposed = plan(database, entity_id=entity_id, principal=principal, books=books)
    if proposed.blocked is not None:
        raise ImportRefused(proposed.blocked)

    import_id = _import_id(books.fingerprint)
    accounts, created = _create_chart(
        database,
        entity_id=entity_id,
        principal=principal,
        request_id=request_id,
        accounts=books.accounts,
    )

    refused = {refusal.reference for refusal in proposed.refusals}
    posted = 0
    replayed = 0
    failures: list[Refusal] = list(proposed.refusals)
    for entry in books.entries:
        if entry.reference in refused:
            continue
        try:
            written = record_transaction(
                database,
                WriteContext(
                    entity_id=entity_id,
                    principal=principal,
                    request_id=request_id,
                    idempotency_key=_entry_key(books.fingerprint, entry.reference),
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
                    "system": books.system,
                    "import_id": import_id,
                    "reference": entry.reference,
                },
            )
        except LedgerError as refusal:
            # A refusal the plan could not foresee — a closed period, an account the chart
            # would not take. Reported, never swallowed: `NFR-01` resolves disagreements
            # rather than tolerating them, and a transaction the ledger declined is one.
            failures.append(
                Refusal(
                    reference=entry.reference,
                    when=entry.transaction_date,
                    code=refusal.code,
                    detail=str(refusal),
                )
            )
        else:
            # Counted apart, because they answer different questions. `posted` is what this
            # call put in the books; `replayed` is what a previous one already had. An operator
            # re-running an import wants to see the second number rise and the first stay at
            # zero — that is the retry working rather than the file half-importing.
            if written.replayed:
                replayed += 1
            else:
                posted += 1

    agreed, compared, divergences = _reconcile(
        database, entity_id=entity_id, principal=principal, books=books
    )
    return Result(
        import_id=import_id,
        accounts_created=created,
        transactions_posted=posted,
        transactions_replayed=replayed,
        refusals=tuple(failures),
        agreed=agreed,
        compared=compared,
        divergences=divergences,
    )


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
    _require_person(principal)
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
    _require_person(principal)
    import_id = _import_id(fingerprint)
    with database.entity_write(entity_id) as write:
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

    The same two checks `_refusals` makes over a whole file, plus the one only a batch can make:
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


def _require_person(principal: Principal) -> None:
    """ADR-0007, ADR-0033: from the shape of the token, never from a claim the caller sets."""
    if principal.actor_class is not ActorClass.PERSON:
        raise NotAPerson(
            "importing a company's books is a person's act; ask the person you act for"
        )


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


def _refusals(books: SourceBooks) -> list[Refusal]:
    """Rows the import will skip, decided before anything is posted (`IMP-05`)."""
    refusals: list[Refusal] = []
    for entry in books.entries:
        if len(entry.lines) < MINIMUM_POSTINGS:
            # The engine's own threshold, imported rather than restated. A single line sums to
            # zero when its amount is zero, so a balance check alone would pass it while it
            # records no movement of value — which is exactly why `TransactionIncomplete` is a
            # separate refusal from `unbalanced_transaction`.
            refusals.append(
                Refusal(
                    entry.reference,
                    entry.transaction_date,
                    "transaction_incomplete",
                    f"{len(entry.lines)} posting(s); a movement of value needs"
                    f" {MINIMUM_POSTINGS}",
                )
            )
        elif (difference := sum(line.amount for line in entry.lines)) != 0:
            # LED-03. Stated here rather than left to the engine so the operator sees it in
            # the plan, which is the whole of what `IMP-05` asks for.
            refusals.append(
                Refusal(
                    entry.reference,
                    entry.transaction_date,
                    "unbalanced",
                    f"debits and credits differ by {difference}",
                )
            )
    return refusals


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
