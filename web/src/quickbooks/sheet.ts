/**
 * A workbook's first worksheet as rows of cell values, without a spreadsheet library. An `.xlsx`
 * is a zip of XML, so the zip and XML readers beside this are the whole requirement.
 */

import { Refused } from "./refused";
import { descendants, parse, textOf, type Element } from "./xml";
import type { Zip } from "./zip";

/**
 * `null` for an empty cell, the text for a string, `"=…"` for a formula, and the *raw digits* for
 * a number — never a JavaScript number. QuickBooks writes every figure in the statement reports as
 * a formula with no cached result, so a reader asking for cached values would get a zero for each
 * of them; and a figure that went through a float would no longer be the one the workbook shows.
 */
export type Cell = string | null;
export type Row = Cell[];

/** `C` from `C7`, as a zero-based index. */
function column(reference: string): number {
  let index = 0;
  for (const char of reference) {
    if (!/[A-Za-z]/.test(char)) break;
    index = index * 26 + (char.toUpperCase().charCodeAt(0) - 64);
  }
  return index - 1;
}

/**
 * The workbook's string table. Each `<si>` may hold one `<t>` or several inside `<r>` runs; the
 * value is all of them joined. Leading whitespace is load-bearing — a statement's indentation is
 * how a sub-account's path is recovered — so the text is kept exactly.
 */
async function sharedStrings(workbook: Zip): Promise<string[]> {
  if (!workbook.has("xl/sharedStrings.xml")) return [];
  const root = parse(await workbook.read("xl/sharedStrings.xml"));
  return root.children.filter((item) => item.name === "si").map((item) => textOf(item, "t"));
}

/** The path of the workbook's first worksheet, resolved through its relationships. */
async function firstSheet(workbook: Zip): Promise<string> {
  const book = parse(await workbook.read("xl/workbook.xml"));
  const sheet = [...descendants(book)].find((node) => node.name === "sheet");
  if (sheet === undefined)
    throw new Refused("unreadable_figure", "the workbook declares no worksheet");
  const relationship = sheet.attributes.id;
  if (relationship !== undefined && workbook.has("xl/_rels/workbook.xml.rels")) {
    const rels = parse(await workbook.read("xl/_rels/workbook.xml.rels"));
    const target = rels.children.find((node) => node.attributes.Id === relationship)?.attributes
      .Target;
    if (target !== undefined) return "xl/" + target.replace(/^\/+/, "").replace(/^xl\//, "");
  }
  return "xl/worksheets/sheet1.xml";
}

function child(element: Element, name: string): Element | undefined {
  return element.children.find((node) => node.name === name);
}

export async function rows(workbook: Zip): Promise<Row[]> {
  const strings = await sharedStrings(workbook);
  const sheet = parse(await workbook.read(await firstSheet(workbook)));

  const out: Row[] = [];
  for (const element of descendants(sheet)) {
    if (element.name !== "row") continue;
    // A worksheet omits a row that holds nothing, and its `r` attribute is the real row number.
    // The gap has to be filled: every report is read by position — five header rows, then the
    // body — so a missing blank row shifts the whole file up by one and the first transaction
    // disappears into the header.
    const declared = element.attributes.r;
    if (declared !== undefined) while (out.length < Number(declared) - 1) out.push([]);

    const values = new Map<number, string>();
    for (const cell of element.children) {
      if (cell.name !== "c") continue;
      const at = column(cell.attributes.r ?? "A");
      const kind = cell.attributes.t;
      const formula = child(cell, "f");
      if (formula !== undefined) {
        values.set(at, "=" + formula.text);
        continue;
      }
      if (kind === "inlineStr") {
        values.set(at, textOf(cell, "t"));
        continue;
      }
      const raw = child(cell, "v")?.text;
      if (raw === undefined || raw === "") continue;
      values.set(at, kind === "s" ? (strings[Number(raw)] ?? "") : raw);
    }
    const width = values.size === 0 ? 0 : Math.max(...values.keys()) + 1;
    out.push(Array.from({ length: width }, (_, at) => values.get(at) ?? null));
  }
  return out;
}
