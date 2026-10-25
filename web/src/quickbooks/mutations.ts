/**
 * The fixture's file cases: its accrual archive, damaged the ways real exports are before they
 * reach a reader (ADR-0078, ADR-0079).
 *
 * The same mutations as `scripts/synthetic_books/mutations.py`, written again rather than shared:
 * nothing is shared between the two languages, and each is a few lines over a zip. Each is a
 * function of the archive's bytes and nothing else, named by its catalog id, and made when a test
 * needs it rather than committed. Test support only: nothing the client builds imports it.
 */

import Big from "big.js";
import { rows } from "./sheet";
import { zip } from "./synthetic";
import { Zip } from "./zip";

const JOURNAL = "Journal.xlsx";
const SHEET = "xl/worksheets/sheet1.xml";
const STRINGS = "xl/sharedStrings.xml";

type Members = Record<string, Uint8Array>;

const encoder = new TextEncoder();
const decoder = new TextDecoder();

/** One member, which every mutation's archive is known to carry. */
function part(members: Members, name: string): Uint8Array {
  const found = members[name];
  if (found === undefined) throw new Error(`the archive carries no ${name}`);
  return found;
}

async function contents(data: Uint8Array): Promise<Members> {
  const archive = new Zip(data);
  const out: Members = {};
  for (const name of archive.names()) out[name] = await archive.read(name);
  return out;
}

/** The archive with one workbook's parts changed by `change`, everything else as it was. */
async function rebuild(
  data: Uint8Array,
  member: string,
  change: (parts: Members) => void,
): Promise<Uint8Array> {
  const members = await contents(data);
  const parts = await contents(part(members, member));
  change(parts);
  members[member] = await zip(parts);
  return zip(members);
}

function indexOf(haystack: Uint8Array, needle: Uint8Array, from: number): number {
  outer: for (let at = from; at <= haystack.length - needle.length; at++) {
    for (let k = 0; k < needle.length; k++) if (haystack[at + k] !== needle[k]) continue outer;
    return at;
  }
  return -1;
}

/** The Journal's worksheet cut off partway through a row, re-zipped as a valid archive. */
function truncatedSheet(data: Uint8Array): Promise<Uint8Array> {
  return rebuild(data, JOURNAL, (parts) => {
    const sheet = part(parts, SHEET);
    const at = indexOf(sheet, encoder.encode("<row "), Math.floor((sheet.length * 3) / 5));
    parts[SHEET] = sheet.slice(0, at + 40);
  });
}

/** One more row above the Journal's column headings, as a customized report prints. */
function extraHeaderRow(data: Uint8Array): Promise<Uint8Array> {
  return rebuild(data, JOURNAL, (parts) => {
    const later = (_: string, prefix: string, number: string) =>
      `${prefix}${Number(number) >= 5 ? Number(number) + 1 : number}`;
    let sheet = decoder.decode(part(parts, SHEET));
    sheet = sheet.replace(/(<row r=")(\d+)/g, later).replace(/(<c r="[A-Z]+)(\d+)/g, later);
    const inserted =
      '<row r="5"><c r="A5" t="inlineStr"><is><t>Filtered by: All accounts</t></is></c></row>';
    sheet = sheet.replace('<row r="6">', inserted + '<row r="6">');
    parts[SHEET] = encoder.encode(sheet);
  });
}

/** The first é in the Journal's strings made into a byte sequence UTF-8 does not allow. */
function invalidUtf8(data: Uint8Array): Promise<Uint8Array> {
  return rebuild(data, JOURNAL, (parts) => {
    const strings = part(parts, STRINGS);
    const at = indexOf(strings, encoder.encode("é"), 0);
    const damaged = strings.slice();
    damaged[at + 1] = 0x28;
    parts[STRINGS] = damaged;
  });
}

/** Unzipped and zipped again on a Mac: AppleDouble entries under __MACOSX/ for each file. */
async function macosRezip(data: Uint8Array): Promise<Uint8Array> {
  const members = await contents(data);
  const appleDouble = new Uint8Array([
    ...[0x00, 0x05, 0x16, 0x07, 0x00, 0x02, 0x00, 0x00],
    ...encoder.encode("Mac OS X        "),
    ...new Uint8Array(64),
  ]);
  for (const name of Object.keys(members)) members[`__MACOSX/._${name}`] = appleDouble;
  members[".DS_Store"] = new Uint8Array([
    0,
    0,
    0,
    1,
    ...encoder.encode("Bud1"),
    ...new Uint8Array(32),
  ]);
  return zip(members);
}

/** Zipped as a folder: every report under export/ rather than at the root. */
async function nestedFolder(data: Uint8Array): Promise<Uint8Array> {
  const members = await contents(data);
  return zip(Object.fromEntries(Object.entries(members).map(([n, b]) => [`export/${n}`, b])));
}

/**
 * A worksheet's formulas worked out, by cell: QuickBooks' formulas are a number, or sums and
 * differences of cells and bracketed terms, such as `((B11)+(B14))+(B18)`.
 */
function results(sheet: string): Map<string, Big> {
  const cells = new Map<string, { formula: string | undefined; value: string | undefined }>();
  for (const [, ref = "", body = ""] of sheet.matchAll(/<c r="([A-Z]+\d+)"[^>]*>(.*?)<\/c>/g)) {
    cells.set(ref, {
      formula: /<f>([^<]*)<\/f>/.exec(body)?.[1],
      value: /<v>([^<]*)<\/v>/.exec(body)?.[1],
    });
  }
  const worked = new Map<string, Big>();
  const figure = (ref: string): Big => {
    const cell = cells.get(ref);
    if (cell === undefined) return new Big(0);
    if (cell.formula === undefined) return new Big(cell.value ?? 0);
    if (!worked.has(ref)) worked.set(ref, evaluate(cell.formula));
    return worked.get(ref) as Big;
  };
  const evaluate = (text: string): Big => {
    const tokens = text.match(/[A-Z]+\d+|\d+(?:\.\d+)?|[()+-]/g) ?? [];
    let at = 0;
    const term = (): Big => {
      const token = tokens[at++] ?? "0";
      if (token === "-") return term().times(-1);
      if (token === "(") {
        const inner = expression();
        at++; // the closing bracket
        return inner;
      }
      return /^[A-Z]/.test(token) ? figure(token) : new Big(token);
    };
    const expression = (): Big => {
      let total = term();
      while (tokens[at] === "+" || tokens[at] === "-") {
        const sign = tokens[at++];
        total = sign === "+" ? total.plus(term()) : total.minus(term());
      }
      return total;
    };
    return expression();
  };
  for (const [ref, cell] of cells) if (cell.formula !== undefined) figure(ref);
  return worked;
}

/**
 * Every workbook as Excel saves it: a formula's result cached beside it, numbers without trailing
 * zeros, and the styles and document properties Excel always writes.
 */
async function excelResave(data: Uint8Array): Promise<Uint8Array> {
  const members = await contents(data);
  for (const [name, body] of Object.entries(members)) {
    const parts = await contents(body);
    let sheet = decoder.decode(part(parts, SHEET));
    const worked = results(sheet);
    sheet = sheet.replace(
      /<c r="([A-Z]+\d+)"><f>([^<]*)<\/f><v>0<\/v><\/c>/g,
      (_, ref: string, formula: string) =>
        `<c r="${ref}"><f>${formula}</f><v>${(worked.get(ref) as Big).toFixed()}</v></c>`,
    );
    sheet = sheet.replace(/<v>(-?\d+)\.(\d*?)0*<\/v>/g, (_, whole: string, fraction: string) =>
      fraction ? `<v>${whole}.${fraction}</v>` : `<v>${whole}</v>`,
    );
    parts[SHEET] = encoder.encode(sheet);
    parts["xl/styles.xml"] = encoder.encode(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>' +
        "</styleSheet>",
    );
    parts["docProps/app.xml"] = encoder.encode(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        "<Properties><Application>Microsoft Excel</Application></Properties>",
    );
    members[name] = await zip(parts);
  }
  return zip(members);
}

/** Journal.xlsx chosen on its own, rather than the archive it came in. */
async function singleWorkbook(data: Uint8Array): Promise<Uint8Array> {
  return part(await contents(data), JOURNAL);
}

/** The journal as the report screen exports it to CSV, rather than through Export Data. */
async function csvInstead(data: Uint8Array): Promise<Uint8Array> {
  const journal = await rows(new Zip(part(await contents(data), JOURNAL)));
  const field = (cell: string | null) => {
    const text = cell ?? "";
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = journal.map((row) => row.map(field).join(",") + "\r\n");
  return encoder.encode("﻿" + lines.join(""));
}

export const MUTATIONS: Record<string, (data: Uint8Array) => Promise<Uint8Array>> = {
  "f-truncated-sheet": truncatedSheet,
  "f-extra-header-row": extraHeaderRow,
  "f-invalid-utf8": invalidUtf8,
  "f-macos-rezip": macosRezip,
  "f-nested-folder": nestedFolder,
  "f-excel-resave": excelResave,
  "f-single-workbook": singleWorkbook,
  "f-csv-instead": csvInstead,
};
