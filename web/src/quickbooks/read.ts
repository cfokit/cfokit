/**
 * Read a QuickBooks Online export into CFOKit's neutral interchange shape (ADR-0041).
 *
 * **Runs where the file is**: in the person's browser, in a Web Worker (ADR-0058). The archive
 * never reaches CFOKit: the server accepts the shape below and parses no foreign binary format, so
 * a zip bomb or a hostile spreadsheet reaches the machine whose owner opened it and nothing else
 * (`NFR-04`).
 *
 * **Amounts are strings, never JavaScript numbers.** A number is a float, and a float's binary
 * expansion is not the figure the workbook shows (ADR-0005). Arithmetic on a figure is `big.js`.
 */

import Big from "big.js";
import { Refused } from "./refused";
import { rows as sheetRows, type Cell, type Row } from "./sheet";
import { MAX_ARCHIVE_BYTES, Zip } from "./zip";

export type Basis = "accrual" | "cash" | "unknown";
export type AccountType = "asset" | "liability" | "equity" | "income" | "expense" | "unknown";

export interface SourceAccount {
  code: string;
  name: string;
  account_type: AccountType;
  parent: string;
}
export interface SourceLine {
  account_code: string;
  amount: string;
  commodity: string;
}
export interface SourceEntry {
  reference: string;
  transaction_date: string;
  description: string;
  lines: SourceLine[];
}
export interface StatedBalance {
  account_code: string;
  balance: string;
}
export interface StatedStatement {
  report: "profit_and_loss" | "balance_sheet";
  basis: Basis;
  lines: StatedBalance[];
  unmatched: string[];
}

/** The neutral interchange shape: what the import endpoints take, and nothing about QuickBooks. */
export interface SourceBooks {
  shape_version: "1";
  system: string;
  fingerprint: string;
  basis: Basis;
  balances_basis: Basis;
  commodity: string;
  accounts: SourceAccount[];
  entries: SourceEntry[];
  journal_total: { debits: string; credits: string } | null;
  balances: StatedBalance[];
  rollups: StatedBalance[];
  statements: StatedStatement[];
}

/** What the export says about the company it came from, for the person to confirm. */
export interface Company {
  /** The company name every report prints above its title. */
  name: string;
  /** The method the company's own reports were run on: what it keeps its books on. */
  basis: Basis;
}

export interface Export {
  books: SourceBooks;
  company: Company;
}

const SYSTEM = "QuickBooks Online";

// QuickBooks Online exports one currency per company file and states it in none of these reports.
// Declared rather than inferred: `IMP-07` refuses a foreign amount, and that refusal is worth
// nothing if the commodity was guessed from a cell.
const COMMODITY = "USD";

// A formula whose whole body is the number it states, which is how QuickBooks writes a figure.
const LITERAL = /^-?\d+(\.\d+)?$/;

// Column positions in the Journal report, from its header row.
const DATE = 1;
const MEMO = 5;
const ACCOUNT = 6;
const DEBIT = 7;
const CREDIT = 8;
const HEADER_ROWS = 5;

const BALANCE_SHEET_SECTIONS: Record<string, AccountType | null> = {
  ASSETS: "asset",
  "LIABILITIES AND EQUITY": null,
  Liabilities: "liability",
  Equity: "equity",
};
// A profit and loss has four sections, not two. "Other Income" and "Other Expenses" carry things
// outside the trading result — interest earned, a gain on disposal — and an account under one of
// them is still income or expense.
const INCOME_STATEMENT_SECTIONS: Record<string, AccountType | null> = {
  Income: "income",
  "Other Income": "income",
  Expenses: "expense",
  "Other Expenses": "expense",
};

function at(row: Row | undefined, index: number): Cell {
  return row?.[index] ?? null;
}

/**
 * A cell as an exact decimal. **A formula that states a number is that number; any other formula
 * is refused.** A formula referencing other cells is a subtotal, and computing it would mean
 * implementing a spreadsheet — where returning zero would be worse than either, because a zero in
 * a financial figure reads as a fact.
 */
function amount(value: Cell): Big {
  if (value === null) return new Big(0);
  if (value.startsWith("=")) {
    const stated = value.slice(1).trim();
    if (!LITERAL.test(stated)) {
      throw new Refused(
        "unreadable_figure",
        `${JSON.stringify(value.slice(0, 40))} is a computed cell, not a stated figure`,
      );
    }
    return new Big(stated);
  }
  try {
    return new Big(value.trim());
  } catch {
    throw new Refused("unreadable_figure", `${JSON.stringify(value.slice(0, 40))} is not a figure`);
  }
}

/** A figure as decimal text, never in exponent notation. */
function text(figure: Big): string {
  return figure.toFixed();
}

/** A journal date, as ISO. QuickBooks prints `MM/DD/YYYY` as text. */
function asDate(value: string): string {
  const parts = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value.trim());
  const [month, day, year] = parts === null ? [] : parts.slice(1).map(Number);
  if (month === undefined || day === undefined || year === undefined) {
    throw new Refused("unreadable_figure", `${JSON.stringify(value.slice(0, 40))} is not a date`);
  }
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw new Refused("unreadable_figure", `${JSON.stringify(value)} is not a date`);
  }
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/**
 * The accounting method a report was run on, from its footer: QuickBooks prints it on the last
 * labeled row — "… - Cash Basis" or "… - Accrual Basis". A report whose basis cannot be read is
 * `unknown`, which callers must treat as unusable rather than assume.
 */
function basisOf(rows: Row[]): Basis {
  for (const row of [...rows].reverse()) {
    const label = at(row, 0);
    if (label === null) continue;
    if (label.includes("Cash Basis")) return "cash";
    if (label.includes("Accrual Basis")) return "accrual";
    break;
  }
  return "unknown";
}

/**
 * Every transaction in the journal, with its lines. A transaction begins on the row carrying a
 * date; its remaining lines carry none. Each group ends with a totals row that has amounts and no
 * account — skipped, or every transaction would count twice.
 *
 * The reference is positional because QuickBooks' journal prints no stable identifier. It
 * identifies the row in *this* export, which is what the server's idempotency key is built on.
 */
function entriesOf(rows: Row[]): SourceEntry[] {
  const entries: SourceEntry[] = [];
  let current: SourceEntry | null = null;
  let reference = 0;
  for (const row of rows.slice(HEADER_ROWS)) {
    const date = at(row, DATE);
    if (date !== null) {
      if (current !== null) entries.push(current);
      reference += 1;
      current = {
        reference: String(reference),
        transaction_date: asDate(date),
        description: at(row, MEMO) ?? "",
        lines: [],
      };
    }
    const account = at(row, ACCOUNT);
    if (account === null || current === null) continue;
    current.lines.push({
      account_code: account,
      amount: text(amount(at(row, DEBIT)).minus(amount(at(row, CREDIT)))),
      commodity: COMMODITY,
    });
  }
  if (current !== null) entries.push(current);
  return entries;
}

/**
 * Each account's type, from the source's own statement sections. An account under `ASSETS` on the
 * balance sheet is an asset; one under `Income` on the profit and loss is income. Guessing a type
 * from an account's name would put our judgment into data whose whole value is that it is not ours.
 */
function accountTypes(sheets: Map<string, Row[]>): Map<string, AccountType> {
  const types = new Map<string, AccountType>();
  for (const [member, sections] of [
    ["Balance_sheet.xlsx", BALANCE_SHEET_SECTIONS],
    ["Profit_and_loss.xlsx", INCOME_STATEMENT_SECTIONS],
  ] as const) {
    const rows = sheets.get(member);
    if (rows === undefined) continue;
    let current: AccountType | null = null;
    for (const row of rows.slice(HEADER_ROWS)) {
      const label = at(row, 0);
      if (label === null) continue;
      const name = label.trim();
      if (name in sections) {
        current = sections[name] ?? null;
        continue;
      }
      if (name.toUpperCase().startsWith("TOTAL") || name.startsWith("Gross ")) continue;
      if (current !== null && row.slice(1).some((cell) => cell !== null) && !types.has(name)) {
        types.set(name, current);
      }
    }
  }
  return types;
}

/**
 * An account's type, from the statement it appears on or from its parent's. QuickBooks prints a
 * sub-account under its bare leaf name, and requires a sub-account to share its parent's type, so
 * walking up the path is the source stating the hierarchy rather than a guess. The bare leaf is
 * tried last, because a leaf name can repeat under two parents.
 */
function typed(name: string, types: Map<string, AccountType>): AccountType {
  const parts = name.split(":");
  for (let cut = parts.length; cut > 0; cut--) {
    const stated = types.get(parts.slice(0, cut).join(":"));
    if (stated !== undefined) return stated;
  }
  return types.get(parts[parts.length - 1] ?? "") ?? "unknown";
}

/**
 * The account this one sits under, where the export has one. A parent taking no postings of its
 * own is not in the journal and so is not an account here.
 */
function parentOf(name: string, accounts: Set<string>): string {
  const parts = name.split(":");
  for (let cut = parts.length - 1; cut > 0; cut--) {
    const candidate = parts.slice(0, cut).join(":");
    if (accounts.has(candidate)) return candidate;
  }
  return "";
}

/** The account a statement row names, from its indentation: the longest posted-to suffix wins. */
function resolve(path: string[], postedTo: Set<string>): string | null {
  for (let start = 0; start < path.length; start++) {
    const candidate = path.slice(start).join(":");
    if (postedTo.has(candidate)) return candidate;
  }
  return null;
}

/**
 * One printed statement, by account. **Account paths come from the indentation**: a statement
 * indents a sub-account under its parent, and the leaf alone is ambiguous. A row matching no
 * account the journal uses is reported as unmatched rather than guessed at. Sign is left exactly
 * as the source prints it; the comparison is where conventions meet.
 */
function statement(
  rows: Row[],
  report: StatedStatement["report"],
  postedTo: Set<string>,
): StatedStatement {
  const lines: StatedBalance[] = [];
  const unmatched: string[] = [];
  const stack: [number, string][] = [];
  for (const row of rows.slice(HEADER_ROWS)) {
    const label = at(row, 0);
    if (label === null) continue;
    const name = label.trim();
    if (name === "" || name.toUpperCase().startsWith("TOTAL") || name.startsWith("Gross "))
      continue;
    if (name.includes("Basis") && name.endsWith("Basis")) continue;

    const depth = label.length - label.trimStart().length;
    while (stack.length > 0 && (stack[stack.length - 1]?.[0] ?? -1) >= depth) stack.pop();
    stack.push([depth, name]);

    if (at(row, 1) === null) continue; // a heading, or a parent carrying no figure of its own

    const code = resolve(
      stack.map(([, entry]) => entry),
      postedTo,
    );
    if (code === null) {
      unmatched.push(name);
      continue;
    }
    lines.push({ account_code: code, balance: text(amount(at(row, 1))) });
  }
  return { report, basis: basisOf(rows), lines, unmatched };
}

/**
 * What the journal says it sums to, from its own TOTAL row: **the only figure in the export
 * carrying no accounting basis**, because the journal is the record rather than a view of it
 * (ADR-0050). Read rather than computed; its value is that QuickBooks produced it.
 */
function journalTotal(rows: Row[]): SourceBooks["journal_total"] {
  for (const row of [...rows].reverse()) {
    const label = at(row, 0);
    if (label === null || label.trim().toUpperCase() !== "TOTAL") continue;
    return { debits: text(amount(at(row, DEBIT))), credits: text(amount(at(row, CREDIT))) };
  }
  return null;
}

/**
 * The general ledger's own stated totals — the source's balances, which `IMP-08` reconciles
 * against — split from the rollups. A "Total for X with sub-accounts", or a bare "Total for X"
 * where the journal posts beneath X and never to X itself, is a subtotal over a parent and its
 * children; comparing it against a chart account would manufacture a divergence.
 */
function ledgerTotals(
  rows: Row[],
  postedTo: Set<string>,
): [StatedBalance[], StatedBalance[], Basis] {
  const balances: StatedBalance[] = [];
  const rollups: StatedBalance[] = [];
  for (const row of rows.slice(HEADER_ROWS)) {
    const label = at(row, 0);
    if (label === null || !label.startsWith("Total for ")) continue;
    const account = label.slice("Total for ".length).trim();
    const parent = account.endsWith(" with sub-accounts")
      ? account.slice(0, -" with sub-accounts".length)
      : account;
    const stated = {
      account_code: parent,
      balance: text(amount(at(row, DEBIT)).minus(amount(at(row, CREDIT)))),
    };
    const hasChildren = [...postedTo].some((code) => code.startsWith(parent + ":"));
    if (account !== parent || (hasChildren && !postedTo.has(parent))) rollups.push(stated);
    else balances.push(stated);
  }
  return [balances, rollups, basisOf(rows)];
}

async function fingerprint(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as Uint8Array<ArrayBuffer>);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * One QuickBooks export, as the neutral interchange shape and what it says about the company.
 *
 * The general ledger's own per-account totals are the oracle, not the trial balance. Every
 * *report* carries its accounting method in its footer; `Journal.xlsx` carries none, because it is
 * the raw record. A cash-basis general ledger beside an accrual journal is routine, which ADR-0037
 * predicts and `IMP-08` reports rather than tolerates.
 */
export async function read(archive: Uint8Array): Promise<Export> {
  if (archive.length > MAX_ARCHIVE_BYTES) {
    throw new Refused(
      "import_too_large",
      `the archive is ${archive.length} bytes; this reads at most ${MAX_ARCHIVE_BYTES}`,
    );
  }
  const exported = new Zip(archive);
  const sheets = new Map<string, Row[]>();
  for (const member of [
    "Journal.xlsx",
    "General_ledger.xlsx",
    "Balance_sheet.xlsx",
    "Profit_and_loss.xlsx",
  ]) {
    if (!exported.has(member)) continue;
    sheets.set(member, await sheetRows(new Zip(await exported.read(member))));
  }
  const journal = sheets.get("Journal.xlsx");
  if (journal === undefined)
    throw new Refused("import_refused", "the export carries no Journal.xlsx to read");

  const entries = entriesOf(journal);
  const postedTo = new Set(
    entries.flatMap((entry) => entry.lines.map((line) => line.account_code)),
  );
  const used = [...postedTo].sort();
  const types = accountTypes(sheets);

  const ledger = sheets.get("General_ledger.xlsx");
  const [balances, rollups, balancesBasis] =
    ledger === undefined ? [[], [], "unknown" as const] : ledgerTotals(ledger, postedTo);

  const statements: StatedStatement[] = [];
  for (const [member, report] of [
    ["Profit_and_loss.xlsx", "profit_and_loss"],
    ["Balance_sheet.xlsx", "balance_sheet"],
  ] as const) {
    const rows = sheets.get(member);
    if (rows !== undefined) statements.push(statement(rows, report, postedTo));
  }

  return {
    books: {
      shape_version: "1",
      system: SYSTEM,
      // Over the archive bytes, so re-reading the same export yields the same identity: the
      // server derives each entry's idempotency key from it and the row's reference, which is
      // what makes an import replayable rather than duplicable (ADR-0029).
      fingerprint: await fingerprint(archive),
      basis: basisOf(journal),
      balances_basis: balancesBasis,
      commodity: COMMODITY,
      accounts: used.map((name) => ({
        code: name,
        name,
        account_type: typed(name, types),
        parent: parentOf(name, postedTo),
      })),
      entries,
      journal_total: journalTotal(journal),
      balances,
      rollups,
      statements,
    },
    company: {
      name: (at(journal[0], 0) ?? "").trim(),
      basis: statements.find((stated) => stated.basis !== "unknown")?.basis ?? "unknown",
    },
  };
}
