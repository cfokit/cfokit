import type { ReactNode } from "react";
import { Money } from "./Money";

export interface Column {
  key: string;
  header: string;
  /** `money` cells hold decimal strings and are set in `money`, right-aligned. */
  kind: "text" | "money";
}

export interface Row {
  id: string;
  cells: Record<string, string>;
  /** Marks the row the reader should look at next, such as one that differs, with an `ochre` tick. */
  flagged?: boolean;
}

interface MoneyTableProps {
  /** What the table lists, for screen readers and as its caption. */
  caption: string;
  columns: Column[];
  rows: Row[];
  /** The currency, shown once, in each money column's header: "USD". */
  currency: string;
  /** Totals the API computed, by money column key. Never summed on the page (RPT-12). */
  totals?: Record<string, string>;
  /** The commodity's display scale (ADR-0025). */
  scale?: number;
}

function Flag() {
  return <span aria-hidden="true" className="inline-block size-2 shrink-0 bg-ochre" />;
}

/**
 * Rows of figures. `label` headers on `sunken`, rows divided by `rule`, amounts right-aligned in
 * `money`, totals from the API beneath in `money-total`. The first column names the row.
 *
 * Below `bp-tablet`, a table of one or two figures per row becomes a list: the row's name on one
 * line, its other text in `caption`, and its figures beside it or labeled beneath. A wider table
 * keeps its columns and scrolls sideways within its own frame, its first column fixed; the page
 * never scrolls sideways.
 */
export function MoneyTable({
  caption,
  columns,
  rows,
  currency,
  totals,
  scale = 2,
}: MoneyTableProps) {
  const [first, ...rest] = columns;
  if (first === undefined) throw new Error("MoneyTable needs at least one column");
  const money = columns.filter((c) => c.kind === "money");
  const stacks = money.length <= 2;
  const header = (c: Column) => (c.kind === "money" ? `${c.header} ${currency}` : c.header);
  const cell = (c: Column, row: Row): ReactNode => {
    // A row with no figure for a column shows an empty cell, not a zero it was never given.
    const value = row.cells[c.key];
    if (value === undefined) return null;
    return c.kind === "money" ? <Money amount={value} scale={scale} /> : value;
  };

  return (
    <div>
      <div
        className={`overflow-x-auto rounded-sm border border-rule ${stacks ? "hidden tablet:block" : ""}`}
      >
        <table className="w-full border-separate border-spacing-0 bg-surface">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th
                  key={c.key}
                  scope="col"
                  className={[
                    "bg-sunken px-4 py-2 text-label whitespace-nowrap text-ink-muted",
                    c.kind === "money" ? "text-right" : "text-left",
                    i === 0 ? "sticky left-0" : "",
                  ].join(" ")}
                >
                  {header(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <th
                  scope="row"
                  className="sticky left-0 border-b border-rule bg-surface px-4 py-3 text-left text-body font-normal text-ink"
                >
                  <span className="flex items-center gap-2">
                    {row.flagged === true && <Flag />}
                    {row.flagged === true && <span className="sr-only">Look at this: </span>}
                    {cell(first, row)}
                  </span>
                </th>
                {rest.map((c) => (
                  <td
                    key={c.key}
                    className={`border-b border-rule px-4 py-3 text-body text-ink ${
                      c.kind === "money" ? "text-right" : "text-left"
                    }`}
                  >
                    {cell(c, row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {totals !== undefined && (
            <tfoot>
              <tr>
                <th
                  scope="row"
                  className="sticky left-0 bg-surface px-4 py-3 text-left text-label text-ink"
                >
                  Total
                </th>
                {rest.map((c) => (
                  <td key={c.key} className="px-4 py-3 text-right text-ink">
                    {c.kind === "money" && totals[c.key] !== undefined && (
                      <Money amount={totals[c.key] ?? ""} scale={scale} variant="total" />
                    )}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {stacks && (
        <ul aria-label={caption} className="border-t border-rule tablet:hidden">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-col gap-1 border-b border-rule py-3">
              <div className="flex items-start justify-between gap-3">
                <span className="flex min-w-0 flex-col">
                  <span className="flex items-center gap-2 text-body text-ink">
                    {row.flagged === true && <Flag />}
                    {row.flagged === true && <span className="sr-only">Look at this: </span>}
                    {cell(first, row)}
                  </span>
                  {rest
                    .filter((c) => c.kind === "text")
                    .map((c) => (
                      <span key={c.key} className="text-caption text-ink-muted">
                        {row.cells[c.key]}
                      </span>
                    ))}
                </span>
                {money.length === 1 && money[0] !== undefined && (
                  <span className="text-ink">{cell(money[0], row)}</span>
                )}
              </div>
              {money.length === 2 && (
                <dl className="flex flex-col gap-1">
                  {money.map((c) => (
                    <div key={c.key} className="flex justify-between gap-3">
                      <dt className="text-caption text-ink-muted">{header(c)}</dt>
                      <dd className="text-ink">{cell(c, row)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ))}
          {totals !== undefined && (
            <li className="flex flex-col gap-1 py-3">
              {money.map((c) =>
                totals[c.key] === undefined ? null : (
                  <div key={c.key} className="flex justify-between gap-3">
                    <span className="text-label text-ink">
                      Total{money.length === 2 ? `, ${c.header}` : ""} {currency}
                    </span>
                    <Money
                      amount={totals[c.key] ?? ""}
                      scale={scale}
                      variant="total"
                      className="text-ink"
                    />
                  </div>
                ),
              )}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
