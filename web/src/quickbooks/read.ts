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
// The general ledger's own: its running balance, on the account's natural side.
const BALANCE = 9;
const HEADER_ROWS = 5;

// The reports read, each found by its name wherever the archive keeps it: at the root as Export
// Data writes it, or under the one folder an archive made by zipping the folder adds.
const REPORTS = [
  "Journal.xlsx",
  "General_ledger.xlsx",
  "Balance_sheet.xlsx",
  "Profit_and_loss.xlsx",
] as const;

// What a statement works out from the accounts above it and prints as a line of its own.
const COMPUTED = new Set([
  "Gross Profit",
  "Net Operating Income",
  "Net Other Income",
  "Net Income",
]);

// The types whose balance is a credit, which a ledger's running balance prints positive.
const CREDIT_NATURE = new Set<AccountType>(["liability", "equity", "income"]);

// Each section, with the type it states and the indentation it is printed at: an account may
// share a section's name, and is told from it by where it sits.
type Sections = Record<string, [AccountType | null, number]>;

const BALANCE_SHEET_SECTIONS: Sections = {
  ASSETS: ["asset", 0],
  "LIABILITIES AND EQUITY": [null, 0],
  Liabilities: ["liability", 3],
  Equity: ["equity", 3],
};
// A profit and loss has five sections, not two. "Cost of Goods Sold" is what the income cost to
// earn, and "Other Income" and "Other Expenses" carry things outside the trading result — interest
// earned, a gain on disposal — and an account under any of them is still income or expense.
const INCOME_STATEMENT_SECTIONS: Sections = {
  Income: ["income", 0],
  "Cost of Goods Sold": ["expense", 0],
  "Other Income": ["income", 0],
  Expenses: ["expense", 0],
  "Other Expenses": ["expense", 0],
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
  // QuickBooks fills an indented total's empty amount with its indentation.
  if (value === null || value.trim() === "") return new Big(0);
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
 *
 * A transaction's description is the first memo it carries. QuickBooks prints a memo on each
 * line rather than one for the transaction, and its first row's is usually blank: a journal
 * entry's memo is on its lines, and a sale's on the line that names what was sold.
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
        description: "",
        lines: [],
      };
    }
    const memo = at(row, MEMO);
    if (current !== null && current.description === "" && memo !== null) current.description = memo;
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

/** A statement row naming something, with the path its indentation puts it on. */
interface Printed {
  name: string;
  /** The labels of the rows it is indented under, outermost first, then its own. */
  path: string[];
  /** The type of the section it is in, where its section states one. */
  section: AccountType | null;
  figure: Cell;
}

/**
 * A statement's rows by indentation. A statement indents each row under the heading it belongs
 * to, and closes each heading with "Total" and the heading's own label, at its indentation: that
 * is how a total is told from an account whose name begins with the word. Section headings are
 * left out; every other heading is kept, because a parent account is one.
 */
function printed(rows: Row[], sections: Sections): Printed[] {
  const out: Printed[] = [];
  const open: [number, string][] = [];
  for (const row of rows.slice(HEADER_ROWS)) {
    const label = at(row, 0);
    if (label === null || label.trim() === "") continue;
    const name = label.trim();
    const depth = label.length - label.trimStart().length;
    while (open.length > 0 && (open[open.length - 1]?.[0] ?? -1) > depth) open.pop();
    const top = open[open.length - 1];
    if (top?.[0] === depth) {
      open.pop();
      if (name.toUpperCase() === `TOTAL ${top[1]}`.toUpperCase()) continue;
    }
    open.push([depth, name]);
    const heading = ([indent, label]: [number, string]) => sections[label]?.[1] === indent;
    if (heading([depth, name])) continue;
    const section = open.findLast(heading);
    out.push({
      name,
      path: open.map(([, label]) => label),
      section: section === undefined ? null : (sections[section[1]]?.[0] ?? null),
      figure: at(row, 1),
    });
  }
  return out;
}

/**
 * Each account's type, from the source's own statement sections. An account under `ASSETS` on the
 * balance sheet is an asset; one under `Income` on the profit and loss is income. Guessing a type
 * from an account's name would put our judgment into data whose whole value is that it is not ours.
 */
function accountTypes(sheets: Map<string, Row[]>, accounts: Set<string>): Map<string, AccountType> {
  const types = new Map<string, AccountType>();
  for (const [member, sections] of [
    ["Balance_sheet.xlsx", BALANCE_SHEET_SECTIONS],
    ["Profit_and_loss.xlsx", INCOME_STATEMENT_SECTIONS],
  ] as const) {
    const rows = sheets.get(member);
    if (rows === undefined) continue;
    for (const { path, section } of printed(rows, sections)) {
      const code = resolve(path, accounts);
      if (code !== null && section !== null && !types.has(code)) types.set(code, section);
    }
  }
  return types;
}

/**
 * An account's type, from the statement it appears on or from its parent's. QuickBooks requires a
 * sub-account to share its parent's type, so walking up the path is the source stating the
 * hierarchy rather than a guess.
 */
function typed(name: string, types: Map<string, AccountType>): AccountType {
  const parts = name.split(":");
  for (let cut = parts.length; cut > 0; cut--) {
    const stated = types.get(parts.slice(0, cut).join(":"));
    if (stated !== undefined) return stated;
  }
  return "unknown";
}

/** The account this one sits under, where it has one. */
function parentOf(name: string, accounts: Set<string>): string {
  const parts = name.split(":");
  for (let cut = parts.length - 1; cut > 0; cut--) {
    const candidate = parts.slice(0, cut).join(":");
    if (accounts.has(candidate)) return candidate;
  }
  return "";
}

/** The account a statement row names, from its indentation: the longest known suffix wins. */
function resolve(path: string[], accounts: Set<string>): string | null {
  for (let start = 0; start < path.length; start++) {
    const candidate = path.slice(start).join(":");
    if (accounts.has(candidate)) return candidate;
  }
  return null;
}

/**
 * What the general ledger shows of the accounts: how each entry names its account against the
 * headings above it, and each account it lists entries under or opens with a beginning balance.
 * An entry names its account by its full path; the headings name each account on that path by
 * its own label, indented under its parent's, as the statements do. With account numbers shown
 * the two differ — an entry puts the account's own number once in front of its path of names, a
 * heading puts each account's in front of its name — so the headings' path is the one an account
 * is known by here. A ledger run from a start date opens an account with nothing in its range
 * with a beginning balance; on a cash basis it lists accounts only that basis has.
 */
function ledgerAccounts(ledger: Row[] | undefined): {
  paths: Map<string, string>;
  listed: string[];
} {
  const paths = new Map<string, string>();
  const listed: string[] = [];
  const open: string[] = [];
  for (const row of ledger?.slice(HEADER_ROWS) ?? []) {
    const label = at(row, 0);
    const account = at(row, ACCOUNT);
    if (label !== null && !label.trim().startsWith("Total for ")) {
      open.length = Math.floor((label.length - label.trimStart().length) / 3);
      open.push(label.trim());
    } else if (label === null && account !== null) {
      paths.set(account, open.join(":"));
      listed.push(open.join(":"));
    } else if (label === null && at(row, DATE)?.trim() === "Beginning Balance") {
      listed.push(open.join(":"));
    }
  }
  return { paths, listed };
}

/**
 * Every account the export shows, and each account above one of them. QuickBooks allows no colon
 * in a name, so every parent on a path is an account.
 */
function accountsOf(named: string[]): Set<string> {
  const accounts = new Set<string>();
  for (const name of named) {
    const parts = name.split(":");
    for (let cut = 1; cut <= parts.length; cut++) accounts.add(parts.slice(0, cut).join(":"));
  }
  return accounts;
}

/** An account as CFOKit's chart holds it. */
interface Charted {
  code: string;
  name: string;
}

/**
 * Each account's code and name. Without account numbers, both are its path. With them, its code
 * is its own number and its name its path of names, as a full path in the export prints them
 * after the number: `6211`, named `Office Expenses:Software:Design Tools`.
 *
 * **Numbers are read only where the export proves them.** They are shown when an entry's full
 * path differs from its headings' path, and each heading is then a number and a name — except
 * QuickBooks' own accounts, which have no number. Every account an entry names is checked: its
 * number, if it has one, then its path of names, must be exactly what the entry printed. If any
 * is not, the numbers are not as this reads them, and every account keeps its path.
 */
function chart(accounts: Set<string>, paths: Map<string, string>): Map<string, Charted> {
  const asPrinted = new Map([...accounts].map((path) => [path, { code: path, name: path }]));
  if (![...paths].some(([full, path]) => full !== path)) return asPrinted;

  const split = (label: string) => /^(\d+) (.+)$/.exec(label)?.slice(1) ?? [null, label];
  const charted = new Map<string, Charted>();
  for (const path of accounts) {
    const labels = path.split(":").map(split);
    const number = labels[labels.length - 1]?.[0] ?? null;
    const name = labels.map(([, own]) => own).join(":");
    charted.set(path, { code: number ?? name, name });
  }
  for (const [full, path] of paths) {
    const account = charted.get(path);
    if (account === undefined) continue;
    const printed =
      account.code === account.name ? account.name : `${account.code} ${account.name}`;
    if (printed !== full) return asPrinted;
  }
  return charted;
}

/**
 * One printed statement, by account. **Account paths come from the indentation**: a statement
 * indents a sub-account under its parent, and the leaf alone is ambiguous. A row with a figure
 * that matches no account is reported as unmatched rather than guessed at, unless it is one of
 * the lines a statement computes. Sign is left exactly as the source prints it; the comparison is
 * where conventions meet.
 */
function statement(
  rows: Row[],
  report: StatedStatement["report"],
  sections: Sections,
  accounts: Set<string>,
): StatedStatement {
  const lines: StatedBalance[] = [];
  const unmatched: string[] = [];
  for (const { name, path, figure } of printed(rows, sections)) {
    if (figure === null) continue; // a heading, or a parent carrying no figure of its own
    const code = resolve(path, accounts);
    if (code !== null) lines.push({ account_code: code, balance: text(amount(figure)) });
    else if (!COMPUTED.has(name)) unmatched.push(name);
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
 * The general ledger's own stated balances — the source's, which `IMP-08` reconciles against —
 * split from the rollups. The ledger names each account by its leaf, indented under its parent,
 * and closes it with "Total for" the leaf. A parent's own entries are totalled one level in from
 * the parent; "Total for X with sub-accounts" (or "with subs"), or a bare "Total for X" over a
 * parent with no entries of its own, is a subtotal over a parent and its children, and comparing
 * it against a chart account would manufacture a divergence.
 *
 * A balance is the account's at the ledger's end: the total's debits less its credits, and the
 * beginning balance a ledger run from a start date prints, which is on the account's natural
 * side. A ledger over all dates prints none.
 */
function ledgerTotals(
  rows: Row[],
  accounts: Set<string>,
  types: Map<string, AccountType>,
): [StatedBalance[], StatedBalance[], Basis] {
  const balances: StatedBalance[] = [];
  const rollups: StatedBalance[] = [];
  const open: string[] = [];
  const openings = new Map<string, Big>();
  for (const row of rows.slice(HEADER_ROWS)) {
    const label = at(row, 0);
    if (label === null) {
      if (at(row, DATE)?.trim() === "Beginning Balance") {
        const code = open.join(":");
        const natural = amount(at(row, BALANCE));
        openings.set(code, CREDIT_NATURE.has(typed(code, types)) ? natural.times(-1) : natural);
      }
      continue;
    }
    const level = Math.floor((label.length - label.trimStart().length) / 3);
    const name = label.trim();
    if (!name.startsWith("Total for ")) {
      open.length = level;
      open.push(name);
      continue;
    }
    // "with subs" where account numbers are shown, as the one numbered export printed it.
    const suffix = [" with sub-accounts", " with subs"].find((ending) => name.endsWith(ending));
    const subtotal = suffix !== undefined;
    const leaf = name.slice("Total for ".length, subtotal ? -suffix.length : undefined);
    const own = open[level] === leaf ? level : open[level - 1] === leaf ? level - 1 : -1;
    if (own < 0) {
      throw new Refused(
        "unreadable_figure",
        `the general ledger's ${JSON.stringify(name)} closes no account it opened`,
      );
    }
    const code = open.slice(0, own + 1).join(":");
    const parent = own === level && [...accounts].some((other) => other.startsWith(code + ":"));
    let balance = amount(at(row, DEBIT)).minus(amount(at(row, CREDIT)));
    for (const [opened, figure] of openings) {
      if (opened === code || ((subtotal || parent) && opened.startsWith(code + ":"))) {
        balance = balance.plus(figure);
      }
    }
    (subtotal || parent ? rollups : balances).push({ account_code: code, balance: text(balance) });
    if (own === level) open.length = level;
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
  const found = new Map<string, string>();
  for (const member of exported.names()) {
    const report = REPORTS.find((name) => member === name || member.endsWith("/" + name));
    if (report === undefined || member.split("/").length > 2) continue;
    if (found.has(report)) {
      throw new Refused("import_refused", `the archive carries ${report} more than once`);
    }
    found.set(report, member);
  }
  const sheets = new Map<string, Row[]>();
  for (const [report, member] of found) {
    sheets.set(report, await sheetRows(new Zip(await exported.read(member))));
  }
  const journal = sheets.get("Journal.xlsx");
  if (journal === undefined)
    throw new Refused("import_refused", "the export carries no Journal.xlsx to read");

  const entries = entriesOf(journal);
  const ledger = sheets.get("General_ledger.xlsx");
  const { paths, listed } = ledgerAccounts(ledger);
  // Every account by the path its headings give it, the statements' and the ledger's own.
  for (const entry of entries) {
    for (const line of entry.lines)
      line.account_code = paths.get(line.account_code) ?? line.account_code;
  }
  const accounts = accountsOf([
    ...entries.flatMap((entry) => entry.lines.map((line) => line.account_code)),
    ...listed,
  ]);
  const types = accountTypes(sheets, accounts);

  const [balances, rollups, balancesBasis] =
    ledger === undefined ? [[], [], "unknown" as const] : ledgerTotals(ledger, accounts, types);

  const statements: StatedStatement[] = [];
  for (const [member, report, sections] of [
    ["Profit_and_loss.xlsx", "profit_and_loss", INCOME_STATEMENT_SECTIONS],
    ["Balance_sheet.xlsx", "balance_sheet", BALANCE_SHEET_SECTIONS],
  ] as const) {
    const rows = sheets.get(member);
    if (rows !== undefined) statements.push(statement(rows, report, sections, accounts));
  }

  // Then as CFOKit's chart holds it: by number where the export shows numbers.
  const charted = chart(accounts, paths);
  const code = (path: string) => charted.get(path)?.code ?? path;
  const coded = (stated: StatedBalance) => ({ ...stated, account_code: code(stated.account_code) });

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
      accounts: [...accounts].sort().map((path) => {
        const parent = parentOf(path, accounts);
        return {
          code: code(path),
          name: charted.get(path)?.name ?? path,
          account_type: typed(path, types),
          parent: parent === "" ? "" : code(parent),
        };
      }),
      entries: entries.map((entry) => ({
        ...entry,
        lines: entry.lines.map((line) => ({ ...line, account_code: code(line.account_code) })),
      })),
      journal_total: journalTotal(journal),
      balances: balances.map(coded),
      rollups: rollups.map(coded),
      statements: statements.map((stated) => ({ ...stated, lines: stated.lines.map(coded) })),
    },
    company: {
      name: (at(journal[0], 0) ?? "").trim(),
      basis: statements.find((stated) => stated.basis !== "unknown")?.basis ?? "unknown",
    },
  };
}
