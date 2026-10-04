// @vitest-environment node
/**
 * The QuickBooks reader against the synthetic export (ADR-0036 layer 3). Every expected value
 * comes from the rows `synthetic.ts` writes — its transactions are 1,200.00 and 12.50 — never from
 * a first run of the reader.
 */
import Big from "big.js";
import { read, type Export, type SourceBooks } from "./read";
import { Refused } from "./refused";
import { JOURNAL, PROFIT_AND_LOSS, syntheticExport, zip } from "./synthetic";

let books: SourceBooks;
let company: Export["company"];

beforeAll(async () => {
  ({ books, company } = await read(await syntheticExport()));
});

const same = (a: string, b: string) => new Big(a).eq(new Big(b));

async function refusal(archive: Uint8Array): Promise<Refused> {
  try {
    await read(archive);
  } catch (error) {
    if (error instanceof Refused) return error;
    throw error;
  }
  throw new Error("the export was read");
}

describe("the shape", () => {
  test("it is the published shape", () => {
    expect(books.shape_version).toBe("1");
    expect(books.system).toBe("QuickBooks Online");
    expect(books.commodity).toBe("USD");
    expect(Object.keys(books).sort()).toEqual(
      [
        "shape_version",
        "system",
        "fingerprint",
        "basis",
        "balances_basis",
        "commodity",
        "accounts",
        "entries",
        "balances",
        "rollups",
        "statements",
        "journal_total",
      ].sort(),
    );
  });

  test("the fingerprint is the archive's SHA-256, so the same file names the same import", async () => {
    const again = await read(await syntheticExport());
    expect(books.fingerprint).toMatch(/^[0-9a-f]{64}$/);
    expect(again.books.fingerprint).toBe(books.fingerprint);
  });

  test("every amount is a string", () => {
    for (const entry of books.entries)
      for (const line of entry.lines) expect(typeof line.amount).toBe("string");
    for (const stated of [...books.balances, ...books.rollups])
      expect(typeof stated.balance).toBe("string");
  });

  test("the company is named as its reports name it, on the basis its reports were run", () => {
    expect(company).toEqual({ name: "Synthetic Co", basis: "accrual" });
  });
});

describe("the journal", () => {
  test("its total is read from its own TOTAL row, not summed (ADR-0050)", () => {
    expect(books.journal_total).not.toBeNull();
    expect(same(books.journal_total?.debits ?? "", "1212.50")).toBe(true);
    expect(same(books.journal_total?.credits ?? "", "1212.50")).toBe(true);
  });

  test("a journal printing no total reports none, never a fabricated one", async () => {
    const without = JOURNAL.filter((row) => row[0] !== "TOTAL");
    const { books: read_ } = await read(await syntheticExport({ "Journal.xlsx": without }));
    expect(read_.journal_total).toBeNull();
  });

  test("the journal states no basis and the general ledger states cash", () => {
    expect(books.basis).toBe("unknown");
    expect(books.balances_basis).toBe("cash");
  });

  test("a transaction is grouped by the row carrying its date", () => {
    expect(books.entries.map((entry) => entry.transaction_date)).toEqual([
      "2026-01-15",
      "2026-02-02",
    ]);
    expect(books.entries.map((entry) => entry.lines.length)).toEqual([2, 2]);
  });

  test("the totals row inside each transaction is skipped", () => {
    expect(books.entries.reduce((sum, entry) => sum + entry.lines.length, 0)).toBe(4);
  });

  test("a debit is positive and a credit negative", () => {
    const lines = Object.fromEntries(
      books.entries[0]?.lines.map((line) => [line.account_code, line.amount]) ?? [],
    );
    expect(Object.keys(lines).sort()).toEqual(["Accounts Receivable", "Income:Consulting"]);
    expect(same(lines["Accounts Receivable"] ?? "", "1200.00")).toBe(true);
    expect(same(lines["Income:Consulting"] ?? "", "-1200.00")).toBe(true);
  });

  test("every transaction balances", () => {
    for (const entry of books.entries) {
      const sum = entry.lines.reduce((total, line) => total.plus(line.amount), new Big(0));
      expect(sum.eq(0)).toBe(true);
    }
  });

  test("a blank row left out of the XML does not shift the body", () => {
    expect(books.entries[0]?.transaction_date).toBe("2026-01-15");
    expect(books.entries).toHaveLength(2);
  });

  test("references are positional and stable", () => {
    expect(books.entries.map((entry) => entry.reference)).toEqual(["1", "2"]);
  });
});

describe("account types and paths", () => {
  const typeOf = (code: string) =>
    books.accounts.find((account) => account.code === code)?.account_type;

  test("types come from the source's own statement sections", () => {
    expect(typeOf("Accounts Receivable")).toBe("asset");
    expect(typeOf("Checking")).toBe("asset");
    expect(typeOf("Income:Consulting")).toBe("income");
  });

  test("a sub-account takes its parent's type", () => {
    expect(typeOf("Meals:Client Meals")).toBe("expense");
  });

  test("a parent that takes no postings is not an account", () => {
    expect(books.accounts.map((account) => account.code)).not.toContain("Meals");
    expect(books.accounts[0]?.parent).toBe("");
  });
});

describe("the statements", () => {
  const profit = () => books.statements.find((stated) => stated.report === "profit_and_loss");
  const figure = (code: string) =>
    profit()?.lines.find((line) => line.account_code === code)?.balance ?? "";

  test("a formula stating a number is that number", () => {
    expect(same(figure("Income:Consulting"), "1200.00")).toBe(true);
    expect(same(figure("Meals:Client Meals"), "12.50")).toBe(true);
  });

  test("a statement's path comes from its indentation", () => {
    expect(profit()?.lines.map((line) => line.account_code)).toContain("Meals:Client Meals");
  });

  test("a statement keeps the sign the source prints", () => {
    expect(new Big(figure("Income:Consulting")).gt(0)).toBe(true);
  });

  test("a subtotal is a rollup, not a balance", () => {
    expect(books.rollups.map((stated) => stated.account_code)).toEqual(["Meals"]);
    expect(books.balances.map((stated) => stated.account_code)).not.toContain("Meals");
  });

  test("the general ledger's totals are read as the source's own balances", () => {
    const stated = Object.fromEntries(
      books.balances.map((line) => [line.account_code, line.balance]),
    );
    expect(Object.keys(stated).sort()).toEqual([
      "Accounts Receivable",
      "Checking",
      "Income:Consulting",
    ]);
    expect(same(stated["Accounts Receivable"] ?? "", "1200.00")).toBe(true);
    expect(same(stated["Income:Consulting"] ?? "", "-1200.00")).toBe(true);
    expect(same(stated.Checking ?? "", "-12.50")).toBe(true);
  });
});

describe("refusals", () => {
  test("a computed cell is refused rather than read as zero", async () => {
    const broken = [
      ...PROFIT_AND_LOSS.slice(0, 6),
      ["   Consulting", "=SUM(B7:B9)"],
      ...PROFIT_AND_LOSS.slice(7),
    ];
    expect((await refusal(await syntheticExport({ "Profit_and_loss.xlsx": broken }))).code).toBe(
      "unreadable_figure",
    );
  });

  test("an export with no journal is refused", async () => {
    expect((await refusal(await syntheticExport({ "Journal.xlsx": null }))).code).toBe(
      "import_refused",
    );
  });

  test("a document type declaration is refused", async () => {
    const hostile = await zip({
      "xl/workbook.xml": '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><workbook/>',
      "xl/worksheets/sheet1.xml": "<sheetData/>",
    });
    const error = await refusal(await zip({ "Journal.xlsx": hostile }));
    expect(error.message).toContain("document type");
  });

  test("an archive expanding past the ceiling is refused, even where its directory understates it", async () => {
    const bomb = await zip({ "Journal.xlsx": new Uint8Array(300 * 1024 * 1024 + 1) });
    expect((await refusal(bomb)).message).toContain("declares");

    // The sizes an archive states are claims by whoever built it: state one byte, deliver 300 MB.
    const view = new DataView(bomb.buffer, bomb.byteOffset, bomb.byteLength);
    const central = bomb.length - 22 - (46 + "Journal.xlsx".length);
    view.setUint32(22, 1, true);
    view.setUint32(central + 24, 1, true);
    const understated = await refusal(bomb);
    expect(understated.code).toBe("import_too_large");
    expect(understated.message).toContain("understated");
  });

  test("an archive with too many members is refused", async () => {
    const members = Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`m${i}.txt`, "x"]));
    expect((await refusal(await zip(members))).code).toBe("import_too_large");
  });

  test("a file that is not a zip is refused", async () => {
    expect((await refusal(new TextEncoder().encode("not an archive"))).code).toBe(
      "unreadable_archive",
    );
  });
});
