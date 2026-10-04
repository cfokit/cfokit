/**
 * A synthetic QuickBooks Online export, written here so the reader's expected values are known
 * from the rows below before it runs rather than read back from a first run (ADR-0036 § 5).
 *
 * The workbooks are written the way QuickBooks writes them: strings in a shared table, figures in
 * the statements as formulas with no cached result, and a blank row left out of the XML.
 */

/** A figure stored as a number cell, written as the digits the workbook holds. */
export interface NumberCell {
  number: string;
}
export type SyntheticCell = string | NumberCell | null;
export type SyntheticRows = SyntheticCell[][];

const n = (digits: string): NumberCell => ({ number: digits });

// Three title rows, a blank, a header row, then the body — the shape every QuickBooks report has,
// and the reason the reader skips exactly five rows.
const HEADER = [
  null,
  "Date",
  "Transaction Type",
  "Num",
  "Name",
  "Memo/Description",
  "Account",
  "Debit",
  "Credit",
];

export const JOURNAL: SyntheticRows = [
  ["Synthetic Co"],
  ["Journal"],
  ["All Dates"],
  [],
  HEADER,
  [
    null,
    "01/15/2026",
    "Invoice",
    "1001",
    "A Client",
    "Consulting",
    "Accounts Receivable",
    n("1200.00"),
    null,
  ],
  [null, null, null, null, null, "Consulting", "Income:Consulting", null, n("1200.00")],
  [null, null, null, null, null, null, null, n("1200.00"), n("1200.00")], // totals row: skipped
  [null, "02/02/2026", "Expense", null, null, "Coffee", "Meals:Client Meals", n("12.50"), null],
  [null, null, null, null, null, "Coffee", "Checking", null, n("12.50")],
  [null, null, null, null, null, null, null, n("12.50"), n("12.50")],
  // The grand total the journal prints for itself, above its footer. It carries no accounting
  // basis, because a journal is the record rather than a view of one (ADR-0050).
  ["TOTAL", null, null, null, null, null, null, n("1212.50"), n("1212.50")],
  ["Saturday, Sep 05, 2026 07:31:11 AM GMT-7"],
];

export const PROFIT_AND_LOSS: SyntheticRows = [
  ["Synthetic Co"],
  ["Profit and Loss"],
  ["All Dates"],
  [],
  [null, "Total"],
  ["Income", null],
  ["   Consulting", "=1200.00"],
  ["Total Income", "=1200.00"],
  ["Expenses", null],
  ["   Meals", null],
  ["      Client Meals", "=12.50"],
  ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis"],
];

export const BALANCE_SHEET: SyntheticRows = [
  ["Synthetic Co"],
  ["Balance Sheet"],
  ["All Dates"],
  [],
  [null, "Total"],
  ["ASSETS", null],
  ["   Checking", "=-12.50"],
  ["   Accounts Receivable", "=1200.00"],
  ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis"],
];

export const GENERAL_LEDGER: SyntheticRows = [
  ["Synthetic Co"],
  ["General Ledger"],
  ["All Dates"],
  [],
  HEADER,
  ["Total for Accounts Receivable", null, null, null, null, null, null, n("1200.00"), null],
  ["Total for Income:Consulting", null, null, null, null, null, null, null, n("1200.00")],
  ["Total for Meals with sub-accounts", null, null, null, null, null, null, n("12.50"), null],
  ["Total for Checking", null, null, null, null, null, null, null, n("12.50")],
  ["Saturday, Sep 05, 2026 07:31:07 AM GMT-7 - Cash Basis"],
];

const escape = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function columnName(index: number): string {
  let name = "";
  for (let at = index + 1; at > 0; at = Math.floor((at - 1) / 26)) {
    name = String.fromCharCode(65 + ((at - 1) % 26)) + name;
  }
  return name;
}

/** One workbook, as QuickBooks writes it. */
export async function workbook(rows: SyntheticRows): Promise<Uint8Array> {
  const strings: string[] = [];
  const body = rows
    .map((row, r) => {
      const cells = row
        .map((cell, c) => {
          const ref = `${columnName(c)}${r + 1}`;
          if (cell === null) return "";
          if (typeof cell === "object") return `<c r="${ref}"><v>${cell.number}</v></c>`;
          if (cell.startsWith("=")) return `<c r="${ref}"><f>${escape(cell.slice(1))}</f></c>`;
          strings.push(cell);
          return `<c r="${ref}" t="s"><v>${strings.length - 1}</v></c>`;
        })
        .join("");
      // A row holding nothing is left out, as a real worksheet leaves it out.
      return cells === "" ? "" : `<row r="${r + 1}">${cells}</row>`;
    })
    .join("");
  const ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
  const rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';
  return zip({
    "xl/workbook.xml": `<?xml version="1.0"?><workbook ${ns} ${rel}><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    "xl/_rels/workbook.xml.rels": `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>`,
    "xl/sharedStrings.xml": `<?xml version="1.0"?><sst ${ns}>${strings
      .map((text) => `<si><t xml:space="preserve">${escape(text)}</t></si>`)
      .join("")}</sst>`,
    "xl/worksheets/sheet1.xml": `<?xml version="1.0"?><worksheet ${ns}><sheetData>${body}</sheetData></worksheet>`,
  });
}

/** The whole export, with any report replaced, or left out where it is given as `null`. */
export async function syntheticExport(
  replace: Record<string, SyntheticRows | null> = {},
): Promise<Uint8Array> {
  const reports: Record<string, SyntheticRows | null> = {
    "Journal.xlsx": JOURNAL,
    "General_ledger.xlsx": GENERAL_LEDGER,
    "Balance_sheet.xlsx": BALANCE_SHEET,
    "Profit_and_loss.xlsx": PROFIT_AND_LOSS,
    ...replace,
  };
  const members: Record<string, Uint8Array> = {};
  for (const [name, rows] of Object.entries(reports)) {
    if (rows !== null) members[name] = await workbook(rows);
  }
  return zip(members);
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = (CRC_TABLE[(crc ^ byte) & 0xff] ?? 0) ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

async function deflate(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes as Uint8Array<ArrayBuffer>])
    .stream()
    .pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** A zip archive of these members, deflated. */
export async function zip(members: Record<string, string | Uint8Array>): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const locals: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const [name, content] of Object.entries(members)) {
    const raw = typeof content === "string" ? encoder.encode(content) : content;
    const data = await deflate(raw);
    const nameBytes = encoder.encode(name);
    const crc = crc32(raw);

    const local = new Uint8Array(30 + nameBytes.length + data.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(8, 8, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, data.length, true);
    lv.setUint32(22, raw.length, true);
    lv.setUint16(26, nameBytes.length, true);
    local.set(nameBytes, 30);
    local.set(data, 30 + nameBytes.length);

    const entry = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(entry.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(10, 8, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, data.length, true);
    cv.setUint32(24, raw.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(42, offset, true);
    entry.set(nameBytes, 46);

    locals.push(local);
    central.push(entry);
    offset += local.length;
  }
  const directorySize = central.reduce((sum, entry) => sum + entry.length, 0);
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, central.length, true);
  ev.setUint16(10, central.length, true);
  ev.setUint32(12, directorySize, true);
  ev.setUint32(16, offset, true);

  const out = new Uint8Array(offset + directorySize + end.length);
  let at = 0;
  for (const part of [...locals, ...central, end]) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}
