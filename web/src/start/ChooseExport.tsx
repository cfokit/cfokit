import { useState } from "react";
import { DropZone, Notice } from "../components";
import type { Export } from "../quickbooks/read";
import { readExport } from "../quickbooks/readExport";
import type { RefusalCode } from "../quickbooks/refused";

/** What to do about each refusal, in the person's terms rather than the reader's. */
const REFUSED: Record<RefusalCode, { label: string; what: string }> = {
  import_too_large: {
    label: "Too large to be an export",
    what: "This file is far larger than a QuickBooks export. Check you chose the .zip QuickBooks gave you.",
  },
  import_refused: {
    label: "Not a QuickBooks export",
    what: "This zip has no journal in it, so it isn't a QuickBooks Online export. Export again from QuickBooks and choose that file.",
  },
  unreadable_figure: {
    label: "A figure couldn't be read",
    what: "One of the reports holds a figure CFOKit can't read exactly, so nothing was read. Export again from QuickBooks, without editing the files.",
  },
  unreadable_archive: {
    label: "The file is damaged",
    what: "This isn't a zip archive CFOKit can open. Download the export from QuickBooks again.",
  },
};

type State =
  | { kind: "choosing" }
  | { kind: "reading"; name: string }
  | { kind: "refused"; code: RefusalCode; detail: string }
  | { kind: "wrong-type"; name: string };

/**
 * How to export from QuickBooks, and where the file is chosen. The file is read here, in the
 * browser, and never sent anywhere: only what is read from it is (ADR-0058 § 1).
 */
export function ChooseExport({ onRead }: { onRead: (exported: Export) => void }) {
  const [state, setState] = useState<State>({ kind: "choosing" });

  const take = async (file: File) => {
    setState({ kind: "reading", name: file.name });
    const reading = await readExport(file);
    if (reading.ok) onRead(reading.export);
    else setState({ kind: "refused", code: reading.code, detail: reading.detail });
  };

  return (
    <div className="flex flex-col gap-6">
      <p className="text-body text-ink">
        In QuickBooks Online, open <strong>Settings → Export data</strong>, choose{" "}
        <strong>Reports</strong> and <strong>All dates</strong>, and export. QuickBooks gives you a
        .zip of its reports. Choose that file here: it is read on this device, and the file itself
        is never uploaded.
      </p>
      {state.kind === "reading" ? (
        <Notice tone="neutral" label="Reading the export" announce>
          Reading {state.name}…
        </Notice>
      ) : (
        <DropZone
          prompt="Drop the QuickBooks export here, or choose it from your computer."
          accept=".zip"
          onFile={(file) => void take(file)}
          onReject={(file) => setState({ kind: "wrong-type", name: file.name })}
        />
      )}
      {state.kind === "refused" && (
        <Notice tone="danger" label={REFUSED[state.code].label} announce>
          {REFUSED[state.code].what} <span className="text-ink-muted">({state.detail})</span>
        </Notice>
      )}
      {state.kind === "wrong-type" && (
        <Notice tone="danger" label="Not a .zip file" announce>
          {state.name} isn&apos;t a .zip. QuickBooks exports its reports as one .zip file.
        </Notice>
      )}
    </div>
  );
}
