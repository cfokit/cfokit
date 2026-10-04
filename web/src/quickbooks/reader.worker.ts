// The export is read off the page's thread, so a large one does not freeze the page (ADR-0049).
import { expose } from "comlink";
import { read } from "./read";
import type { Reading } from "./readExport";
import { Refused } from "./refused";

const reader = {
  async read(file: File): Promise<Reading> {
    try {
      return { ok: true, export: await read(new Uint8Array(await file.arrayBuffer())) };
    } catch (error) {
      if (error instanceof Refused) return { ok: false, code: error.code, detail: error.message };
      return { ok: false, code: "unreadable_archive", detail: String(error) };
    }
  },
};

export type Reader = typeof reader;

expose(reader);
