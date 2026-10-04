import { wrap } from "comlink";
import type { Export } from "./read";
import type { Reader } from "./reader.worker";
import type { RefusalCode } from "./refused";
import { MAX_ARCHIVE_BYTES } from "./zip";

/** An export read, or the reason it was not. A refusal crosses from the worker as data. */
export type Reading =
  { ok: true; export: Export } | { ok: false; code: RefusalCode; detail: string };

/** Read a QuickBooks export in a Web Worker, which is ended once it answers. */
export async function readExport(file: File): Promise<Reading> {
  // Refused before a byte is read: a file this large is not an export, whatever it holds.
  if (file.size > MAX_ARCHIVE_BYTES) {
    return { ok: false, code: "import_too_large", detail: `the file is ${file.size} bytes` };
  }
  const worker = new Worker(new URL("./reader.worker.ts", import.meta.url), { type: "module" });
  try {
    return await wrap<Reader>(worker).read(file);
  } finally {
    worker.terminate();
  }
}
