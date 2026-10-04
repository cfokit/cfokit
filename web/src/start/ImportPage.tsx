import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ApiError, useApi } from "../api";
import { ActionBar, Button, Card, Money, MoneyTable, Notice, Progress } from "../components";
import type { SourceBooks } from "../quickbooks/read";
import { ChooseExport } from "./ChooseExport";
import { importBooks, type Imported } from "./importBooks";
import { StartFrame } from "./StartFrame";
import { useStarted } from "./state";

type State =
  | { kind: "preview" }
  | { kind: "importing"; done: number }
  | { kind: "imported"; result: Imported }
  | { kind: "failed"; message: string };

/** Step 3: what will be imported, confirmed or abandoned; then the import, and whether it agrees. */
export function ImportPage({ entityId }: { entityId: string }) {
  const { exported, setExported } = useStarted();
  const api = useApi();
  const navigate = useNavigate();
  const [state, setState] = useState<State>({ kind: "preview" });

  if (exported === null) {
    return (
      <StartFrame step={2} title="Choose the export again">
        <p className="text-body text-ink">
          The export isn&apos;t kept once this page closes. Choose the same file to carry on:
          anything already imported from it is recognized, and nothing is counted twice.
        </p>
        <ChooseExport onRead={setExported} />
      </StartFrame>
    );
  }
  const { books } = exported;

  const run = async () => {
    setState({ kind: "importing", done: 0 });
    try {
      const result = await importBooks(api, entityId, books, (done) =>
        setState({ kind: "importing", done }),
      );
      setState({ kind: "imported", result });
    } catch (error) {
      setState({
        kind: "failed",
        message: error instanceof ApiError ? error.message : "CFOKit stopped answering.",
      });
    }
  };

  if (state.kind === "imported") {
    return (
      <StartFrame step={2} title="Do the books agree?">
        <Agreement books={books} result={state.result} />
        <ActionBar>
          <Button
            variant="primary"
            fullWidth
            className="tablet:w-auto"
            onClick={() =>
              void navigate({ to: "/companies/$entityId/connect", params: { entityId } })
            }
          >
            Next: connect Claude
          </Button>
        </ActionBar>
      </StartFrame>
    );
  }

  if (state.kind === "importing") {
    return (
      <StartFrame step={2} title="Importing your books">
        <Progress
          value={state.done}
          max={books.entries.length}
          unit="transactions"
          label="Importing"
        />
        <p className="text-body text-ink-muted">
          It&apos;s safe to leave. Choosing the same file again picks up where this stopped, and
          nothing is counted twice.
        </p>
      </StartFrame>
    );
  }

  return (
    <StartFrame step={2} title="What will be imported">
      <Summary books={books} />
      {state.kind === "failed" && (
        <Notice tone="danger" label="The import stopped" announce>
          {state.message} Import again to carry on: nothing already imported is counted twice.
        </Notice>
      )}
      <ActionBar>
        <Button variant="primary" fullWidth className="tablet:w-auto" onClick={() => void run()}>
          Import
        </Button>
        <Button fullWidth className="tablet:w-auto" onClick={() => setExported(null)}>
          Cancel
        </Button>
      </ActionBar>
    </StartFrame>
  );
}

/** The period, the counts, and anything the person should know before agreeing (`IMP-05`). */
function Summary({ books }: { books: SourceBooks }) {
  const dates = books.entries.map((entry) => entry.transaction_date).sort();
  const lines = books.entries.reduce((sum, entry) => sum + entry.lines.length, 0);
  const untyped = books.accounts.filter((account) => account.account_type === "unknown");
  return (
    <>
      <Card>
        <dl className="grid grid-cols-2 gap-3 text-body">
          <dt className="text-ink-muted">Transactions</dt>
          <dd className="text-ink tabular-nums">{books.entries.length.toLocaleString("en-US")}</dd>
          <dt className="text-ink-muted">Posting lines</dt>
          <dd className="text-ink tabular-nums">{lines.toLocaleString("en-US")}</dd>
          <dt className="text-ink-muted">Accounts</dt>
          <dd className="text-ink tabular-nums">{books.accounts.length.toLocaleString("en-US")}</dd>
          <dt className="text-ink-muted">Covering</dt>
          <dd className="text-ink">
            {dates.length === 0 ? "No dated transactions" : `${dates[0]} to ${dates.at(-1)}`}
          </dd>
        </dl>
      </Card>
      <p className="text-body text-ink">
        Each account is created, then every transaction is posted as QuickBooks recorded it, and the
        result is checked against the totals QuickBooks states for itself.
      </p>
      {untyped.length > 0 && (
        <Notice tone="warning" label="Accounts with no type">
          QuickBooks states no type for {untyped.length === 1 ? "this account" : "these accounts"},
          so {untyped.length === 1 ? "it is" : "they are"} created as assets, for you to change:{" "}
          {untyped.map((account) => account.name).join(", ")}.
        </Notice>
      )}
      {books.balances_basis === "cash" && <CashBasisNote />}
    </>
  );
}

/** Why a cash-basis general ledger differs from books that record every invoice and bill. */
function CashBasisNote() {
  return (
    <Notice tone="neutral" label="Expect a difference">
      QuickBooks ran its general ledger on the cash basis. CFOKit records every invoice and bill
      when it happens, so what is still unpaid — receivables, payables, and the income and expenses
      behind them — will differ from QuickBooks by exactly that amount.
    </Notice>
  );
}

/** Lead with the answer, then each account that differs with both figures (`IMP-08`). */
function Agreement({ books, result }: { books: SourceBooks; result: Imported }) {
  const { reconciliation: found, refusals } = result;
  const expected = books.balances_basis === "cash" && found.divergences_net_to_zero;
  const total = found.journal_total;
  return (
    <>
      <p className="font-display text-heading text-ink">
        {found.agreed} of {found.compared} accounts match QuickBooks exactly.
      </p>
      {total !== null && (
        <Notice tone={total.agrees ? "success" : "danger"} label="Journal total">
          {total.agrees ? (
            <>
              Every transaction came across: the books total <Money amount={total.our_debits} />,
              the same as QuickBooks&apos; journal.
            </>
          ) : (
            <>
              The books total <Money amount={total.our_debits} /> and QuickBooks&apos; journal{" "}
              <Money amount={total.stated_debits} />, a difference of{" "}
              <Money amount={total.difference} />.
            </>
          )}
        </Notice>
      )}
      {found.divergences.length > 0 && (
        <>
          {expected ? (
            <CashBasisNote />
          ) : (
            <Notice tone="danger" label="Accounts that differ">
              These accounts differ from QuickBooks, and the accounting basis does not explain it.
            </Notice>
          )}
          <MoneyTable
            caption="Accounts that differ from QuickBooks"
            currency={books.commodity}
            columns={[
              { key: "account", header: "Account", kind: "text" },
              { key: "ours", header: "CFOKit", kind: "money" },
              { key: "theirs", header: "QuickBooks", kind: "money" },
            ]}
            rows={found.divergences.map((divergence) => ({
              id: divergence.account_code,
              cells: {
                account: divergence.account_code,
                ours: divergence.ours,
                theirs: divergence.theirs,
              },
              flagged: !expected,
            }))}
          />
        </>
      )}
      {refusals.length > 0 && (
        <Notice tone="warning" label={`${refusals.length} not imported`}>
          QuickBooks recorded {refusals.length === 1 ? "this transaction" : "these transactions"} in
          a way that can&apos;t be posted, so {refusals.length === 1 ? "it was" : "they were"} left
          out:
          <ul className="mt-2 flex flex-col gap-1">
            {refusals.map((refusal) => (
              <li key={refusal.reference}>
                Row {refusal.reference}
                {refusal.date === null ? "" : `, ${refusal.date}`}: {refusal.detail}
              </li>
            ))}
          </ul>
        </Notice>
      )}
      <p className="text-caption text-ink-muted">
        {result.accountsCreated} accounts created, {result.posted} transactions posted
        {result.replayed > 0 ? `, ${result.replayed} already imported earlier` : ""}.
      </p>
    </>
  );
}
